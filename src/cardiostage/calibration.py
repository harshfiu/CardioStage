"""
Phase 5: honest probabilities and "not sure" answers.

Part A, calibration. A model is CALIBRATED if, among all patients it gives
"30% risk", about 30% really have the disease. Ranking (ROC-AUC) and
calibration are different things: a model can rank perfectly yet say 90%
when the truth is 60%. Patients and doctors read the NUMBER, so it must be
honest.

For each stage's model (chosen in Phase 4) we compare, inside the usual
nested cross-validation:
    uncalibrated  vs  sigmoid (Platt) calibration  vs  isotonic calibration
and keep the method with the lowest Brier score.

Part B, uncertainty. Using the calibrated models we test whether the
"not confident" flag (copies of the model disagreeing across a threshold)
really identifies predictions that are more often wrong.

Run:  python -m cardiostage.calibration     (~5-8 minutes)
"""

import json
import time

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold

from cardiostage import config, integrity
from cardiostage.data import get_features_and_target, load_clean, split_cleveland
from cardiostage.staging import (
    bootstrap_strategies,
    compare_strategies,
    compute_zones,
    fit_final_model,
    outer_cv,
)
from cardiostage.thresholds import decision_metrics
from cardiostage.uncertainty import NoveltyDetector, SubsampleEnsemble, straddles

VARIANTS = ["uncalibrated"] + config.CALIBRATION_METHODS
VARIANT_COLORS = {"uncalibrated": "#eb6834", "sigmoid": "#2a78d6", "isotonic": "#1baf7a"}
TEXT = "#52514e"


# ----------------------------------------------------------------------------
# Calibration building blocks
# ----------------------------------------------------------------------------
def make_variant(base, variant: str):
    """
    Wrap an (already tuned) model in a calibrator.

    CalibratedClassifierCV splits the training data into 5 folds; for each,
    it trains the model on 4 folds and learns the probability correction on
    the 5th, the patients that copy didn't see. (Learning the correction on
    the model's own training patients would be useless: it is overconfident
    exactly on those.) The 5 calibrated copies are averaged.
    """
    if variant == "uncalibrated":
        return clone(base)
    return CalibratedClassifierCV(
        clone(base),
        method=variant,
        cv=StratifiedKFold(config.CV_FOLDS, shuffle=True, random_state=config.RANDOM_SEED),
    )


def expected_calibration_error(y, p, n_bins: int = 10) -> float:
    """
    ECE: group patients into bins by predicted probability (equal-sized
    groups), compare each bin's average prediction with its actual disease
    rate, and average the gaps (weighted by bin size).
    ECE = 0.05 means predictions are off by ~5 percentage points on average.
    """
    y, p = np.asarray(y), np.asarray(p)
    edges = np.quantile(p, np.linspace(0, 1, n_bins + 1))
    bins = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, n_bins - 1)
    ece = 0.0
    for b in range(n_bins):
        in_bin = bins == b
        if in_bin.any():
            ece += in_bin.mean() * abs(p[in_bin].mean() - y[in_bin].mean())
    return float(ece)


def score_probabilities(y, p) -> dict:
    """
    brier    : mean squared gap between probability and outcome (0/1).
               Rewards being both accurate AND honest. Lower is better.
    log_loss : like Brier, but punishes confident mistakes much harder.
    ece      : calibration gap (see above).
    roc_auc  : ranking quality, to check calibration didn't hurt it.
    """
    return {
        "brier": brier_score_loss(y, p),
        "log_loss": log_loss(y, p),
        "ece": expected_calibration_error(y, p),
        "roc_auc": roc_auc_score(y, p),
    }


# ----------------------------------------------------------------------------
# Cross-validated experiment
# ----------------------------------------------------------------------------
def collect_calibration(train, chosen):
    """Out-of-fold probabilities for every stage and calibration variant."""
    y = train[config.TARGET_COLUMN].to_numpy()
    shape = (config.CV_REPEATS, len(y))
    oof = {s: {v: np.full(shape, np.nan) for v in VARIANTS} for s in config.STAGES}
    scores = {s: {v: [] for v in VARIANTS} for s in config.STAGES}
    tuned = {s: [] for s in config.STAGES}  # reused by the uncertainty pass

    for stage in config.STAGES:
        X, _ = get_features_and_target(train, stage)
        start = time.time()
        for i, (tr, te) in enumerate(outer_cv().split(X, y)):
            repeat = i // config.CV_FOLDS
            # Tune on the outer-training part only (inner grid search).
            base = fit_final_model(chosen[stage], stage, X.iloc[tr], y[tr])
            tuned[stage].append((tr, te, base))
            for variant in VARIANTS:
                model = make_variant(base, variant).fit(X.iloc[tr], y[tr])
                p = model.predict_proba(X.iloc[te])[:, 1]
                oof[stage][variant][repeat, te] = p
                scores[stage][variant].append(score_probabilities(y[te], p))
        print(f"Stage {stage}: calibration done in {time.time() - start:.0f}s")
    return y, oof, scores, tuned


