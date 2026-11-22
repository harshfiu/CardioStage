"""
Phase 4: staged screening, CardioStage's headline feature.

Questions answered:
  1. How good is each stage's best model?   (basic -> +treadmill -> +invasive)
  2. How much does each extra test add?
  3. If we escalate tests only for UNCERTAIN patients, how many tests can we
     save while still catching sick patients?

Method
------
For every stage we run the same nested cross-validation as Phase 3 (outer
5 folds x 3 repeats, inner 5-fold grid search), with one addition: we keep
every patient's OUT-OF-FOLD probability, meaning the prediction made by a
model that never saw that patient. Because all stages use the identical
outer folds, each patient gets an honest "unseen" probability at stage 1,
2 and 3, which lets us simulate the step-by-step policy on real patients.

Candidates per stage: the 3 Phase 3 models + an ENSEMBLE that averages their
probabilities (averaging different kinds of models often cancels out their
individual errors).

Run:  python -m cardiostage.staging      (a few minutes)
"""

import json
import time

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import VotingClassifier
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.model_selection import (GridSearchCV, RepeatedStratifiedKFold,
                                     StratifiedKFold)

from cardiostage import config
from cardiostage.data import get_features_and_target, load_clean, split_cleveland
from cardiostage.models import MODEL_LABELS, MODEL_NAMES, PARAM_GRIDS, build_pipeline
from cardiostage.thresholds import (decision_metrics, threshold_for_precision,
                                    threshold_for_recall)

CANDIDATES = MODEL_NAMES + ["ensemble"]
LABELS = {**MODEL_LABELS, "ensemble": "Ensemble (average of 3)"}
COLORS = {"logistic_regression": "#2a78d6", "random_forest": "#eb6834",
          "xgboost": "#1baf7a", "ensemble": "#eda100"}
STAGE_COLORS = {1: "#2a78d6", 2: "#eb6834", 3: "#1baf7a"}
TEXT = "#52514e"


# ----------------------------------------------------------------------------
# 1. Out-of-fold predictions for every stage and model
# ----------------------------------------------------------------------------
def grid_search(name: str, stage: int) -> GridSearchCV:
    return GridSearchCV(build_pipeline(name, stage), PARAM_GRIDS[name],
                        scoring="roc_auc", n_jobs=-1,
                        cv=StratifiedKFold(config.CV_FOLDS, shuffle=True,
                                           random_state=config.RANDOM_SEED))


def outer_cv() -> RepeatedStratifiedKFold:
    # Same seed every time -> identical folds for every stage.
    return RepeatedStratifiedKFold(n_splits=config.CV_FOLDS, n_repeats=config.CV_REPEATS,
                                   random_state=config.RANDOM_SEED)


def collect_out_of_fold(train: pd.DataFrame):
    """
    Returns
      oof[stage][model]      -> array (repeats, patients) of unseen probabilities
      fold_auc[stage][model] -> list of 15 outer-fold ROC-AUCs
    """
    y = train[config.TARGET_COLUMN].to_numpy()
    oof = {s: {m: np.full((config.CV_REPEATS, len(y)), np.nan) for m in CANDIDATES}
           for s in config.STAGES}
    fold_auc = {s: {m: [] for m in CANDIDATES} for s in config.STAGES}

    for stage in config.STAGES:
        X, _ = get_features_and_target(train, stage)
        start = time.time()
        for i, (tr, te) in enumerate(outer_cv().split(X, y)):
            repeat = i // config.CV_FOLDS
            probs = {}
            for name in MODEL_NAMES:
                tuned = grid_search(name, stage).fit(X.iloc[tr], y[tr])
                probs[name] = tuned.predict_proba(X.iloc[te])[:, 1]
            probs["ensemble"] = np.mean([probs[n] for n in MODEL_NAMES], axis=0)
            for name, p in probs.items():
                oof[stage][name][repeat, te] = p
                fold_auc[stage][name].append(roc_auc_score(y[te], p))
        print(f"Stage {stage}: done in {time.time() - start:.0f}s  " + "  ".join(
            f"{m[:6]} {np.mean(fold_auc[stage][m]):.3f}" for m in CANDIDATES))
    return y, oof, fold_auc


