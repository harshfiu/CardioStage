"""
Phase 6a: does CardioStage work at hospitals it has never seen?

The final stage models were trained ONLY on Cleveland. Here we apply them,
unchanged, to every patient from Hungary, Switzerland and VA Long Beach.
This is called EXTERNAL VALIDATION, and it's the strongest evidence a medical
model can offer short of a clinical trial: a different place, different
staff, different equipment, different patients.

Only stages 1 and 2 can be tested: the stage-3 tests (ca, thal) are 83-99%
missing outside Cleveland (Phase 2), so "results" there would mostly measure
our gap-filling, not the model.

For each hospital we check:
  - ranking   : ROC-AUC, with 95% bootstrap CI
  - honesty   : average predicted risk vs actual disease rate, and ECE
  - decisions : how safe the stage's "clear" zone is, how accurate "refer" is,
                and recall/specificity at the stage's 97%-recall threshold
  - warnings  : are patients flagged "unusual" really predicted worse?
  - a fix     : PRIOR SHIFT, adjusting for the local disease rate (stats.py)

Run:  python -m cardiostage.external_validation
"""

import json

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

from cardiostage import config
from cardiostage.calibration import _reliability, expected_calibration_error
from cardiostage.data import get_features_and_target, load_clean, split_cleveland
from cardiostage.stats import bootstrap_ci, fmt_ci, prior_shift
from cardiostage.thresholds import decision_metrics, threshold_for_recall

EXTERNAL_STAGES = (1, 2)
HOSPITAL_COLORS = {"Cleveland (internal, out-of-fold)": "#52514e", "Hungary": "#2a78d6",
                   "VA Long Beach": "#eb6834", "Switzerland": "#1baf7a"}
TEXT = "#52514e"


def load_bundles():
    return {s: joblib.load(config.MODELS_DIR / f"stage{s}.joblib") for s in config.STAGES}


def internal_reference():
    """Cleveland out-of-fold predictions (Phase 5) and each stage's 97%-recall threshold."""
    saved = joblib.load(config.MODELS_DIR / "phase5_oof.joblib")
    y = saved["y"]
    p = {s: saved["oof"][s][saved["method"][s]].mean(axis=0) for s in config.STAGES}
    thresholds = {s: threshold_for_recall(y, p[s], config.SCREENING_RECALL) for s in config.STAGES}
    return y, p, thresholds


def evaluate(y, p, zones, threshold, unusual=None) -> dict:
    """All metrics for one hospital at one stage."""
    y, p = np.asarray(y), np.asarray(p)
    auc = bootstrap_ci(roc_auc_score, y, p, need_both_classes=True)
    cleared = p < zones["rule_out_below"]
    referred = p >= zones["rule_in_from"]
    at_threshold = decision_metrics(y, (p >= threshold).astype(int))
    row = {
        "n": len(y), "disease_rate": y.mean(), "mean_predicted": p.mean(),
        "roc_auc": fmt_ci(*auc), "auc_value": auc[0], "auc_low": auc[1], "auc_high": auc[2],
        "ece": expected_calibration_error(y, p), "brier": brier_score_loss(y, p),
        "recall@97": at_threshold["recall"], "specificity@97": at_threshold["specificity"],
        "share_cleared": cleared.mean(),
        "cleared_but_sick": int((cleared & (y == 1)).sum()),
        "npv_cleared": 1 - y[cleared].mean() if cleared.any() else np.nan,
        "share_referred": referred.mean(),
        "ppv_referred": y[referred].mean() if referred.any() else np.nan,
    }
    if unusual is not None:
        row["share_unusual"] = unusual.mean()
    return row


def missing_summary(df, stage) -> pd.Series:
    """Share of each hospital's stage features that had to be filled in."""
    features = config.STAGES[stage]
    return df.groupby(config.HOSPITAL_COLUMN)[features].apply(lambda g: g.isna().mean().mean())


def plot_external_auc(table: pd.DataFrame):
    fig, axes = plt.subplots(1, 2, figsize=(13, 3.8), sharex=True, sharey=True)
    fig.subplots_adjust(wspace=0.08)
    for ax, stage in zip(axes, EXTERNAL_STAGES):
        sub = table[table["stage"] == stage]
        for i, (_, row) in enumerate(sub.iterrows()):
            color = HOSPITAL_COLORS[row["hospital"]]
            err = [[row.auc_value - row.auc_low], [row.auc_high - row.auc_value]]
            ax.errorbar(row.auc_value, i, xerr=err, fmt="o", color=color, markersize=9,
                        capsize=4, linewidth=2)
            ax.text(row.auc_high + 0.01, i, f"{row.auc_value:.3f}  (n={int(row.n)})",
                    va="center", color=TEXT, fontsize=9)
        if stage == EXTERNAL_STAGES[0]:  # hospital names on the left panel only
            ax.set_yticks(range(len(sub)), sub["hospital"])
        ax.set_ylim(len(sub) - 0.5, -0.5)
        ax.axvline(0.5, color="#b5b4ae", linestyle="--", linewidth=1)
        ax.set_xlim(0.4, 1.12)
        ax.set_title(f"Stage {stage}: {config.STAGE_NAMES[stage]}", fontweight="bold")
        ax.set_xlabel("ROC-AUC (95% CI)")
        ax.grid(axis="x", color="#ebeae6"); ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    fig.suptitle("External validation: Cleveland-trained models at unseen hospitals",
                 fontweight="bold", y=1.03)
    _save(fig, "12_external_auc.png")