def collect_uncertainty(train, method, tuned):
    """Per-patient uncertainty ranges from models that never saw the patient."""
    y = train[config.TARGET_COLUMN].to_numpy()
    shape = (config.CV_REPEATS, len(y))
    low = {s: np.full(shape, np.nan) for s in config.STAGES}
    high = {s: np.full(shape, np.nan) for s in config.STAGES}
    for stage in config.STAGES:
        X, _ = get_features_and_target(train, stage)
        start = time.time()
        for i, (tr, te, base) in enumerate(tuned[stage]):
            repeat = i // config.CV_FOLDS
            ens = SubsampleEnsemble(make_variant(base, method[stage])).fit(X.iloc[tr], y[tr])
            low[stage][repeat, te], high[stage][repeat, te] = ens.predict_interval(X.iloc[te])
        print(f"Stage {stage}: uncertainty done in {time.time() - start:.0f}s")
    return low, high


OUTCOMES = [
    "Missed sick (FN)",
    "False alarm (FP)",
    "Correctly referred (TP)",
    "Correctly cleared (TN)",
]


def evaluate_not_confident(y, p3, low3, high3, threshold) -> pd.DataFrame:
    """
    Does the flag work? At the final (stage 3) decision, split patients by
    outcome and ask how often each group was flagged "not confident".

    A useful flag would fire often on MISSED SICK patients (the dangerous
    error) and rarely on correct decisions. Plain "error rate" would be
    misleading here: at a 97%-recall threshold most errors are deliberate
    false alarms, which the threshold accepts by design.
    Pooled over the 3 repeats (each patient counted once per repeat).
    """
    y_all = np.tile(y, config.CV_REPEATS)
    decision = p3.ravel() >= threshold
    flagged = straddles(low3.ravel(), high3.ravel(), threshold)
    masks = {
        "Missed sick (FN)": (y_all == 1) & ~decision,
        "False alarm (FP)": (y_all == 0) & decision,
        "Correctly referred (TP)": (y_all == 1) & decision,
        "Correctly cleared (TN)": (y_all == 0) & ~decision,
    }
    return pd.DataFrame(
        {
            name: {
                "n": int(m.sum()),
                "flagged": int(flagged[m].sum()),
                "share_flagged": flagged[m].mean() if m.any() else np.nan,
            }
            for name, m in masks.items()
        }
    ).T


def simulate_guarded_policy(p_by_stage, low_by_stage, high_by_stage, zones):
    """
    The staged policy, but only clear or refer early when ALL model copies
    agree (the whole uncertainty range lies inside the zone). Otherwise the
    patient gets the next test. Safer, at the cost of a few more tests.
    """
    n = len(p_by_stage[1])
    decision, stopped_at = np.full(n, -1), np.zeros(n, dtype=int)
    for stage in (1, 2):
        z = zones[stage]
        undecided = decision == -1
        high = undecided & (low_by_stage[stage] >= z["rule_in_from"])
        low = undecided & ~high & (high_by_stage[stage] < z["rule_out_below"])
        decision[high], decision[low] = 1, 0
        stopped_at[high | low] = stage
    undecided = decision == -1
    decision[undecided] = (p_by_stage[3][undecided] >= zones[3]["screening_threshold"]).astype(int)
    stopped_at[undecided] = 3
    return decision, stopped_at


# ----------------------------------------------------------------------------
# Charts
# ----------------------------------------------------------------------------
def _reliability(y, p, n_bins=8):
    edges = np.quantile(p, np.linspace(0, 1, n_bins + 1))
    bins = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, n_bins - 1)
    return (
        np.array([p[bins == b].mean() for b in range(n_bins) if (bins == b).any()]),
        np.array([y[bins == b].mean() for b in range(n_bins) if (bins == b).any()]),
    )


