"""
v2.0 stage 1: the check-up model, learned from all five hospitals.

Same recipe as v1 (Phases 4-5), with the pooled training set from
pooled.split_v2 and one change in how the model type is chosen:

  1. Candidates (logistic regression, random forest, XGBoost, ensemble) are
     compared by LEAVE-ONE-HOSPITAL-OUT ranking quality: each is trained
     without hospital H and tested on H, for every hospital. The winner is
     the best AVERAGE over hospitals, because v2's goal is to work at
     hospitals the model hasn't seen.
  2. Calibration (uncalibrated vs sigmoid) is chosen by Brier score on
     repeated out-of-fold predictions over the pooled training set.
  3. Decision zones (rule out at 99% recall, rule in at 90% precision) come
     from those pooled out-of-fold predictions.
  4. The final bundle (model, 20 range copies, unusual-patient detector,
     zones) is trained on all pooled training patients, in v1's format.

Stages 2-3 keep v1's Cleveland models (pooling showed no clear gain there).
v1's stage-1 bundle is kept as models/v1_stage1.joblib for comparison.

Run (~10 minutes):
    python -m cardiostage.v2_stage1
"""

import json
import shutil
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold

from cardiostage import config, integrity
from cardiostage.calibration import (
    VARIANTS,
    expected_calibration_error,
    make_variant,
    score_probabilities,
)
from cardiostage.models import MODEL_NAMES
from cardiostage.pooled import STAGE_HOSPITALS, load_pooled, split_v2
from cardiostage.staging import fit_final_model, grid_search, outer_cv
from cardiostage.thresholds import threshold_for_precision, threshold_for_recall
from cardiostage.uncertainty import NoveltyDetector, SubsampleEnsemble

STAGE = 1
CANDIDATES = MODEL_NAMES + ["ensemble"]
V2_OOF_PATH = config.MODELS_DIR / "v2_stage1_oof.joblib"
V1_BACKUP = config.MODELS_DIR / "v1_stage1.joblib"  # distinct name: the manifest keys by file name


def _candidate_predictions(train: pd.DataFrame, test: pd.DataFrame) -> dict:
    """Each candidate's predictions on `test` after tuning on `train` (inner CV)."""
    features = config.STAGES[STAGE]
    X, y = train[features], train[config.TARGET_COLUMN].to_numpy()
    preds = {
        n: grid_search(n, STAGE).fit(X, y).predict_proba(test[features])[:, 1] for n in MODEL_NAMES
    }
    preds["ensemble"] = np.mean([preds[n] for n in MODEL_NAMES], axis=0)
    return preds


def loho_candidates(train: pd.DataFrame) -> pd.DataFrame:
    """AUC of every candidate at every hospital it never saw (Cleveland: 5-fold within)."""
    hosp = train[config.HOSPITAL_COLUMN]
    rows = []
    for held_out in STAGE_HOSPITALS[STAGE]:
        target = train[hosp == held_out]
        y = target[config.TARGET_COLUMN].to_numpy()
        if held_out == config.TRAIN_HOSPITAL:
            preds = {c: np.zeros(len(y)) for c in CANDIDATES}
            others = train[hosp != held_out]
            folds = StratifiedKFold(config.CV_FOLDS, shuffle=True, random_state=config.RANDOM_SEED)
            for tr, te in folds.split(target, y):
                fold = _candidate_predictions(pd.concat([target.iloc[tr], others]), target.iloc[te])
                for c in CANDIDATES:
                    preds[c][te] = fold[c]
        else:
            preds = _candidate_predictions(train[hosp != held_out], target)
        for c in CANDIDATES:
            rows.append({"held_out": held_out, "candidate": c, "auc": roc_auc_score(y, preds[c])})
        print(
            f"  LOHO {held_out:13s} "
            + "  ".join(
                f"{c[:6]} {rows[-len(CANDIDATES) + i]['auc']:.3f}" for i, c in enumerate(CANDIDATES)
            ),
            flush=True,
        )
    return pd.DataFrame(rows)


def choose_candidate(table: pd.DataFrame) -> str:
    """Best average AUC over unseen hospitals."""
    return table.groupby("candidate")["auc"].mean().idxmax()


