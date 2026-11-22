"""
Phase 7: what drives CardioStage's predictions, and is it reasoning sensibly?

  1. GLOBAL importance: average size of each measurement's SHAP contribution,
     per stage, over all 243 training patients.
  2. EFFECT shapes: how risk changes as a measurement changes (dependence).
  3. SANITY checks: do effects point in medically expected directions?
  4. CASE STUDY: the woman with atypical chest pain who was cleared at
     stage 1 in Phase 6, explained at stage 1 and stage 3.

Run:  python -m cardiostage.explanations     (~1-2 minutes, all CPU cores)
"""

import json

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from cardiostage import config, integrity
from cardiostage.data import load_clean, split_cleveland
from cardiostage.explain import LABELS, StageExplainer, explanation_text
from cardiostage.staging import simulate_policy

UP, DOWN, TEXT = "#eb6834", "#2a78d6", "#52514e"


def _explain_chunk(model, features, background, chunk):
    explainer = StageExplainer(model, features, background)
    e = explainer.explain(chunk)
    return e.values, e.base_values


def explain_all(bundle, train) -> tuple:
    """SHAP values for every training patient, computed in parallel chunks."""
    chunks = np.array_split(np.arange(len(train)), 20)
    results = Parallel(n_jobs=-1)(
        delayed(_explain_chunk)(bundle["model"], bundle["features"], train, train.iloc[idx])
        for idx in chunks
    )
    values = np.vstack([r[0] for r in results])
    base = np.concatenate([r[1] for r in results])
    return values, base


def direction_checks(train, shap_values: dict) -> pd.DataFrame:
    """
    Expected directions from cardiology / Phase 2's data exploration:
      numeric : sign of the correlation between value and contribution
      category: average contribution for that category
    """
    s3 = pd.DataFrame(shap_values[3], columns=config.STAGES[3], index=train.index)
    checks = [
        ("thalch", "numeric", None, "-", "higher max heart rate lowers risk"),
        ("oldpeak", "numeric", None, "+", "more ST depression raises risk"),
        ("ca", "numeric", None, "+", "more blocked vessels raise risk"),
        ("age", "numeric", None, "+", "older age raises risk"),
        ("trestbps", "numeric", None, "+", "higher blood pressure raises risk"),
        ("sex", "category", 1.0, "+", "male sex raises risk"),
        ("exang", "category", 1.0, "+", "exercise chest pain raises risk"),
        ("cp", "category", "asymptomatic", "+", "no chest pain raises risk (referral paradox)"),
        ("cp", "category", "atypical angina", "-", "atypical angina lowers risk"),
        ("thal", "category", "reversable defect", "+", "reversible defect raises risk"),
        ("thal", "category", "normal", "-", "normal thallium scan lowers risk"),
        ("slope", "category", "upsloping", "-", "upsloping ST segment lowers risk"),
    ]
    rows = []
    for feature, kind, value, expected, meaning in checks:
        if kind == "numeric":
            stat = np.corrcoef(train[feature].fillna(train[feature].median()), s3[feature])[0, 1]
        else:
            stat = s3.loc[train[feature] == value, feature].mean()
        ok = (stat > 0) if expected == "+" else (stat < 0)
        rows.append(
            {
                "check": meaning,
                "statistic": round(float(stat), 3),
                "expected": expected,
                "passes": bool(ok),
            }
        )
    return pd.DataFrame(rows)


def find_case_study(train):
    """The sick woman cleared at stage 1 by the staged policy (Phase 6)."""
    saved = integrity.load(config.MODELS_DIR / "phase5_oof.joblib")
    y = saved["y"]
    p = {s: saved["oof"][s][saved["method"][s]].mean(axis=0) for s in config.STAGES}
    with open(config.REPORTS_DIR / "phase5_zones.json") as f:
        zones = {int(s): z for s, z in json.load(f)["zones"].items()}
    decision, stopped = simulate_policy(p, zones)
    mask = (decision == 0) & (y == 1) & (stopped == 1) & (train["sex"].to_numpy() == 0)
    return train.iloc[np.flatnonzero(mask)[:1]]


# ----------------------------------------------------------------------------
# Charts
# ----------------------------------------------------------------------------
def _clean(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def _save(fig, name):
    path = config.FIGURES_DIR / name
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {path.relative_to(config.PROJECT_ROOT)}")


def plot_importance(importance: dict):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), gridspec_kw={"width_ratios": [6, 11, 13]})
    for ax, stage in zip(axes, config.STAGES):
        imp = importance[stage].sort_values()
        ax.barh([LABELS[f] for f in imp.index], imp.values * 100, color="#2a78d6", height=0.6)
        for i, v in enumerate(imp.values):
            ax.text(v * 100 + 0.2, i, f"{v * 100:.1f}", va="center", color=TEXT, fontsize=8.5)
        ax.set_title(f"Stage {stage}: {config.STAGE_NAMES[stage]}", fontweight="bold")
        ax.set_xlabel("Average impact on risk (percentage points)")
        ax.set_xlim(0, max(imp_s.max() for imp_s in importance.values()) * 100 * 1.2)
        _clean(ax)
    fig.suptitle(
        "What drives each stage's predictions (mean |SHAP| over 243 training patients)",
        fontweight="bold",
        y=1.02,
    )
    fig.tight_layout()
    _save(fig, "15_global_importance.png")