def plot_calibration(y, oof, method):
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.6), sharey=True)
    y_rep = np.tile(y, config.CV_REPEATS)
    for ax, stage in zip(axes, config.STAGES):
        ax.plot(
            [0, 1], [0, 1], linestyle="--", color="#b5b4ae", linewidth=1, label="Perfectly honest"
        )
        for variant in ("uncalibrated", "sigmoid"):
            p = oof[stage][variant].ravel()
            mean_pred, frac_sick = _reliability(y_rep, p)
            ece = expected_calibration_error(y_rep, p)
            chosen_mark = "  ✓ chosen" if variant == method[stage] else ""
            ax.plot(
                mean_pred,
                frac_sick,
                "o-",
                color=VARIANT_COLORS[variant],
                linewidth=2,
                markersize=7,
                label=f"{variant} (ECE {ece:.3f}){chosen_mark}",
            )
        ax.set_title(f"Stage {stage}: {config.STAGE_NAMES[stage]}", fontweight="bold")
        ax.set_xlabel("Predicted risk")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.legend(frameon=False, loc="upper left", fontsize=9)
        ax.grid(color="#ebeae6")
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[0].set_ylabel("Actual share with heart disease")
    fig.suptitle(
        "Calibration: does predicted risk match reality?  (out-of-fold, 243 patients x 3 repeats)",
        fontweight="bold",
        y=1.03,
    )
    path = config.FIGURES_DIR / "10_calibration_curves.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {path.relative_to(config.PROJECT_ROOT)}")


def plot_not_confident(table: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(8, 3.2))
    bars = ax.barh(table.index, table["share_flagged"] * 100, color="#2a78d6", height=0.5)
    for bar, (_, row) in zip(bars, table.iterrows()):
        ax.text(
            bar.get_width() + 0.8,
            bar.get_y() + bar.get_height() / 2,
            f"{row.share_flagged:.0%}  ({int(row.flagged)} of {int(row.n)})",
            va="center",
            color=TEXT,
        )
    ax.set_xlim(0, max(table["share_flagged"]) * 100 * 1.6)
    ax.set_xlabel("Share flagged 'not confident' (%)")
    ax.invert_yaxis()
    ax.set_title(
        "Model-disagreement flag at the final decision: a weak signal on this data",
        fontweight="bold",
    )
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    path = config.FIGURES_DIR / "11_not_confident_errors.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {path.relative_to(config.PROJECT_ROOT)}")


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def pooled_scores(y, oof) -> pd.DataFrame:
    """
    Score each stage/variant on ALL out-of-fold predictions pooled together
    (243 patients x 3 repeats = 729 per stage). Per-fold ECE is unreliable:
    ~49 patients split into 10 bins leaves ~5 per bin, so random noise alone
    produces gaps of 0.1+. Pooling gives ~73 per bin.
    """
    y_all = np.tile(y, config.CV_REPEATS)
    return pd.DataFrame(
        [
            {
                "stage": s,
                "variant": v,
                **{
                    k: round(val, 4)
                    for k, val in score_probabilities(y_all, oof[s][v].ravel()).items()
                },
            }
            for s in config.STAGES
            for v in VARIANTS
        ]
    )


def choose_methods(cal_table: pd.DataFrame) -> dict:
    """Per stage, the variant with the lowest Brier score."""
    best = cal_table.loc[cal_table.groupby("stage")["brier"].idxmin()]
    return dict(zip(best["stage"], best["variant"]))


