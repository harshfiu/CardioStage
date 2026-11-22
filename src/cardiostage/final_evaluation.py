"""
Phase 9: the final exam. Opening the sealed test set.

Since Phase 3, 61 Cleveland patients have been locked away. Every model,
hyperparameter, calibration method, threshold and design decision was made
WITHOUT them. Here they're used exactly once, with the final models and the
frozen decision zones, to give an unbiased estimate of real performance.

Rules of a sealed test:
  - nothing is tuned or changed after seeing these results,
  - results are reported as they are, good or bad, with confidence intervals
    (61 patients is small, so the intervals will be wide).

Run:  python -m cardiostage.final_evaluation
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

from cardiostage import config, integrity
from cardiostage.calibration import expected_calibration_error
from cardiostage.data import get_features_and_target, load_clean, split_cleveland
from cardiostage.external_validation import internal_reference
from cardiostage.staging import simulate_policy
from cardiostage.stats import bootstrap_ci, exact_proportion_ci, fmt_ci
from cardiostage.thresholds import decision_metrics

TEXT = "#52514e"


def main():
    train, test = split_cleveland(load_clean())
    bundles = {s: integrity.load(config.MODELS_DIR / f"stage{s}.joblib") for s in config.STAGES}
    y = test[config.TARGET_COLUMN].to_numpy()
    print(
        f"Sealed test set: {len(y)} patients, {int(y.sum())} with heart disease ({y.mean():.0%})\n"
    )

    # ---- 1. Each stage model on its own -----------------------------------------
    y_int, p_int, stage_thresholds = internal_reference()
    p = {}
    stage_rows = []
    for s in config.STAGES:
        X, _ = get_features_and_target(test, s)
        p[s] = bundles[s]["model"].predict_proba(X)[:, 1]
        auc = bootstrap_ci(roc_auc_score, y, p[s], need_both_classes=True)
        cv_auc = roc_auc_score(y_int, p_int[s])
        stage_rows.append(
            {
                "stage": s,
                "name": config.STAGE_NAMES[s],
                "test_roc_auc": fmt_ci(*auc),
                "cv_roc_auc": round(cv_auc, 3),
                "test_brier": round(brier_score_loss(y, p[s]), 4),
                "test_ece_5bins": round(expected_calibration_error(y, p[s], n_bins=5), 3),
                "mean_predicted": round(p[s].mean(), 3),
                "actual_rate": round(y.mean(), 3),
                "_auc": auc,
                "_cv": cv_auc,
            }
        )
    stages = pd.DataFrame(stage_rows)
    public = [c for c in stages.columns if not c.startswith("_")]
    stages[public].to_csv(config.REPORTS_DIR / "final_test_stages.csv", index=False)
    pd.set_option("display.width", 250, "display.max_columns", 30)
    print("Stage models on the sealed test set (CV = earlier out-of-fold estimate):")
    print(stages[public].to_string(index=False))

    # ---- 2. Strategies with the FROZEN thresholds -------------------------------
    zones = {s: bundles[s]["zones"] for s in config.STAGES}
    decision, reached = simulate_policy(p, zones)
    strategies = {
        f"Everyone: stage {s} only": ((p[s] >= stage_thresholds[s]).astype(int), np.full(len(y), s))
        for s in config.STAGES
    }
    strategies["CardioStage staged policy"] = (decision, reached)

    rows = {}
    for name, (d, r) in strategies.items():
        m = decision_metrics(y, d)
        # Exact intervals for proportions: the bootstrap collapses to [1, 1]
        # when nothing is missed (see stats.exact_proportion_ci).
        rows[name] = {
            "recall": fmt_ci(*exact_proportion_ci(m["tp"], m["tp"] + m["fn"])),
            "specificity": fmt_ci(*exact_proportion_ci(m["tn"], m["tn"] + m["fp"])),
            "sick_missed": m["fn"],
            "healthy_flagged": m["fp"],
            "needed_treadmill": (r >= 2).mean(),
            "needed_invasive": (r == 3).mean(),
        }
    strat_table = pd.DataFrame(rows).T
    strat_table.to_csv(config.REPORTS_DIR / "final_test_strategies.csv")
    print("\nDecision strategies on the sealed test set (thresholds frozen from training):")
    print(strat_table.to_string())

    # Where did each test patient stop?
    flow = pd.crosstab(
        pd.Series(reached, name="stopped_at_stage"),
        pd.Series(np.where(decision == 1, "referred", "cleared"), name="decision"),
    )
    print("\nWhere the 61 test patients stopped:\n", flow)
    missed = test[(decision == 0) & (y == 1)]
    if len(missed):
        cols = ["age", "sex", "cp", "trestbps", "chol", "thalch", "exang", "oldpeak", "ca", "thal"]
        print(
            "\nMissed sick patients:\n",
            missed[cols].assign(stopped=reached[(decision == 0) & (y == 1)]).to_string(),
        )

    plot_test_vs_cv(stages)


def plot_test_vs_cv(stages: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(8, 3.8))
    for i, row in stages.iterrows():
        s = row["stage"]
        est, lo, hi = row["_auc"]
        ax.errorbar(
            s + 0.08,
            est,
            yerr=[[est - lo], [hi - est]],
            fmt="o",
            color="#2a78d6",
            markersize=9,
            capsize=4,
            linewidth=2,
            label="Sealed test set (61 patients, 95% CI)" if i == 0 else None,
        )
        ax.plot(
            s - 0.08,
            row["_cv"],
            "D",
            color="#eb6834",
            markersize=8,
            label="Cross-validation estimate (243 patients)" if i == 0 else None,
        )
        ax.text(s + 0.16, est, f"{est:.3f}", va="center", color=TEXT, fontsize=9)
    ax.set_xticks(
        list(config.STAGES), [f"Stage {s}\n{config.STAGE_NAMES[s]}" for s in config.STAGES]
    )
    ax.set_xlim(0.5, 3.6)
    ax.set_ylim(0.6, 1.02)
    ax.set_ylabel("ROC-AUC")
    ax.legend(frameon=False, loc="lower right", fontsize=9)
    ax.set_title("Final exam: sealed test set vs earlier estimates", fontweight="bold")
    ax.grid(axis="y", color="#ebeae6")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    path = config.FIGURES_DIR / "18_final_test.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\nsaved {path.relative_to(config.PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
