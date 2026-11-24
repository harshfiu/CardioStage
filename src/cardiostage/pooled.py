"""
v2.0 data: all five hospitals pooled, a new sealed test set, and the
"leave-one-hospital-out" experiment that decides whether pooling helps.

Why: v1 learned from Cleveland only and failed on modern Iranian patients
(stage-1 AUC 0.68, recall 0.68; see external_iran.py). v2 learns from every
hospital that has each stage's measurements:

    stage 1 (check-up)   Cleveland, Hungary, Switzerland, VA Long Beach, Iran
    stage 2 (treadmill)  Cleveland, Hungary, Switzerland, VA Long Beach
                         (Iran has no exercise test)
    stage 3 (imaging)    Cleveland (other hospitals are 90-99% missing)

Sealed test (v2): Cleveland keeps v1's 61 test patients (v2 reuses v1's
stage-2/3 models, trained on the other 243, so a new Cleveland split would
leak); every other hospital contributes a fresh 20%, stratified by outcome.
Opened once, at the very end.

Leave-one-hospital-out (LOHO): for each hospital H, train without H and test
on H. That's the honest answer to "how will this do at a hospital it has
never seen?". It compares two training strategies on equal footing:
    cleveland_only  train on Cleveland only (the v1 approach)
    pooled          train on every other hospital with that stage's data
When H is Cleveland itself, both use 5-fold cross-validation within
Cleveland (pooled adds all the other hospitals to every training fold).

Run:
    python -m cardiostage.pooled            # LOHO experiment -> reports/v2_loho.csv
"""

import time

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, train_test_split

from cardiostage import config
from cardiostage.calibration import expected_calibration_error
from cardiostage.data import load_clean, split_cleveland
from cardiostage.external_iran import load_iran, to_cardiostage
from cardiostage.models import MODEL_NAMES
from cardiostage.staging import grid_search
from cardiostage.stats import bootstrap_ci, fmt_ci

HOSPITALS = ["Cleveland", "Hungary", "Switzerland", "VA Long Beach", "Iran"]
STAGE_HOSPITALS = {
    1: HOSPITALS,
    2: ["Cleveland", "Hungary", "Switzerland", "VA Long Beach"],
    3: ["Cleveland"],
}
TEST_SIZE_V2 = 0.2


def load_pooled() -> pd.DataFrame:
    """The four UCI hospitals (cleaned) plus the Iranian cohort, in one table."""
    uci = load_clean()
    iran = to_cardiostage(load_iran())
    iran[config.HOSPITAL_COLUMN] = "Iran"
    # Iran's cholesterol was never measured directly: it's ESTIMATED from LDL,
    # HDL and triglycerides, in a modern population (lipid-lowering drugs are
    # common). Its median (~170) is far below the 1980s hospitals (~240) while
    # its disease rate is high, so pooling taught a false "lower cholesterol =
    # more risk" rule (coefficient -0.06; v1 +0.22). Treated as not measured,
    # the model learns cholesterol only where it was measured (+0.14), with
    # equal or better unseen-hospital ranking (reports/v2_cholesterol_check.csv).
    iran["chol"] = float("nan")
    keep = config.STAGES[3] + [config.TARGET_COLUMN, config.HOSPITAL_COLUMN]
    return pd.concat([uci[keep], iran[keep]], ignore_index=True)


def split_v2(df: pd.DataFrame):
    """
    (train, sealed_test) for v2.

    Cleveland keeps EXACTLY v1's split (243 train / 61 test): v2 reuses v1's
    stage-2/3 models, which trained on those 243, so any other Cleveland split
    would put their training patients into the test set (leakage). Every other
    hospital: a fresh 20%, stratified by outcome.
    """
    cle = df[df[config.HOSPITAL_COLUMN] == config.TRAIN_HOSPITAL]
    cle_train, cle_test = split_cleveland(cle)  # same rows, order and seed as v1
    rest = df[df[config.HOSPITAL_COLUMN] != config.TRAIN_HOSPITAL]
    strata = rest[config.HOSPITAL_COLUMN] + "_" + rest[config.TARGET_COLUMN].astype(str)
    rest_train, rest_test = train_test_split(
        rest, test_size=TEST_SIZE_V2, stratify=strata, random_state=config.RANDOM_SEED
    )
    return pd.concat([cle_train, rest_train]).copy(), pd.concat([cle_test, rest_test]).copy()