def plot_external_calibration(curves: dict):
    hospitals = config.EXTERNAL_HOSPITALS
    fig, axes = plt.subplots(1, len(hospitals), figsize=(14, 4.4), sharey=True)
    for ax, hospital in zip(axes, hospitals):
        y, p, p_shift = curves[hospital]
        ax.plot([0, 1], [0, 1], linestyle="--", color="#b5b4ae", linewidth=1, label="Perfectly honest")
        for probs, color, label in [(p, "#eb6834", "as trained"),
                                    (p_shift, "#2a78d6", "after prior shift")]:
            mx, my = _reliability(y, probs, n_bins=6)
            ax.plot(mx, my, "o-", color=color, linewidth=2, markersize=7,
                    label=f"{label} (ECE {expected_calibration_error(y, probs):.3f})")
        ax.set_title(f"{hospital}  (disease rate {y.mean():.0%})", fontweight="bold")
        ax.set_xlabel("Predicted risk"); ax.set_xlim(0, 1); ax.set_ylim(0, 1.02)
        ax.legend(frameon=False, loc="upper left", fontsize=8.5)
        ax.grid(color="#ebeae6")
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[0].set_ylabel("Actual share with heart disease")
    fig.suptitle("Stage 1 calibration at unseen hospitals, before and after adjusting for "
                 "local disease rate", fontweight="bold", y=1.03)
    _save(fig, "13_external_calibration.png")


def _save(fig, name):
    path = config.FIGURES_DIR / name
    fig.savefig(path, dpi=150, bbox_inches="tight"); plt.close(fig)
    print(f"saved {path.relative_to(config.PROJECT_ROOT)}")


def main():
    df = load_clean()
    train, _sealed_test = split_cleveland(df)
    bundles = load_bundles()
    y_int, p_int, thresholds = internal_reference()
    train_rate = train[config.TARGET_COLUMN].mean()

    rows, curves, unusual_quality = [], {}, []
    for stage in EXTERNAL_STAGES:
        b = bundles[stage]
        rows.append({"stage": stage, "hospital": "Cleveland (internal, out-of-fold)",
                     **evaluate(y_int, p_int[stage], b["zones"], thresholds[stage])})
        for hospital in config.EXTERNAL_HOSPITALS:
            X, y = get_features_and_target(df[df[config.HOSPITAL_COLUMN] == hospital], stage)
            p = b["model"].predict_proba(X)[:, 1]
            unusual = b["novelty"].is_unusual(X)
            row = evaluate(y, p, b["zones"], thresholds[stage], unusual)
            p_shift = prior_shift(p, train_rate, y.mean())
            row["ece_after_prior_shift"] = expected_calibration_error(y, p_shift)
            row["mean_predicted_after_shift"] = p_shift.mean()
            rows.append({"stage": stage, "hospital": hospital, **row})
            if stage == 1:
                curves[hospital] = (y.to_numpy(), p, p_shift)
            unusual_quality.append(pd.DataFrame({
                "stage": stage, "unusual": unusual,
                "sq_error": (p - y.to_numpy()) ** 2}))

    table = pd.DataFrame(rows)
    table.to_csv(config.REPORTS_DIR / "phase6_external.csv", index=False)
    show = ["stage", "hospital", "n", "disease_rate", "mean_predicted", "roc_auc", "ece",
            "recall@97", "specificity@97", "share_cleared", "cleared_but_sick", "npv_cleared",
            "share_referred", "ppv_referred", "share_unusual", "ece_after_prior_shift"]
    pd.set_option("display.width", 250, "display.max_columns", 30)
    print(table[show].round(3).to_string(index=False))

    print("\nShare of each stage's inputs that were missing (filled in by the model's imputer):")
    print(pd.DataFrame({f"stage_{s}": missing_summary(df, s) for s in EXTERNAL_STAGES}).round(3))

    # Are "unusual" patients predicted worse? Compare Brier (mean squared error).
    uq = pd.concat(unusual_quality)
    uq_table = uq.groupby(["stage", "unusual"])["sq_error"].agg(["mean", "size"]).round(4)
    uq_table.to_csv(config.REPORTS_DIR / "phase6_unusual_vs_error.csv")
    print("\nBrier score (lower = better) for unusual vs typical external patients:\n", uq_table)

    plot_external_auc(table)
    plot_external_calibration(curves)


if __name__ == "__main__":
    main()