def plot_effects(train, shap3):
    features = ["thalch", "oldpeak", "age", "chol"]
    fig, axes = plt.subplots(1, 4, figsize=(16, 3.6), sharey=True)
    s3 = pd.DataFrame(shap3, columns=config.STAGES[3])
    for ax, f in zip(axes, features):
        x = train[f].to_numpy()
        ax.scatter(x, s3[f] * 100, s=18, alpha=0.6, color="#2a78d6", edgecolor="none")
        ax.axhline(0, color="#b5b4ae", linewidth=1)
        ax.set_title(LABELS[f], fontweight="bold")
        ax.grid(color="#ebeae6")
        _clean(ax)
    axes[0].set_ylabel("Contribution to risk (pts)")
    fig.suptitle(
        "How each measurement's value changes the stage-3 prediction (one dot per patient)",
        fontweight="bold",
        y=1.04,
    )
    _save(fig, "16_feature_effects.png")


def plot_case_study(cases: list):
    fig, axes = plt.subplots(1, len(cases), figsize=(15, 4.4))
    for ax, (title, table, base, risk) in zip(axes, cases):
        t = table.head(8).iloc[::-1]
        colors = [UP if v > 0 else DOWN for v in t["contribution"]]
        labels = [f"{r.label} = {r.value}" for r in t.itertuples()]
        ax.barh(labels, t["contribution"] * 100, color=colors, height=0.6)
        for i, v in enumerate(t["contribution"] * 100):
            ax.text(
                v + (0.3 if v >= 0 else -0.3),
                i,
                f"{v:+.1f}",
                va="center",
                ha="left" if v >= 0 else "right",
                color=TEXT,
                fontsize=9,
            )
        ax.axvline(0, color="#52514e", linewidth=1)
        lim = max(abs(t["contribution"]).max() * 100 * 1.5, 5)
        ax.set_xlim(-lim, lim)
        ax.set_title(f"{title}\nbaseline {base:.0%}  →  risk {risk:.0%}", fontweight="bold")
        ax.set_xlabel("Contribution (percentage points)")
        _clean(ax)
    fig.suptitle(
        "Case study: a sick woman with atypical chest pain, cleared at the basic check-up",
        fontweight="bold",
        y=1.06,
    )
    fig.tight_layout()
    _save(fig, "17_case_study.png")


def main():
    train, _sealed_test = split_cleveland(load_clean())
    bundles = {s: integrity.load(config.MODELS_DIR / f"stage{s}.joblib") for s in config.STAGES}

    shap_values, importance = {}, {}
    for stage in config.STAGES:
        values, base = explain_all(bundles[stage], train)
        shap_values[stage] = values
        importance[stage] = pd.Series(np.abs(values).mean(axis=0), index=config.STAGES[stage])
        pred = bundles[stage]["model"].predict_proba(train[config.STAGES[stage]])[:, 1]
        gap = np.abs(base + values.sum(axis=1) - pred).max()
        print(f"Stage {stage}: explained {len(train)} patients; additivity gap {gap:.2e}")

    imp_table = pd.DataFrame(importance).round(4)
    imp_table.columns = [f"stage_{s}" for s in config.STAGES]
    imp_table.to_csv(config.REPORTS_DIR / "phase7_importance.csv")
    print("\nMean |SHAP| (probability units):\n", (imp_table * 100).round(1).to_string())

    checks = direction_checks(train, shap_values)
    checks.to_csv(config.REPORTS_DIR / "phase7_direction_checks.csv", index=False)
    print("\nDirection sanity checks (stage 3):\n", checks.to_string(index=False))

    case = find_case_study(train)
    cases = []
    for stage in (1, 3):
        b = bundles[stage]
        explainer = StageExplainer(b["model"], b["features"], train)
        e = explainer.explain(case)
        table = explainer.describe(case.iloc[0], e[0])
        risk = float(b["model"].predict_proba(case[b["features"]])[0, 1])
        base = float(e.base_values[0])
        print(f"\nCase study, stage {stage}: " + explanation_text(table, base, risk))
        cases.append((f"Stage {stage}: {config.STAGE_NAMES[stage]}", table, base, risk))

    plot_importance(importance)
    plot_effects(train, shap_values[3])
    plot_case_study(cases)
    joblib.dump(
        {"shap_values": shap_values, "index": train.index.to_numpy()},
        config.MODELS_DIR / "phase7_shap.joblib",
    )


if __name__ == "__main__":
    main()
