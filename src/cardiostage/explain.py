"""
Explaining predictions with SHAP (SHapley Additive exPlanations).

The question: "this patient got 34% risk; which of their measurements pushed
it up, and which pushed it down, and by how much?"

The idea comes from game theory. Treat each measurement as a "player" in a
team game whose score is the predicted risk. A player's fair share of the
credit (its Shapley value) is its average contribution across every possible
order in which the players could join the team. Two properties make it ideal
for explanations:

  1. ADDITIVE: baseline risk + all contributions = this patient's risk, exactly.
     Example: baseline 46% + chest pain +14 + max heart rate -6 + ... = 34%.
  2. FAIR: features that do nothing get 0; identical features get equal credit.

"Removing" a measurement means replacing it with values from typical training
patients (the BACKGROUND) and seeing how the prediction changes.

We explain in terms of the 13 ORIGINAL measurements, not the 22 internal
model columns. "Chest pain type: asymptomatic" is one explanation item, not
four one-hot columns. To make that possible, categories are converted to
integer codes for SHAP, and converted back before calling the model.
"""

import numpy as np
import pandas as pd
import shap

from cardiostage import config

# Plain-English names and value formatting for explanations.
LABELS = {
    "age": "Age",
    "sex": "Sex",
    "cp": "Chest pain type",
    "trestbps": "Resting blood pressure",
    "chol": "Cholesterol",
    "fbs": "Fasting blood sugar",
    "restecg": "Resting ECG",
    "thalch": "Max heart rate (treadmill)",
    "exang": "Chest pain during exercise",
    "oldpeak": "ST depression (treadmill ECG)",
    "slope": "ST segment slope",
    "ca": "Blocked vessels (fluoroscopy)",
    "thal": "Thallium scan",
}

CATEGORY_TEXT = {
    "typical angina": "typical angina (classic exertion-triggered chest pain)",
    "atypical angina": "atypical angina (some classic features)",
    "non-anginal": "non-anginal (chest pain unlikely to be heart-related)",
    "asymptomatic": "no chest pain",
    "normal": "normal",
    "st-t abnormality": "ST-T wave abnormality",
    "lv hypertrophy": "thickened heart wall (LV hypertrophy)",
    "upsloping": "upsloping (usually normal)",
    "flat": "flat (warning sign)",
    "downsloping": "downsloping (warning sign)",
    "fixed defect": "fixed defect (old damage)",
    "reversable defect": "reversible defect (reduced blood flow under stress)",
}


