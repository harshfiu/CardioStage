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

import joblib
import numpy as np
import pandas as pd

from cardiostage import config
from cardiostage.data import load_clean, split_cleveland
from cardiostage.explain import StageExplainer, explanation_text

# Valid category values (exactly as they appear in the training data).
CHOICES = {
    "cp": ["typical angina", "atypical angina", "non-anginal", "asymptomatic"],
    "restecg": ["normal", "st-t abnormality", "lv hypertrophy"],
    "slope": ["upsloping", "flat", "downsloping"],
    "thal": ["normal", "fixed defect", "reversable defect"],
}

ZONE_TEXT = {
    "low": ("Low estimated risk",
            "Risk is below this stage's rule-out level. In the training data, further "
            "tests rarely changed the outcome for patients in this range."),
    "high": ("High estimated risk",
             "Risk is above this stage's rule-in level, where at least 9 in 10 training "
             "patients truly had heart disease. Referral to a cardiologist is suggested."),
    "uncertain": ("Uncertain",
                  "Risk is between the rule-out and rule-in levels. The next test is "
                  "likely to clarify the picture."),
    "refer": ("Above the screening threshold",
              "Risk is above the final screening threshold, which was set to catch 97% "
              "of sick patients. Referral to a cardiologist is suggested."),
    "clear": ("Below the screening threshold",
              "Risk is below the final screening threshold. In training, only about "
              "3% of sick patients fell below it."),
}

NEXT_TEST = {1: "a treadmill (exercise stress) test with ECG",
             2: "invasive imaging (fluoroscopy and a thallium scan)"}


class ModelsNotFoundError(FileNotFoundError):
    pass


@dataclass
class Assessment:
    stage: int
    risk: float                 # calibrated probability of heart disease
    range_low: float            # plausible range from the 20 model copies
    range_high: float
    baseline: float             # "typical patient" risk used by the explanation
    zone: str                   # low / high / uncertain (stages 1-2) or refer / clear (stage 3)
    headline: str
    recommendation: str
    unusual: list = field(default_factory=list)   # reasons this patient is atypical
    not_measured: list = field(default_factory=list)
    explanation: pd.DataFrame = None               # per-measurement contributions
    summary: str = ""                              # plain-English explanation
    thresholds: dict = field(default_factory=dict)

    @property
    def suggests_next_test(self) -> bool:
        return self.zone == "uncertain"


class CardioStagePredictor:
    def __init__(self, bundles: dict, background: pd.DataFrame):
        self.bundles = bundles
        self.background = background
        self._explainers = {}

    @classmethod
    def load(cls) -> "CardioStagePredictor":
        paths = {s: config.MODELS_DIR / f"stage{s}.joblib" for s in config.STAGES}
        missing = [p.name for p in paths.values() if not p.exists()]
        if missing:
            raise ModelsNotFoundError(
                f"Trained models not found ({', '.join(missing)}). "
                "Build them with:  python -m cardiostage.train_all")
        bundles = {s: joblib.load(p) for s, p in paths.items()}
        train, _ = split_cleveland(load_clean())
        return cls(bundles, train)

    def explainer(self, stage: int) -> StageExplainer:
        # Built on first use and reused: creating one takes a moment.
        if stage not in self._explainers:
            b = self.bundles[stage]
            self._explainers[stage] = StageExplainer(b["model"], b["features"], self.background)
        return self._explainers[stage]

    @staticmethod
    def to_frame(patient: dict, features: list) -> pd.DataFrame:
        """One-row DataFrame in the exact format the models were trained on."""
        row = {}
        for f in features:
            value = patient.get(f)
            if value is None or (isinstance(value, float) and np.isnan(value)):
                row[f] = np.nan
            elif f in CHOICES:
                if value not in CHOICES[f]:
                    raise ValueError(f"{f} must be one of {CHOICES[f]}, got {value!r}")
                row[f] = value
            else:
                row[f] = float(value)
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

    def assess(self, patient: dict, stage: int, explain: bool = True) -> Assessment:
        """Full assessment of one patient using the measurements of `stage`."""
        b = self.bundles[stage]
        X = self.to_frame(patient, b["features"])
        risk = float(b["model"].predict_proba(X)[0, 1])
        low, high = b["uncertainty"].predict_interval(X)
        zone = self.zone(stage, risk)
        headline, detail = ZONE_TEXT[zone]
        recommendation = detail
        if zone == "uncertain":
            recommendation += f" Suggested next step: {NEXT_TEST[stage]}."

        result = Assessment(
            stage=stage, risk=risk, range_low=float(low[0]), range_high=float(high[0]),
            baseline=float("nan"), zone=zone, headline=headline,
            recommendation=recommendation,
            unusual=b["novelty"].check(X)[0],
            not_measured=[f for f in b["features"] if pd.isna(X.iloc[0][f])],
            thresholds=dict(b["zones"]),
        )
        if explain:
            explainer = self.explainer(stage)
            e = explainer.explain(X)
            result.baseline = float(e.base_values[0])
            result.explanation = explainer.describe(X.iloc[0], e[0])
            result.summary = explanation_text(result.explanation, result.baseline, risk)
        return result
