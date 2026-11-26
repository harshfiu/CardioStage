"""About page: method, data, limitations."""

import streamlit as st

from consent import data_handling_text, is_public_deployment
from ui import DISCLAIMER

st.title("ℹ️ About CardioStage")
st.warning(DISCLAIMER, icon="⚕️")

st.markdown("### Your privacy")
st.markdown(data_handling_text(is_public_deployment()))

st.markdown("""
### The idea
Doctors don't send every patient with chest pain for invasive imaging. They start with
cheap information, and escalate only when the answer is still unclear. CardioStage
copies that process with three models, one per stage:

| Stage | Measurements | What it takes |
|---|---|---|
| 1. Basic check-up | age, sex, chest pain type, blood pressure, cholesterol, blood sugar | Clinic visit and blood test |
| 2. + Treadmill | resting ECG, max heart rate, exercise chest pain, ST depression, ST slope | ECG and supervised stress test |
| 3. + Invasive imaging | vessels seen on fluoroscopy, thallium scan | Hospital, dye/radiation |

At stages 1–2 each patient is **cleared** (low risk), **referred** (high risk), or
sent to the **next test** (uncertain). Stage 3 makes the final call with a threshold
set to catch 97% of sick patients.

### How it was built
- **Data:** UCI Heart Disease dataset: 920 patients from Cleveland, Hungary,
  Switzerland and VA Long Beach (1980s), plus 303 patients from Iran (2010s,
  Z-Alizadeh Sani). The check-up model (version 2) learned from all five hospitals;
  the treadmill and imaging models from Cleveland only, the one hospital with
  complete data for those stages.
- **Models:** logistic regression, random forest, XGBoost and their average, compared
  with nested cross-validation at each stage. Used: logistic regression (stage 1)
  and the averaged ensemble (stages 2–3).
- **Honest probabilities:** calibrated with Platt scaling where it helped.
- **Transparency:** every estimate is explained with SHAP; a plausible range shows how
  stable it is; an unusual-patient check warns when the model is extrapolating.
- **Evaluation:** out-of-fold predictions, bootstrap confidence intervals, external
  validation at three unseen hospitals and in Iran, a fairness analysis by sex and age,
  leave-one-hospital-out tests, and a 245-patient sealed test for version 2.

### Known limitations
- **Underestimates typical angina in modern patients:** tested on 303 patients from Iran (2010s),
  version 1 caught only ~68% of sick patients instead of 97%, mainly because 94% of people with
  typical angina had heart disease while it estimated ~23%. Version 2 learned from five hospitals
  and fixes most of this, but in Iran's sealed-test patients it still estimated ~81% where 97%
  were sick, so the app shows a warning for typical angina.
- **VA Long Beach is version 2's weak spot:** on its 40 sealed-test patients, version 2 ranks
  them worse than version 1 did (AUC 0.71 vs 0.83; version 1 was partly lucky there).
- **Small, mostly old data:** the check-up stage learned from 976 patients at five hospitals
  (1980s-2010s); the treadmill and imaging stages from 243 patients at one US hospital in the 1980s.
  Medicine, populations and equipment have changed.
- **Referral population:** all patients were already sent for heart testing, so
  patterns (e.g. "no chest pain → higher risk") don't apply to the general public.
- **Cutoffs are local:** the clear/refer thresholds were tuned on the training hospitals
  (stage 1 on all five, stages 2–3 on Cleveland). In version 1's test at Hungary, the
  stage-1 clear zone was less safe (90% vs 96%). Any new setting must re-validate them.
- **Stage 3 not externally validated:** other hospitals lacked the invasive test data.
- **Atypical presentations:** in version 1's testing, a woman with atypical chest pain was
  cleared at stage 1. Version 2 no longer clears the matching example patient, but such
  presentations need more data to evaluate properly.
- **Explanations describe the model, not biology:** a feature lowering the estimate
  isn't a protective effect you could change.

### Learn more
The project's code, step-by-step learning guides and full results are in the
[GitHub repository](https://github.com/harshfiu/CardioStage).
""")