# ----------------------------------------------------------------------------
# 2. Decision zones and the staged policy
# ----------------------------------------------------------------------------
def compute_zones(y, p_by_stage: dict) -> dict:
    """
    Stages 1-2 get LOW / UNCERTAIN / HIGH zones; stage 3 (the last) gets a
    single screening threshold, because there's no further test to send to.
    """
    zones = {}
    for stage in (1, 2):
        zones[stage] = {
            "rule_out_below": threshold_for_recall(y, p_by_stage[stage], config.RULE_OUT_RECALL),
            "rule_in_from": threshold_for_precision(y, p_by_stage[stage], config.RULE_IN_PRECISION),
        }
    zones[3] = {"screening_threshold": threshold_for_recall(y, p_by_stage[3],
                                                            config.SCREENING_RECALL)}
    return zones


def simulate_policy(p_by_stage: dict, zones: dict):
    """
    Walk every patient through the stages:
      stage 1: HIGH -> refer (1), LOW -> clear (0), else go to stage 2
      stage 2: same rule for those still undecided
      stage 3: everyone left is decided by the screening threshold
    Returns (decision per patient, stage at which each patient stopped).
    """
    n = len(p_by_stage[1])
    decision = np.full(n, -1)
    stopped_at = np.zeros(n, dtype=int)
    for stage in (1, 2):
        p, z = p_by_stage[stage], zones[stage]
        undecided = decision == -1
        high = undecided & (p >= z["rule_in_from"])
        low = undecided & ~high & (p < z["rule_out_below"])
        decision[high], decision[low] = 1, 0
        stopped_at[high | low] = stage
    undecided = decision == -1
    decision[undecided] = (p_by_stage[3][undecided] >= zones[3]["screening_threshold"]).astype(int)
    stopped_at[undecided] = 3
    return decision, stopped_at


STAGED = "CardioStage staged policy"


def strategy_decisions(y, p_by_stage, zones) -> dict:
    """
    For each strategy: (decision per patient, stage each patient reached).
    "Everyone: stage s only" = give every patient the stage-s tests and use a
    threshold catching SCREENING_RECALL of sick patients.
    """
    out = {}
    for stage in (1, 2, 3):
        t = threshold_for_recall(y, p_by_stage[stage], config.SCREENING_RECALL)
        out[f"Everyone: stage {stage} only"] = (
            (p_by_stage[stage] >= t).astype(int), np.full(len(y), stage))
    out[STAGED] = simulate_policy(p_by_stage, zones)
    return out


def _summarise(y, decision, reached) -> dict:
    m = decision_metrics(y, decision)
    m["needed_treadmill"] = float((reached >= 2).mean())
    m["needed_invasive"] = float((reached == 3).mean())
    return m


def compare_strategies(y, p_by_stage, zones) -> pd.DataFrame:
    """CardioStage's staged policy vs giving everyone the same tests."""
    return pd.DataFrame({name: _summarise(y, d, r) for name, (d, r)
                         in strategy_decisions(y, p_by_stage, zones).items()}).T


def bootstrap_strategies(y, p_by_stage, zones, n_boot=2000) -> pd.DataFrame:
    """
    How much could these numbers wobble by chance? BOOTSTRAP: draw 243
    patients WITH replacement (some twice, some not at all), recompute every
    metric, repeat 2000 times. The middle 95% of results is a 95% confidence
    interval. Decisions are fixed beforehand; only the patient sample varies.

    Also computes the PAIRED difference (staged policy minus "everyone gets all
    tests") on each resample: if its interval contains 0, the two strategies
    are statistically indistinguishable on that metric.
    """
    rng = np.random.default_rng(config.RANDOM_SEED)
    decisions = strategy_decisions(y, p_by_stage, zones)
    metrics = ["recall", "specificity", "needed_invasive"]
    samples = {(name, m): [] for name in decisions for m in metrics}
    diffs = {m: [] for m in metrics}
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        summaries = {name: _summarise(y[idx], d[idx], r[idx]) for name, (d, r) in decisions.items()}
        for name, s in summaries.items():
            for m in metrics:
                samples[(name, m)].append(s[m])
        for m in metrics:
            diffs[m].append(summaries[STAGED][m] - summaries["Everyone: stage 3 only"][m])

    fmt = lambda v: f"{np.mean(v):.3f} [{np.percentile(v, 2.5):.3f}, {np.percentile(v, 97.5):.3f}]"
    table = pd.DataFrame({m: {name: fmt(samples[(name, m)]) for name in decisions} for m in metrics})
    table.loc["Difference: staged - all tests"] = {m: fmt(diffs[m]) for m in metrics}
    return table