def format_value(feature: str, value) -> str:
    """Human-readable value, e.g. 152 -> '152 bpm', 1.0 (sex) -> 'male'."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "not measured"
    formats = {
        "age": lambda v: f"{v:.0f} years",
        "sex": lambda v: "male" if v == 1 else "female",
        "trestbps": lambda v: f"{v:.0f} mm Hg",
        "chol": lambda v: f"{v:.0f} mg/dl",
        "fbs": lambda v: "above 120 mg/dl" if v == 1 else "normal",
        "thalch": lambda v: f"{v:.0f} bpm",
        "exang": lambda v: "yes" if v == 1 else "no",
        "oldpeak": lambda v: f"{v:.1f} mm",
        "ca": lambda v: f"{v:.0f}",
    }
    if feature in formats:
        return formats[feature](float(value))
    return CATEGORY_TEXT.get(str(value), str(value))


class StageExplainer:
    """SHAP explanations for one stage's final (calibrated) model."""

    def __init__(self, model, features, background: pd.DataFrame, n_background: int = 50):
        self.model = model
        self.features = list(features)
        self.categorical = [c for c in self.features if c in config.CATEGORICAL_FEATURES]
        # A sample of training patients acts as "typical patients". 50 keeps
        # explanations fast (~1-3 s). If the diagnosis column is available we
        # sample sick and healthy patients in their true proportions, so the
        # baseline ("typical patient") risk matches the real training rate
        # instead of depending on the luck of a random draw.
        n = min(n_background, len(background))
        if config.TARGET_COLUMN in background.columns:
            frac = n / len(background)
            sample = background.groupby(config.TARGET_COLUMN, group_keys=False).apply(
                lambda g: g.sample(n=round(len(g) * frac), random_state=config.RANDOM_SEED)
            )
        else:
            sample = background.sample(n=n, random_state=config.RANDOM_SEED)
        background = background[self.features]
        sample = sample[self.features]
        # The list of known categories defines the integer codes.
        self.categories = {c: sorted(background[c].dropna().unique()) for c in self.categorical}
        masker = shap.maskers.Independent(self.encode(sample), max_samples=len(sample))
        self.explainer = shap.PermutationExplainer(self._predict, masker, seed=config.RANDOM_SEED)

    # ---- converting between model inputs and SHAP's numeric arrays ----------
    def encode(self, df: pd.DataFrame) -> np.ndarray:
        out = df[self.features].copy()
        for c in self.categorical:
            codes = {cat: i for i, cat in enumerate(self.categories[c])}
            out[c] = out[c].map(codes)  # unknown or missing -> NaN
        return out.astype(float).to_numpy()

    def decode(self, arr: np.ndarray) -> pd.DataFrame:
        df = pd.DataFrame(arr, columns=self.features)
        for c in self.categorical:
            cats = np.array(self.categories[c], dtype=object)
            codes = df[c].to_numpy()
            valid = ~np.isnan(codes)
            values = np.full(len(df), np.nan, dtype=object)
            values[valid] = cats[codes[valid].astype(int)]
            df[c] = values
        return df

    def _predict(self, arr: np.ndarray) -> np.ndarray:
        return self.model.predict_proba(self.decode(arr))[:, 1]

    # ---- explanations --------------------------------------------------------
    def explain(self, df: pd.DataFrame) -> shap.Explanation:
        """
        SHAP values in PROBABILITY units: a value of 0.12 means this
        measurement raised the risk by 12 percentage points.

        Reproducible: the permutation method tries random orderings of the
        measurements. SHAP only seeds NumPy's generator once (when the
        explainer is created), so without re-seeding the same patient could
        get slightly different bars on each request. Re-seeding here makes
        identical inputs always give identical explanations.
        """
        np.random.seed(config.RANDOM_SEED)
        return self.explainer(self.encode(df), silent=True)

    def describe(self, patient: pd.Series, explanation_row) -> pd.DataFrame:
        """
        One patient's explanation as a readable table, biggest effects first:
            feature | value | contribution (percentage points)
        """
        rows = [
            {
                "feature": f,
                "label": LABELS[f],
                "value": format_value(f, patient[f]),
                "contribution": float(v),
            }
            for f, v in zip(self.features, explanation_row.values)
        ]
        table = pd.DataFrame(rows)
        return table.reindex(table["contribution"].abs().sort_values(ascending=False).index)


def explanation_text(table: pd.DataFrame, base: float, risk: float, top: int = 4) -> str:
    """
    A short plain-English summary, e.g.
    "Estimated risk 34% (typical patient: 46%). Raising it: chest pain during
     exercise = yes (+12 pts). Lowering it: max heart rate = 172 bpm (-9 pts)."
    """
    up = table[table["contribution"] > 0.005].head(top)
    down = table[table["contribution"] < -0.005].head(top)
    parts = [f"Estimated risk {risk:.0%} (typical patient: {base:.0%})."]
    if len(up):
        parts.append(
            "Raising it: "
            + "; ".join(
                f"{r.label} = {r.value} (+{r.contribution * 100:.0f} pts)" for r in up.itertuples()
            )
            + "."
        )
    if len(down):
        parts.append(
            "Lowering it: "
            + "; ".join(
                f"{r.label} = {r.value} ({r.contribution * 100:.0f} pts)" for r in down.itertuples()
            )
            + "."
        )
    return " ".join(parts)