def report(train, df, y, oof, low, high, method, chosen):
    """All Phase 5 tables and charts, from saved out-of-fold predictions."""
    cal_table = pooled_scores(y, oof)
    cal_table.to_csv(config.REPORTS_DIR / "phase5_calibration.csv", index=False)
    print("\nPooled out-of-fold scores:\n", cal_table.to_string(index=False))
    print("\nChosen calibration per stage:", method)

    p_by_stage = {s: oof[s][method[s]].mean(axis=0) for s in config.STAGES}
    zones = compute_zones(y, p_by_stage)
    strategies = compare_strategies(y, p_by_stage, zones)
    print("\nCalibrated zones:", json.dumps(zones, indent=1))
    cols = ["recall", "specificity", "fn", "fp", "needed_treadmill", "needed_invasive"]

    low_mean = {s: low[s].mean(axis=0) for s in config.STAGES}
    high_mean = {s: high[s].mean(axis=0) for s in config.STAGES}
    nc = evaluate_not_confident(
        y, oof[3][method[3]], low[3], high[3], zones[3]["screening_threshold"]
    )
    nc.to_csv(config.REPORTS_DIR / "phase5_not_confident.csv")
    print(
        "\nStage-3 decision, share flagged 'not confident' by outcome:\n", nc.round(3).to_string()
    )
    widths = (high[3] - low[3]).ravel()
    print(f"Median uncertainty range at stage 3: {np.median(widths):.3f}")

    guarded_decision, guarded_stop = simulate_guarded_policy(p_by_stage, low_mean, high_mean, zones)
    g = decision_metrics(y, guarded_decision)
    g["needed_treadmill"] = float((guarded_stop >= 2).mean())
    g["needed_invasive"] = float((guarded_stop == 3).mean())
    strategies.loc["Staged + uncertainty guard"] = pd.Series(g)
    strategies.to_csv(config.REPORTS_DIR / "phase5_strategies.csv")
    print("\nStrategies with calibrated probabilities:\n", strategies[cols].round(3).to_string())
    ci = bootstrap_strategies(y, p_by_stage, zones)
    ci.to_csv(config.REPORTS_DIR / "phase5_strategies_bootstrap.csv")
    print("\n95% bootstrap CIs:\n", ci.to_string())

    # ---- C. Unusual-patient detector -------------------------------------------
    novelty_rows = {}
    for stage in config.STAGES:
        X_train, _ = get_features_and_target(train, stage)
        detector = NoveltyDetector(stage).fit(X_train)
        novelty_rows[f"stage_{stage}"] = {
            "Cleveland (training)": detector.is_unusual(X_train).mean()
        }
        for hospital in config.EXTERNAL_HOSPITALS:
            X_h, _ = get_features_and_target(df[df[config.HOSPITAL_COLUMN] == hospital], stage)
            novelty_rows[f"stage_{stage}"][hospital] = detector.is_unusual(X_h).mean()
    novelty = pd.DataFrame(novelty_rows)
    novelty.to_csv(config.REPORTS_DIR / "phase5_unusual_rates.csv")
    print("\nShare of patients flagged unusual:\n", novelty.round(3).to_string())

    plot_calibration(y, oof, method)
    plot_not_confident(nc)
    with open(config.REPORTS_DIR / "phase5_zones.json", "w") as f:
        json.dump(
            {
                "chosen": {str(s): m for s, m in chosen.items()},
                "calibration": {str(s): m for s, m in method.items()},
                "zones": {str(s): z for s, z in zones.items()},
            },
            f,
            indent=2,
        )
    return zones


def main(report_only: bool = False):
    df = load_clean()
    train, _sealed_test = split_cleveland(df)
    with open(config.REPORTS_DIR / "phase4_zones.json") as f:
        chosen = {int(s): m for s, m in json.load(f)["chosen"].items()}

    if report_only:  # regenerate tables/charts without retraining
        saved = integrity.load(config.MODELS_DIR / "phase5_oof.joblib")
        report(
            train,
            df,
            saved["y"],
            saved["oof"],
            saved["low"],
            saved["high"],
            saved["method"],
            chosen,
        )
        return

    # A. calibration variants, B. uncertainty ranges (both out-of-fold)
    y, oof, _fold_scores, tuned = collect_calibration(train, chosen)
    method = choose_methods(pooled_scores(y, oof))
    low, high = collect_uncertainty(train, method, tuned)
    joblib.dump(
        {"y": y, "oof": oof, "method": method, "low": low, "high": high},
        config.MODELS_DIR / "phase5_oof.joblib",
    )
    zones = report(train, df, y, oof, low, high, method, chosen)

    # D. final models, trained on all 243 training patients
    for stage in config.STAGES:
        X, _ = get_features_and_target(train, stage)
        base = fit_final_model(chosen[stage], stage, X, y)
        bundle = {
            "model": make_variant(base, method[stage]).fit(X, y),
            "uncertainty": SubsampleEnsemble(make_variant(base, method[stage])).fit(X, y),
            "novelty": NoveltyDetector(stage).fit(X),
            "model_name": chosen[stage],
            "calibration": method[stage],
            "features": config.STAGES[stage],
            "zones": zones[stage],
        }
        joblib.dump(bundle, config.MODELS_DIR / f"stage{stage}.joblib")
    # Record each bundle's SHA-256 so the app can refuse tampered files (SEC-05).
    integrity.write_manifest(integrity.stage_bundle_paths())
    print("saved calibrated stage models (with uncertainty + novelty detectors) to models/")
    print(f"wrote integrity manifest {integrity.MANIFEST_PATH.name}")


if __name__ == "__main__":
    import sys

    main(report_only="--report-only" in sys.argv)