# ----------------------------------------------------------------------------
# 3. Charts
# ----------------------------------------------------------------------------
def _clean_axes(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(color="#ebeae6"); ax.set_axisbelow(True)


def _save(fig, name):
    path = config.FIGURES_DIR / name
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {path.relative_to(config.PROJECT_ROOT)}")


def plot_auc_by_stage(fold_auc):
    fig, ax = plt.subplots(figsize=(8, 4.2))
    offsets = np.linspace(-0.18, 0.18, len(CANDIDATES))
    for off, name in zip(offsets, CANDIDATES):
        means = [np.mean(fold_auc[s][name]) for s in config.STAGES]
        stds = [np.std(fold_auc[s][name]) for s in config.STAGES]
        xs = np.array(list(config.STAGES)) + off
        ax.errorbar(xs, means, yerr=stds, fmt="o-", color=COLORS[name], label=LABELS[name],
                    markersize=8, capsize=3, linewidth=2)
    ax.set_xticks(list(config.STAGES), [f"Stage {s}\n{config.STAGE_NAMES[s]}" for s in config.STAGES])
    ax.set_ylabel("ROC-AUC (nested CV)")
    ax.set_ylim(0.6, 1.0)
    ax.legend(frameon=False, loc="lower right", fontsize=9)
    ax.set_title("What each test adds: ranking quality by stage", fontweight="bold")
    _clean_axes(ax)
    _save(fig, "07_auc_by_stage.png")


def plot_roc_by_stage(y, p_by_stage, chosen):
    fig, ax = plt.subplots(figsize=(5.6, 5.2))
    for stage in config.STAGES:
        fpr, tpr, _ = roc_curve(y, p_by_stage[stage])
        auc = roc_auc_score(y, p_by_stage[stage])
        ax.plot(fpr, tpr, color=STAGE_COLORS[stage], linewidth=2,
                label=f"Stage {stage}: {config.STAGE_NAMES[stage]} (AUC {auc:.3f})")
    ax.plot([0, 1], [0, 1], linestyle="--", color="#b5b4ae", linewidth=1, label="Coin flip")
    ax.axhline(config.SCREENING_RECALL, color=TEXT, linewidth=1, linestyle=":")
    ax.text(0.98, config.SCREENING_RECALL - 0.04, f"{config.SCREENING_RECALL:.0%} recall target",
            ha="right", color=TEXT, fontsize=9)
    ax.set_xlabel("False-alarm rate (1 - specificity)")
    ax.set_ylabel("Sick patients caught (recall)")
    ax.legend(frameon=False, loc="lower right", fontsize=8.5)
    ax.set_title("ROC curves of each stage's chosen model", fontweight="bold")
    _clean_axes(ax)
    _save(fig, "08_roc_by_stage.png")


def plot_policy_flow(y, p_by_stage, zones):
    decision, stopped_at = simulate_policy(p_by_stage, zones)
    n = len(y)
    fig, ax = plt.subplots(figsize=(9, 3.6))
    remaining = n
    for row, stage in enumerate(config.STAGES):
        here = stopped_at == stage
        cleared = int((here & (decision == 0)).sum())
        referred = int((here & (decision == 1)).sum())
        onward = remaining - cleared - referred
        left = 0
        for count, color in [(cleared, "#2a78d6"), (referred, "#eb6834"), (onward, "#d0cfca")]:
            if count:
                ax.barh(row, count, left=left, color=color, height=0.55,
                        edgecolor="white", linewidth=2)
                ax.text(left + count / 2, row, str(count), ha="center", va="center",
                        color="white" if color != "#d0cfca" else TEXT, fontweight="bold")
            left += count
        remaining = onward
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in ("#2a78d6", "#eb6834", "#d0cfca")]
    ax.legend(handles, ["Cleared (low risk)", "Referred (high risk)", "Needs next test"],
              frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3)
    ax.set_yticks(range(3), [f"Stage {s}: {config.STAGE_NAMES[s]}" for s in config.STAGES])
    ax.invert_yaxis()
    ax.set_xlim(0, n)
    ax.set_xlabel("")
    ax.set_title(f"Staged policy: where the {n} training patients stop", fontweight="bold")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    _save(fig, "09_staged_policy_flow.png")


