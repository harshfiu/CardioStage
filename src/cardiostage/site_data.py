"""
Export the numbers shown on the landing site (site/) from the project's real
results, so the website never contains hand-typed statistics.

Reads reports/*.csv / *.json (committed) and, for the patient-flow and the
explanation example, the trained models (local, git-ignored). Writes
site/assets/data/site-data.json, which the site's JavaScript renders.

Re-run after any retraining:
    python -m cardiostage.site_data
"""

import json
import re

import pandas as pd

from cardiostage import config
from cardiostage.stats import parse_ci

SITE_DATA_PATH = config.PROJECT_ROOT / "site" / "assets" / "data" / "site-data.json"
SITE_DATA_JS_PATH = config.PROJECT_ROOT / "site" / "assets" / "data" / "site-data.js"
REP = config.REPORTS_DIR

# The landing site's worked example (same patient as the app's
# "Uncertain, then cleared" example).
EXAMPLE_PATIENT = dict(
    age=54,
    sex=1.0,
    cp="non-anginal",
    trestbps=135,
    chol=250,
    fbs=0.0,
    restecg="normal",
    thalch=165,
    exang=0.0,
    oldpeak=0.4,
    slope="upsloping",
    ca=0,
    thal="normal",
)
MODEL_LABELS = {
    "logistic_regression": "Logistic Regression",
    "random_forest": "Random Forest",
    "xgboost": "XGBoost",
    "ensemble": "Ensemble (average of 3)",
}


def strategies() -> dict:
    cv = pd.read_csv(REP / "phase5_strategies.csv", index_col=0)
    boot = pd.read_csv(REP / "phase5_strategies_bootstrap.csv", index_col=0)
    test = pd.read_csv(REP / "final_test_strategies.csv", index_col=0)
    staged, everyone = "CardioStage staged policy", "Everyone: stage 3 only"
    diff = boot.loc["Difference: staged - all tests"]

    def summary(row):
        return {
            "recall": float(row["recall"]),
            "specificity": float(row["specificity"]),
            "sick_missed": int(row["fn"]),
            "n_sick": int(row["tp"] + row["fn"]),
            "needed_invasive": float(row["needed_invasive"]),
            "needed_treadmill": float(row["needed_treadmill"]),
        }

    t_staged = test.loc[staged]
    recall_ci = parse_ci(t_staged["recall"])
    from cardiostage.data import load_clean, split_cleveland

    _, sealed = split_cleveland(load_clean())
    sealed_sick = int(sealed[config.TARGET_COLUMN].sum())
    return {
        "cv": {
            "staged": summary(cv.loc[staged]),
            "all_tests": summary(cv.loc[everyone]),
            "invasive_difference": parse_ci(diff["needed_invasive"]),
            "recall_difference": parse_ci(diff["recall"]),
            "n_patients": int(cv.loc[staged, ["tp", "fp", "fn", "tn"]].sum()),
        },
        "sealed_test": {
            "n_patients": len(sealed),
            "n_sick": sealed_sick,
            "sick_missed": int(t_staged["sick_missed"]),
            "recall": recall_ci,
            "needed_invasive": float(t_staged["needed_invasive"]),
            "specificity": parse_ci(t_staged["specificity"]),
            "all_tests_specificity": parse_ci(test.loc[everyone, "specificity"]),
        },
    }


def stage_auc() -> list:
    chosen = json.loads((REP / "phase5_zones.json").read_text())["chosen"]
    table = pd.read_csv(REP / "phase4_stage_auc.csv", index_col=0)
    out = []
    for stage in config.STAGES:
        mean, sd = (
            float(x)
            for x in re.findall(
                r"\d+\.\d+", table.loc[MODEL_LABELS[chosen[str(stage)]], f"stage_{stage}"]
            )
        )
        out.append({"stage": stage, "name": config.STAGE_NAMES[stage], "auc": mean, "sd": sd})
    return out


def external() -> list:
    df = pd.read_csv(REP / "phase6_external.csv")
    rows = []
    for hospital in ["Cleveland (internal, out-of-fold)"] + config.EXTERNAL_HOSPITALS:
        entry = {"hospital": hospital, "internal": hospital.startswith("Cleveland")}
        for stage in (1, 2):
            r = df[(df["stage"] == stage) & (df["hospital"] == hospital)].iloc[0]
            entry["n"] = int(r["n"])
            entry["disease_rate"] = float(r["disease_rate"])
            entry[f"stage{stage}"] = {
                "value": float(r["auc_value"]),
                "low": float(r["auc_low"]),
                "high": float(r["auc_high"]),
            }
        rows.append(entry)
    return rows


def patient_flow() -> list:
    """Where the 243 training patients stop in the staged policy (out-of-fold, calibrated).

    Shared by the landing site and the app's Results page (chart_data.py).
    """
    from cardiostage import integrity
    from cardiostage.staging import simulate_policy

    saved = integrity.load(config.MODELS_DIR / "phase5_oof.joblib")
    p = {s: saved["oof"][s][saved["method"][s]].mean(axis=0) for s in config.STAGES}
    zones = {
        int(s): z for s, z in json.loads((REP / "phase5_zones.json").read_text())["zones"].items()
    }
    decision, stopped = simulate_policy(p, zones)
    flow = []
    for stage in config.STAGES:
        here = stopped == stage
        flow.append(
            {
                "stage": stage,
                "name": config.STAGE_NAMES[stage],
                "reached": int((stopped >= stage).sum()),
                "cleared": int((here & (decision == 0)).sum()),
                "referred": int((here & (decision == 1)).sum()),
                "onward": int((stopped > stage).sum()),
            }
        )
    return flow


def worked_example() -> dict:
    """The landing site's explanation example (needs models/)."""
    from cardiostage.predictor import CardioStagePredictor

    predictor = CardioStagePredictor.load()
    result = predictor.assess(EXAMPLE_PATIENT, 1, with_range=False)
    return {
        "stage": 1,
        "risk": result.risk,
        "baseline": result.baseline,
        "zone": result.zone,
        "headline": result.headline,
        "contributions": [
            {"label": r.label, "value": r.value, "points": round(r.contribution * 100, 1)}
            for r in result.explanation.itertuples()
        ],
    }


def build() -> dict:
    return {
        "source": "Generated by `python -m cardiostage.site_data` from reports/ and models/.",
        "strategies": strategies(),
        "stage_auc": stage_auc(),
        "flow": patient_flow(),
        "external": external(),
        "example": worked_example(),
        "targets": {"screening_recall": config.SCREENING_RECALL},
    }


def main():
    data = build()
    SITE_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2)
    SITE_DATA_PATH.write_text(text, encoding="utf-8")
    # Same data as a script, so the site also works when opened straight from
    # disk (browsers block fetch() of local JSON files). Loaded with
    # <script src>, which the site's Content-Security-Policy allows ('self').
    SITE_DATA_JS_PATH.write_text(
        "// Generated by `python -m cardiostage.site_data`. Do not edit by hand.\n"
        f"window.CARDIOSTAGE_DATA = {text};\n",
        encoding="utf-8",
    )
    print(
        f"wrote {SITE_DATA_PATH.relative_to(config.PROJECT_ROOT)} and "
        f"{SITE_DATA_JS_PATH.relative_to(config.PROJECT_ROOT)}"
    )


if __name__ == "__main__":
    main()