def stage_data(df: pd.DataFrame, stage: int) -> pd.DataFrame:
    """Patients from the hospitals that have this stage's measurements."""
    return df[df[config.HOSPITAL_COLUMN].isin(STAGE_HOSPITALS[stage])]


def fit_predict(train: pd.DataFrame, test: pd.DataFrame, stage: int) -> np.ndarray:
    """Tune the three model types on `train` (inner CV) and average their predictions."""
    features = config.STAGES[stage]
    X, y = train[features], train[config.TARGET_COLUMN].to_numpy()
    preds = [
        grid_search(name, stage).fit(X, y).predict_proba(test[features])[:, 1]
        for name in MODEL_NAMES
    ]
    return np.mean(preds, axis=0)  # the "ensemble" candidate, as in v1


def _metrics(y, p) -> dict:
    auc = bootstrap_ci(roc_auc_score, y, p, need_both_classes=True)
    return {
        "n": len(y),
        "disease_rate": float(np.mean(y)),
        "mean_predicted": float(np.mean(p)),
        "roc_auc": fmt_ci(*auc),
        "auc_value": auc[0],
        "auc_low": auc[1],
        "auc_high": auc[2],
        "ece": expected_calibration_error(y, p),
    }


def loho(train: pd.DataFrame, stage: int) -> pd.DataFrame:
    """Leave-one-hospital-out comparison of Cleveland-only vs pooled training."""
    data = stage_data(train, stage)
    hosp = data[config.HOSPITAL_COLUMN]
    rows = []
    for held_out in STAGE_HOSPITALS[stage]:
        start = time.time()
        target = data[hosp == held_out]
        y = target[config.TARGET_COLUMN].to_numpy()
        if held_out == "Cleveland":
            p_cle, p_pool = np.zeros(len(y)), np.zeros(len(y))
            others = data[hosp != "Cleveland"]
            folds = StratifiedKFold(config.CV_FOLDS, shuffle=True, random_state=config.RANDOM_SEED)
            for tr, te in folds.split(target, y):
                p_cle[te] = fit_predict(target.iloc[tr], target.iloc[te], stage)
                p_pool[te] = fit_predict(
                    pd.concat([target.iloc[tr], others]), target.iloc[te], stage
                )
        else:
            p_cle = fit_predict(data[hosp == "Cleveland"], target, stage)
            p_pool = fit_predict(data[hosp != held_out], target, stage)
        for strategy, p in (("cleveland_only", p_cle), ("pooled", p_pool)):
            rows.append(
                {"stage": stage, "held_out": held_out, "strategy": strategy, **_metrics(y, p)}
            )
        print(
            f"stage {stage} | {held_out:13s} | Cleveland-only AUC {rows[-2]['auc_value']:.3f} "
            f"| pooled AUC {rows[-1]['auc_value']:.3f} | {time.time() - start:.0f}s",
            flush=True,
        )
    return pd.DataFrame(rows)


def main():
    train, test = split_v2(load_pooled())
    print(f"v2 split: {len(train)} train / {len(test)} sealed test (never touched here)")
    print(train.groupby(config.HOSPITAL_COLUMN).size().to_string(), flush=True)
    results = pd.concat([loho(train, stage) for stage in (1, 2)], ignore_index=True)
    results.to_csv(config.REPORTS_DIR / "v2_loho.csv", index=False)
    pd.set_option("display.width", 200)
    print(
        results[
            [
                "stage",
                "held_out",
                "strategy",
                "n",
                "disease_rate",
                "mean_predicted",
                "roc_auc",
                "ece",
            ]
        ]
        .round(3)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