# ----------------------------------------------------------------------------
# 4. Final models
# ----------------------------------------------------------------------------
def fit_final_model(name: str, stage: int, X, y):
    """Tune on ALL training patients and return the final fitted model."""
    if name != "ensemble":
        return grid_search(name, stage).fit(X, y).best_estimator_
    tuned = [(n, grid_search(n, stage).fit(X, y).best_estimator_) for n in MODEL_NAMES]
    # Soft voting = average the predicted probabilities, same as in CV.
    return VotingClassifier(tuned, voting="soft").fit(X, y)


def main():
    train, _sealed_test = split_cleveland(load_clean())
    y, oof, fold_auc = collect_out_of_fold(train)

    # Table of ROC-AUC per stage and candidate.
    auc_table = pd.DataFrame({
        (LABELS[m]): {f"stage_{s}": f"{np.mean(fold_auc[s][m]):.3f} ± {np.std(fold_auc[s][m]):.3f}"
                      for s in config.STAGES} for m in CANDIDATES}).T
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    auc_table.to_csv(config.REPORTS_DIR / "phase4_stage_auc.csv")
    print("\nROC-AUC by stage (mean ± std over 15 outer folds):\n", auc_table.to_string())

    # Pick each stage's model: highest mean outer-fold ROC-AUC.
    chosen = {s: max(CANDIDATES, key=lambda m: np.mean(fold_auc[s][m])) for s in config.STAGES}
    print("\nChosen model per stage:", {s: LABELS[m] for s, m in chosen.items()})

    # Each patient's unseen probability, averaged over the 3 repeats.
    p_by_stage = {s: oof[s][chosen[s]].mean(axis=0) for s in config.STAGES}
    zones = compute_zones(y, p_by_stage)
    strategies = compare_strategies(y, p_by_stage, zones)
    strategies.to_csv(config.REPORTS_DIR / "phase4_strategies.csv")
    print("\nZones:", json.dumps(zones, indent=1))
    cols = ["recall", "specificity", "precision", "npv", "fn", "fp",
            "needed_treadmill", "needed_invasive"]
    print("\nStrategy comparison (out-of-fold, 243 training patients):")
    print(strategies[cols].round(3).to_string())

    ci = bootstrap_strategies(y, p_by_stage, zones)
    ci.to_csv(config.REPORTS_DIR / "phase4_strategies_bootstrap.csv")
    print("\n95% bootstrap confidence intervals  (mean [low, high]):")
    print(ci.to_string())

    plot_auc_by_stage(fold_auc)
    plot_roc_by_stage(y, p_by_stage, chosen)
    plot_policy_flow(y, p_by_stage, zones)

    # Fit and save the final model for each stage, with its decision zones.
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for stage in config.STAGES:
        X, _ = get_features_and_target(train, stage)
        model = fit_final_model(chosen[stage], stage, X, y)
        joblib.dump({"model": model, "model_name": chosen[stage],
                     "features": config.STAGES[stage], "zones": zones[stage]},
                    config.MODELS_DIR / f"stage{stage}.joblib")
    # Out-of-fold predictions are reused by Phase 5 (calibration).
    joblib.dump({"y": y, "oof": oof, "fold_auc": fold_auc, "chosen": chosen},
                config.MODELS_DIR / "phase4_oof.joblib")
    with open(config.REPORTS_DIR / "phase4_zones.json", "w") as f:
        json.dump({"chosen": {str(s): m for s, m in chosen.items()},
                   "zones": {str(s): z for s, z in zones.items()}}, f, indent=2)
    print("saved final stage models to models/")


if __name__ == "__main__":
    main()
