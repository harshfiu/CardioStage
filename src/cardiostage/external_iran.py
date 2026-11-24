"""
External validation on a modern, non-US cohort: the Z-Alizadeh Sani dataset.

Data: 303 patients evaluated for coronary artery disease (CAD) at a Tehran
heart centre (Iran), donated to the UCI repository in 2017, CC BY 4.0
(data/raw/external/README.md). Its outcome matches ours exactly: "CAD if
diameter narrowing >= 50% on angiography, otherwise Normal".

What can be tested: only STAGE 1 (the basic check-up) fairly. The dataset
has no treadmill (exercise) test and no fluoroscopy/thallium results, so
stages 2-3 would be mostly imputed guesses. Stage 2 is reported once, clearly
labelled, only to show how much the missing exercise test matters.

Mapping to CardioStage's inputs (every assumption is listed here):
  age        Age
  sex        Sex ("Male" -> 1, "Fmale" -> 0; the file's spelling)
  cp         Typical Chest Pain=1 -> "typical angina"; else Atypical=Y ->
             "atypical angina"; else Nonanginal=Y -> "non-anginal"; else
             "asymptomatic". (The columns never contradict each other.)
  trestbps   BP (mm Hg)
  chol       NOT measured directly. Estimated total cholesterol with the
             Friedewald relation TC = LDL + HDL + TG/5 (mg/dl). Unreliable
             when TG >= 400 (5 patients), and 2 patients with implausibly
             low LDL give estimates below the app's plausible range
             (80-700 mg/dl): those 7 get "not measured", as the app would.
  fbs        FBS (mg/dl) > 120 -> 1
  restecg    LVH=Y -> "lv hypertrophy"; else any of ST elevation, ST
             depression or T inversion -> "st-t abnormality"; else "normal"
  exercise   thalch, exang, oldpeak, slope: not available -> not measured

Run (needs the trained models):
    python -m cardiostage.external_iran
"""

import json

import numpy as np
import pandas as pd

from cardiostage import config, integrity
from cardiostage.calibration import expected_calibration_error
from cardiostage.external_validation import evaluate, internal_reference
from cardiostage.predictor import PLAUSIBLE_RANGES
from cardiostage.stats import prior_shift

IRAN_DATA_PATH = config.PROJECT_ROOT / "data" / "raw" / "external" / "z_alizadeh_sani.csv"
CHEST_PAIN_ORDER = ["typical angina", "atypical angina", "non-anginal", "asymptomatic"]


def load_iran() -> pd.DataFrame:
    """The dataset exactly as published (converted once from the UCI .xlsx; verified identical)."""
    return pd.read_csv(IRAN_DATA_PATH)


def to_cardiostage(raw: pd.DataFrame) -> pd.DataFrame:
    """Map the Iranian columns onto CardioStage's features (see the module docstring)."""
    out = pd.DataFrame(index=raw.index)
    out["age"] = raw["Age"].astype(float)
    out["sex"] = raw["Sex"].map({"Male": 1.0, "Fmale": 0.0})
    out["cp"] = np.select(
        [raw["Typical Chest Pain"] == 1, raw["Atypical"] == "Y", raw["Nonanginal"] == "Y"],
        ["typical angina", "atypical angina", "non-anginal"],
        "asymptomatic",
    )
    out["trestbps"] = raw["BP"].astype(float)
    estimated_chol = raw["LDL"] + raw["HDL"] + raw["TG"] / 5
    low, high = PLAUSIBLE_RANGES["chol"]
    usable = (raw["TG"] < 400) & estimated_chol.between(low, high)  # Friedewald fails above 400
    out["chol"] = estimated_chol.where(usable)
    out["fbs"] = (raw["FBS"] > 120).astype(float)
    st_t = (raw["St Elevation"] == 1) | (raw["St Depression"] == 1) | (raw["Tinversion"] == 1)
    out["restecg"] = np.select(
        [raw["LVH"] == "Y", st_t], ["lv hypertrophy", "st-t abnormality"], "normal"
    )
    for not_available in ("thalch", "exang", "oldpeak", "slope", "ca", "thal"):
        out[not_available] = np.nan
    out[config.TARGET_COLUMN] = (raw["Cath"] == "Cad").astype(int)
    return out


def chest_pain_table(df: pd.DataFrame, p: np.ndarray) -> pd.DataFrame:
    """Observed disease rate vs the model's average prediction, per chest-pain type."""
    t = pd.DataFrame({"cp": df["cp"], "y": df[config.TARGET_COLUMN], "p": p})
    g = t.groupby("cp").agg(
        n=("y", "size"), disease_rate=("y", "mean"), mean_predicted=("p", "mean")
    )
    return g.reindex(CHEST_PAIN_ORDER)


def main():
    iran = to_cardiostage(load_iran())
    y = iran[config.TARGET_COLUMN].to_numpy()
    train_rate = 0.4568  # Cleveland training disease rate (reports/phase6_external.csv)
    _, _, thresholds = internal_reference()
    results, details = [], {}
    for stage in (1, 2):
        bundle = integrity.load(config.MODELS_DIR / f"stage{stage}.joblib")
        X = iran[config.STAGES[stage]]
        p = bundle["model"].predict_proba(X)[:, 1]
        row = evaluate(y, p, bundle["zones"], thresholds[stage], bundle["novelty"].is_unusual(X))
        p_shift = prior_shift(p, train_rate, y.mean())
        row["ece_after_prior_shift"] = expected_calibration_error(y, p_shift)
        row["mean_predicted_after_shift"] = p_shift.mean()
        row["note"] = (
            "fair test: all stage-1 measurements available (cholesterol estimated)"
            if stage == 1
            else "exercise-test measurements NOT available: imputed; informational only"
        )
        results.append({"stage": stage, "cohort": "Iran (Z-Alizadeh Sani)", **row})
        if stage == 1:
            details["chest_pain"] = (
                chest_pain_table(iran, p).round(3).reset_index().to_dict("records")
            )
    table = pd.DataFrame(results)
    table.to_csv(config.REPORTS_DIR / "phase10_iran_external.csv", index=False)
    (config.REPORTS_DIR / "phase10_iran_details.json").write_text(
        json.dumps(details, indent=2), encoding="utf-8"
    )
    pd.set_option("display.width", 220, "display.max_columns", 30)
    show = [
        "stage",
        "n",
        "disease_rate",
        "mean_predicted",
        "roc_auc",
        "ece",
        "ece_after_prior_shift",
        "recall@97",
        "specificity@97",
        "share_cleared",
        "cleared_but_sick",
        "share_referred",
        "ppv_referred",
        "share_unusual",
    ]
    print(table[show].round(3).to_string(index=False))
    print("\nStage 1, by chest-pain type (observed vs predicted):")
    print(pd.DataFrame(details["chest_pain"]).to_string(index=False))


if __name__ == "__main__":
    main()
