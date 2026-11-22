"""
Phase 3: compare Logistic Regression, Random Forest and XGBoost.

Uses ALL 13 features (Stage 3) to find out how well each model type can do
with full information. Phase 4 then repeats this per stage.

Method: NESTED cross-validation on the Cleveland training set.

    OUTER loop (grading):  split training data into 5 folds. For each fold:
        INNER loop (tuning): on the other 4 folds, run a grid search with its
                             own 5-fold CV to pick the best hyperparameters.
        Grade the chosen model on the held-out outer fold it never saw.
    Repeat the outer loop 3 times with different shuffles -> 15 grades.

Why nested? If we tuned AND graded on the same folds, the winning settings
would partly be chosen *because* they happened to suit those folds, and the
score would be optimistic. Nested CV keeps grading data out of tuning.

The sealed Cleveland test set is NOT used here. It is opened once, at the
end of the project, to report final results.

Run:  python -m cardiostage.train_baselines
"""

import time

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.model_selection import (
    GridSearchCV,
    RepeatedStratifiedKFold,
    StratifiedKFold,
    cross_validate,
)

from cardiostage import config
from cardiostage.data import get_features_and_target, load_clean, split_cleveland
from cardiostage.models import MODEL_LABELS, MODEL_NAMES, PARAM_GRIDS, build_pipeline

STAGE = 3  # all features

# What we measure on every outer fold (names are scikit-learn's built-ins).
#   roc_auc   : how well the model RANKS sick patients above healthy ones,
#               across every possible threshold (1.0 perfect, 0.5 = coin flip)
#   recall    : of the truly sick, what fraction did we catch?
#   precision : of those we flagged as sick, what fraction really were?
#   accuracy  : fraction of all predictions that were right
#   f1        : a single balance of precision and recall
SCORING = ["roc_auc", "recall", "precision", "accuracy", "f1"]

MODEL_COLORS = {
    "logistic_regression": "#2a78d6",
    "random_forest": "#eb6834",
    "xgboost": "#1baf7a",
}


def make_grid_search(name: str) -> GridSearchCV:
    """Inner loop: tune one model type's hyperparameters by 5-fold CV."""
    return GridSearchCV(
        estimator=build_pipeline(name, STAGE),
        param_grid=PARAM_GRIDS[name],
        scoring="roc_auc",  # pick the settings that rank best
        cv=StratifiedKFold(n_splits=config.CV_FOLDS, shuffle=True, random_state=config.RANDOM_SEED),
        n_jobs=-1,  # use all CPU cores
    )


def nested_cv(name: str, X: pd.DataFrame, y: pd.Series) -> dict:
    """Outer loop: grade the whole 'tune-then-train' procedure honestly."""
    outer_cv = RepeatedStratifiedKFold(
        n_splits=config.CV_FOLDS, n_repeats=config.CV_REPEATS, random_state=config.RANDOM_SEED
    )
    results = cross_validate(
        make_grid_search(name), X, y, cv=outer_cv, scoring=SCORING, return_estimator=True
    )
    # Which settings did the inner search pick on each outer fold?
    # If they vary wildly, the choice of settings is fragile.
    chosen = [str(est.best_params_) for est in results["estimator"]]
    return {"scores": {m: results[f"test_{m}"] for m in SCORING}, "chosen": chosen}


def plot_comparison(summary: pd.DataFrame) -> None:
    """One panel per metric; dot = mean over 15 outer folds, bar = ±1 std."""
    metrics = ["roc_auc", "recall", "precision", "accuracy"]
    titles = {
        "roc_auc": "ROC-AUC",
        "recall": "Recall (sick caught)",
        "precision": "Precision (alarms correct)",
        "accuracy": "Accuracy",
    }
    fig, axes = plt.subplots(1, len(metrics), figsize=(15, 3.4), sharey=True)
    names = list(summary.index)
    for ax, metric in zip(axes, metrics):
        for i, name in enumerate(names):
            mean, std = summary.loc[name, f"{metric}_mean"], summary.loc[name, f"{metric}_std"]
            ax.errorbar(
                mean,
                i,
                xerr=std,
                fmt="o",
                color=MODEL_COLORS[name],
                markersize=9,
                capsize=4,
                linewidth=2,
            )
            ax.text(mean, i - 0.28, f"{mean:.3f}", ha="center", color="#52514e", fontsize=9)
        ax.set_title(titles[metric], fontweight="bold")
        ax.set_xlim(0.6, 1.0)
        ax.grid(axis="x", color="#ebeae6")
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[0].set_yticks(range(len(names)), [MODEL_LABELS[n] for n in names])
    axes[0].set_ylim(len(names) - 0.5, -0.7)
    fig.suptitle(
        "Model comparison: nested cross-validation on Cleveland (all features)\n"
        "dot = mean of 15 outer folds, bar = ±1 standard deviation",
        fontweight="bold",
        y=1.08,
    )
    config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = config.FIGURES_DIR / "05_model_comparison.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {path.relative_to(config.PROJECT_ROOT)}")


def main():
    train, _sealed_test = split_cleveland(load_clean())
    X, y = get_features_and_target(train, STAGE)
    print(f"Training patients: {len(X)}  (disease rate {y.mean():.0%})\n")

    rows, chosen_params = {}, {}
    for name in MODEL_NAMES:
        start = time.time()
        result = nested_cv(name, X, y)
        rows[name] = {
            f"{m}_{stat}": getattr(np, stat)(v)
            for m, v in result["scores"].items()
            for stat in ("mean", "std")
        }
        chosen_params[name] = pd.Series(result["chosen"]).value_counts()
        print(
            f"{MODEL_LABELS[name]:<20} ROC-AUC {rows[name]['roc_auc_mean']:.3f} "
            f"± {rows[name]['roc_auc_std']:.3f}   ({time.time() - start:.0f}s)"
        )

        # Final version of this model: tune on ALL training data and save it.
        final = make_grid_search(name).fit(X, y)
        config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(final.best_estimator_, config.MODELS_DIR / f"phase3_{name}.joblib")
        print(f"{'':<20} final settings: {final.best_params_}")

    summary = pd.DataFrame(rows).T
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    summary.round(4).to_csv(config.REPORTS_DIR / "phase3_model_comparison.csv")
    print("\n", summary[[c for c in summary.columns if c.endswith("_mean")]].round(3))
    print("\nHow often each setting was chosen across the 15 outer folds:")
    for name, counts in chosen_params.items():
        print(f"\n{MODEL_LABELS[name]}:\n{counts.to_string()}")
    plot_comparison(summary)


if __name__ == "__main__":
    main()