def oof_calibration(train: pd.DataFrame, name: str):
    """Repeated out-of-fold probabilities for both calibration variants (as v1 Phase 5)."""
    features = config.STAGES[STAGE]
    X, y = train[features], train[config.TARGET_COLUMN].to_numpy()
    oof = {v: np.full((config.CV_REPEATS, len(y)), np.nan) for v in VARIANTS}
    for i, (tr, te) in enumerate(outer_cv().split(X, y)):
        base = fit_final_model(name, STAGE, X.iloc[tr], y[tr])
        for v in VARIANTS:
            model = make_variant(base, v).fit(X.iloc[tr], y[tr])
            oof[v][i // config.CV_FOLDS, te] = model.predict_proba(X.iloc[te])[:, 1]
    return y, oof


def per_hospital_table(train: pd.DataFrame, y, p, zones) -> pd.DataFrame:
    """Out-of-fold quality and zone safety at each hospital (pooled model)."""
    rows = []
    for h in STAGE_HOSPITALS[STAGE]:
        m = (train[config.HOSPITAL_COLUMN] == h).to_numpy()
        yh, ph = y[m], p[m]
        cleared = ph < zones["rule_out_below"]
        rows.append(
            {
                "hospital": h,
                "n": int(m.sum()),
                "disease_rate": yh.mean(),
                "mean_predicted": ph.mean(),
                "auc": roc_auc_score(yh, ph),
                "ece": expected_calibration_error(yh, ph),
                "share_cleared": cleared.mean(),
                "cleared_but_sick": int((cleared & (yh == 1)).sum()),
                "share_referred": (ph >= zones["rule_in_from"]).mean(),
            }
        )
    return pd.DataFrame(rows)


def main():
    t0 = time.time()
    train, _sealed = split_v2(load_pooled())  # the sealed test is NOT used here
    train = train[train[config.HOSPITAL_COLUMN].isin(STAGE_HOSPITALS[STAGE])]
    print(
        f"v2 stage 1: {len(train)} training patients from {train[config.HOSPITAL_COLUMN].nunique()} hospitals"
    )

    print("1. Leave-one-hospital-out model choice", flush=True)
    loho = loho_candidates(train)
    name = choose_candidate(loho)
    loho.to_csv(config.REPORTS_DIR / "v2_stage1_candidates.csv", index=False)
    print(
        f"   chosen: {name} (mean unseen-hospital AUC "
        f"{loho.groupby('candidate')['auc'].mean()[name]:.3f})",
        flush=True,
    )

    print("2. Calibration (repeated out-of-fold over the pooled set)", flush=True)
    y, oof = oof_calibration(train, name)
    briers = {
        v: score_probabilities(np.tile(y, config.CV_REPEATS), oof[v].ravel())["brier"]
        for v in VARIANTS
    }
    method = min(briers, key=briers.get)
    p = oof[method].mean(axis=0)
    print(f"   Brier {briers} -> {method}", flush=True)

    print("3. Decision zones", flush=True)
    zones = {
        "rule_out_below": threshold_for_recall(y, p, config.RULE_OUT_RECALL),
        "rule_in_from": threshold_for_precision(y, p, config.RULE_IN_PRECISION),
    }
    table = per_hospital_table(train, y, p, zones)
    table.to_csv(config.REPORTS_DIR / "v2_stage1_by_hospital.csv", index=False)
    (config.REPORTS_DIR / "v2_stage1_zones.json").write_text(
        json.dumps({"chosen": name, "calibration": method, "zones": zones}, indent=2),
        encoding="utf-8",
    )
    print(f"   zones {zones}\n{table.round(3).to_string(index=False)}", flush=True)

    print("4. Final bundle (all pooled training patients)", flush=True)
    X = train[config.STAGES[STAGE]]
    base = fit_final_model(name, STAGE, X, y)
    bundle = {
        "model": make_variant(base, method).fit(X, y),
        "uncertainty": SubsampleEnsemble(make_variant(base, method)).fit(X, y),
        "novelty": NoveltyDetector(STAGE).fit(X),
        "model_name": name,
        "calibration": method,
        "features": config.STAGES[STAGE],
        "zones": zones,
        "version": "v2",
        "trained_on": sorted(train[config.HOSPITAL_COLUMN].unique()),
    }
    current = config.MODELS_DIR / "stage1.joblib"
    if not V1_BACKUP.exists():  # keep v1's stage 1 once, for comparisons
        V1_BACKUP.parent.mkdir(parents=True, exist_ok=True)
        integrity.verify(current)
        shutil.copy2(current, V1_BACKUP)
    joblib.dump(bundle, current)
    joblib.dump(
        {
            "y": y,
            "oof": oof,
            "method": method,
            "hospital": train[config.HOSPITAL_COLUMN].to_numpy(),
        },
        V2_OOF_PATH,
    )
    integrity.write_manifest(integrity.stage_bundle_paths())
    print(
        f"saved v2 stage 1 to {current.name} (v1 kept at models/v1_stage1.joblib); "
        f"manifest updated; {time.time() - t0:.0f}s total"
    )


if __name__ == "__main__":
    main()
