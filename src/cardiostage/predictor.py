"""
CardioStage's decision engine: everything the app needs, with no UI code.

Keeping the logic here (instead of inside the Streamlit file) means:
  - it can be tested directly (tests/test_predictor.py),
  - the app stays a thin layer that only collects inputs and shows outputs,
  - the same engine could power a different interface later (API, CLI...).

Usage:
    predictor = CardioStagePredictor.load()
    result = predictor.assess({"age": 58, "sex": 0.0, "cp": "atypical angina", ...}, stage=1)
    result.risk, result.zone, result.recommendation, result.summary
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from cardiostage import config, integrity
from cardiostage.data import load_clean, split_cleveland
from cardiostage.explain import StageExplainer, explanation_text

# Valid category values (exactly as they appear in the training data).
CHOICES = {
    "cp": ["typical angina", "atypical angina", "non-anginal", "asymptomatic"],
    "restecg": ["normal", "st-t abnormality", "lv hypertrophy"],
    "slope": ["upsloping", "flat", "downsloping"],
    "thal": ["normal", "fixed defect", "reversable defect"],
}

# Allowed values for coded numeric inputs (security finding SEC-06: the
# interface restricts these, but the engine re-checks them so a crafted
# request can't feed it anything else).
ALLOWED_CODES = {
    "sex": {0.0, 1.0},
    "fbs": {0.0, 1.0},
    "exang": {0.0, 1.0},
    "ca": {0.0, 1.0, 2.0, 3.0},
}

# Physically plausible limits for measurements (the same bounds as the app's
# input boxes). Values outside these are rejected outright; values inside but
# outside the TRAINING range are accepted and flagged by the novelty detector.
PLAUSIBLE_RANGES = {
    "age": (18, 100),
    "trestbps": (60, 250),
    "chol": (80, 700),
    "thalch": (60, 230),
    "oldpeak": (-3.0, 7.0),
}


class InvalidInputError(ValueError):
    """Patient input that the models must not be asked to score."""


ZONE_TEXT = {
    "low": (
        "Low estimated risk",
        "Risk is below this stage's rule-out level. In the training data, further "
        "tests rarely changed the outcome for patients in this range.",
    ),
    "high": (
        "High estimated risk",
        "Risk is above this stage's rule-in level, where at least 9 in 10 training "
        "patients truly had heart disease. Referral to a cardiologist is suggested.",
    ),
    "uncertain": (
        "Uncertain",
        "Risk is between the rule-out and rule-in levels. The next test is "
        "likely to clarify the picture.",
    ),
    "refer": (
        "Above the screening threshold",
        "Risk is above the final screening threshold, which was set to catch 97% "
        "of sick patients. Referral to a cardiologist is suggested.",
    ),
    "clear": (
        "Below the screening threshold",
        "Risk is below the final screening threshold. In training, only about "
        "3% of sick patients fell below it.",
    ),
}

NEXT_TEST = {
    1: "a treadmill (exercise stress) test with ECG",
    2: "invasive imaging (fluoroscopy and a thallium scan)",
}


class ModelsNotFoundError(FileNotFoundError):
    pass


# Known weaknesses found by external testing, shown with any matching estimate.
# Each entry: (which patients, plain-language caution). Evidence lives in
# reports/phase10_iran_external.csv (v1), reports/v2_final_second_look_typical_angina.csv
# (v2) and docs/learning/14-new-data-and-v2.md. Kept until it is completely unnecessary (owner).
TYPICAL_ANGINA_CAUTION = (
    "**Known weakness: this estimate may still be too low.** Version 2 learned from five "
    "hospitals and now treats typical angina as a strong warning sign, but in a test on modern "
    "patients (Iran, 2010s) 97% of people with typical angina had coronary artery disease, while "
    "CardioStage estimated about 81% on average. Typical angina is a classic warning sign. Please "
    "treat it as a reason to see a doctor, whatever this number says."
)


def known_cautions(patient: dict) -> list:
    """Plain-language cautions for patient groups where the model is known to be wrong."""
    cautions = []
    if patient.get("cp") == "typical angina":
        cautions.append(TYPICAL_ANGINA_CAUTION)
    return cautions


def load_bundles() -> dict:
    """
    The three stage bundles, from the safest source available.

    Public deployment (CARDIOSTAGE_DEPLOYMENT=public): skops files only,
    downloaded and fingerprint-checked if missing; never a pickle.
    Locally: the trained joblib bundles when present (fingerprint-checked by
    integrity.load, SEC-05), otherwise the skops files. Set
    CARDIOSTAGE_MODEL_FORMAT=skops to force skops locally.
    """
    import os

    from cardiostage import model_store

    public = os.environ.get("CARDIOSTAGE_DEPLOYMENT", "").strip().lower() == "public"
    force_skops = os.environ.get("CARDIOSTAGE_MODEL_FORMAT", "").strip().lower() == "skops"
    paths = {s: config.MODELS_DIR / f"stage{s}.joblib" for s in config.STAGES}
    if not public and not force_skops and all(p.exists() for p in paths.values()):
        return {s: integrity.load(p) for s, p in paths.items()}
    if public and not model_store.available():
        model_store.download()  # verified against deploy/models.json before use
    if model_store.available():
        return model_store.load_bundles()
    raise ModelsNotFoundError(
        "Trained models not found. Either build them (~10 minutes):  "
        "python -m cardiostage.train_all   or download the released ones:  "
        "python -m cardiostage.model_store download"
    )


@dataclass
class Assessment:
    stage: int
    risk: float  # calibrated probability of heart disease
    zone: str  # low / high / uncertain (stages 1-2) or refer / clear (stage 3)
    headline: str
    recommendation: str
    unusual: list = field(default_factory=list)  # reasons this patient is atypical
    cautions: list = field(default_factory=list)  # known model weaknesses that apply here
    not_measured: list = field(default_factory=list)
    thresholds: dict = field(default_factory=dict)
    # The validated one-row input, kept so the slower parts below can be
    # computed after the core result is already on screen.
    frame: pd.DataFrame = None
    # Filled by add_range() (~2 s for stages 2-3):
    range_low: float = None  # plausible range from the 20 model copies
    range_high: float = None
    # Filled by add_explanation() (~3 s for stages 2-3):
    baseline: float = None  # "typical patient" risk used by the explanation
    explanation: pd.DataFrame = None  # per-measurement contributions
    summary: str = ""  # plain-English explanation

    @property
    def suggests_next_test(self) -> bool:
        return self.zone == "uncertain"

    @property
    def has_range(self) -> bool:
        return self.range_low is not None

    @property
    def has_explanation(self) -> bool:
        return self.explanation is not None


class CardioStagePredictor:
    def __init__(self, bundles: dict, background: pd.DataFrame):
        self.bundles = bundles
        self.background = background
        self._explainers = {}

    @classmethod
    def load(cls) -> "CardioStagePredictor":
        train, _ = split_cleveland(load_clean())
        return cls(load_bundles(), train)

    def explainer(self, stage: int) -> StageExplainer:
        # Built on first use and reused: creating one takes a moment.
        if stage not in self._explainers:
            b = self.bundles[stage]
            self._explainers[stage] = StageExplainer(b["model"], b["features"], self.background)
        return self._explainers[stage]

    @staticmethod
    def to_frame(patient: dict, features: list) -> pd.DataFrame:
        """
        One-row DataFrame in the exact format the models were trained on.

        Every value is validated (defence in depth, SEC-06); anything unexpected
        raises InvalidInputError instead of reaching the models.
        """
        row = {}
        for f in features:
            value = patient.get(f)
            if value is None or (isinstance(value, float) and np.isnan(value)):
                row[f] = np.nan  # "not measured": the model imputes a typical value
                continue
            if f in CHOICES:
                if value not in CHOICES[f]:
                    raise InvalidInputError(f"{f} must be one of {CHOICES[f]}, got {value!r}")
                row[f] = value
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                raise InvalidInputError(f"{f} must be a number, got {value!r}") from None
            if not np.isfinite(number):
                raise InvalidInputError(f"{f} must be a finite number, got {value!r}")
            if f in ALLOWED_CODES and number not in ALLOWED_CODES[f]:
                raise InvalidInputError(
                    f"{f} must be one of {sorted(ALLOWED_CODES[f])}, got {value!r}"
                )
            if f in PLAUSIBLE_RANGES:
                low, high = PLAUSIBLE_RANGES[f]
                if not low <= number <= high:
                    raise InvalidInputError(f"{f} must be between {low} and {high}, got {value!r}")
            row[f] = number
        return pd.DataFrame([row], columns=features)

    def zone(self, stage: int, risk: float) -> str:
        z = self.bundles[stage]["zones"]
        if stage == 3:
            return "refer" if risk >= z["screening_threshold"] else "clear"
        if risk >= z["rule_in_from"]:
            return "high"
        if risk < z["rule_out_below"]:
            return "low"
        return "uncertain"

    def assess(
        self, patient: dict, stage: int, explain: bool = True, with_range: bool = True
    ) -> Assessment:
        """
        Assessment of one patient using the measurements of `stage`.

        The core result (validation, risk, decision zone, unusual-patient
        warnings) takes ~0.1 s. The plausible range (~2 s) and the explanation
        (~3 s) are the slow parts; pass with_range=False / explain=False to get
        the core result immediately and add them later with add_range() and
        add_explanation(). The app does exactly that, so the decision appears
        at once and the details fill in underneath.
        """
        b = self.bundles[stage]
        X = self.to_frame(patient, b["features"])
        risk = float(b["model"].predict_proba(X)[0, 1])
        zone = self.zone(stage, risk)
        headline, detail = ZONE_TEXT[zone]
        recommendation = detail
        if zone == "uncertain":
            recommendation += f" Suggested next step: {NEXT_TEST[stage]}."

        result = Assessment(
            stage=stage,
            risk=risk,
            zone=zone,
            headline=headline,
            recommendation=recommendation,
            unusual=b["novelty"].check(X)[0],
            cautions=known_cautions(patient),
            not_measured=[f for f in b["features"] if pd.isna(X.iloc[0][f])],
            thresholds=dict(b["zones"]),
            frame=X,
        )
        if with_range:
            self.add_range(result)
        if explain:
            self.add_explanation(result)
        return result

    def add_range(self, result: Assessment) -> Assessment:
        """Fill in the plausible range (10th-90th percentile of the 20 model copies)."""
        low, high = self.bundles[result.stage]["uncertainty"].predict_interval(result.frame)
        result.range_low, result.range_high = float(low[0]), float(high[0])
        return result

    def add_explanation(self, result: Assessment) -> Assessment:
        """Fill in the SHAP explanation and its plain-English summary."""
        explainer = self.explainer(result.stage)
        e = explainer.explain(result.frame)
        result.baseline = float(e.base_values[0])
        result.explanation = explainer.describe(result.frame.iloc[0], e[0])
        result.summary = explanation_text(result.explanation, result.baseline, result.risk)
        return result
