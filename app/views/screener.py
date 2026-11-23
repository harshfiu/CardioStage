"""
CardioStage: staged heart-disease risk screening (Streamlit app).

Run from the project root:
    streamlit run app/streamlit_app.py

Flow: enter basic check-up details -> get a calibrated risk, explanation and
recommendation -> if uncertain, add treadmill results -> then invasive
imaging. Each step only asks for the next test when it's likely to help.
"""

import logging
import time

import streamlit as st

from cardiostage import ratelimit
from cardiostage.predictor import InvalidInputError
from ui import DISCLAIMER, load_predictor_or_stop, render_assessment

# ----------------------------------------------------------------------------
# Input options with plain-English labels
# ----------------------------------------------------------------------------
CP = {
    "typical angina": "Typical angina: pressure-like pain on exertion, eased by rest",
    "atypical angina": "Atypical angina: some, but not all, of those features",
    "non-anginal": "Non-anginal: chest pain that doesn't seem heart-related",
    "asymptomatic": "No chest pain",
}
RESTECG = {
    "normal": "Normal",
    "st-t abnormality": "ST-T wave abnormality",
    "lv hypertrophy": "Thickened heart wall (LV hypertrophy)",
    None: "Not measured",
}
SLOPE = {
    "upsloping": "Upsloping",
    "flat": "Flat",
    "downsloping": "Downsloping",
    None: "Not measured",
}
THAL = {
    "normal": "Normal",
    "fixed defect": "Fixed defect (permanent damage)",
    "reversable defect": "Reversible defect (reduced blood flow under stress)",
    None: "Not measured",
}
FBS = {0.0: "Normal (120 mg/dl or below)", 1.0: "High (above 120 mg/dl)", None: "Not measured"}
YES_NO = {0.0: "No", 1.0: "Yes"}
CA = {0: "0", 1: "1", 2: "2", 3: "3", None: "Not measured"}

# Example patients (made up for demonstration; not real people). Names are
# kept short so they fit the sidebar; the description is shown underneath.
EXAMPLE_DESCRIPTIONS = {
    "Low risk": "42-year-old woman, chest pain that doesn't seem heart-related.",
    "Uncertain, then cleared": "54-year-old man; reassuring treadmill and imaging results.",
    "High risk": "63-year-old man, no chest pain, abnormal treadmill and imaging.",
    "Known limitation": "57-year-old woman with atypical chest pain.",
}
NO_EXAMPLE = "(enter my own)"
EXAMPLES = {
    "Low risk": dict(
        age=42,
        sex="Female",
        cp="non-anginal",
        trestbps=118,
        chol=205,
        chol_unknown=False,
        fbs=0.0,
        restecg="normal",
        thalch=172,
        exang=0.0,
        oldpeak=0.0,
        slope="upsloping",
        ca=0,
        thal="normal",
    ),
    "Uncertain, then cleared": dict(
        age=54,
        sex="Male",
        cp="non-anginal",
        trestbps=135,
        chol=250,
        chol_unknown=False,
        fbs=0.0,
        restecg="normal",
        thalch=165,
        exang=0.0,
        oldpeak=0.4,
        slope="upsloping",
        ca=0,
        thal="normal",
    ),
    "High risk": dict(
        age=63,
        sex="Male",
        cp="asymptomatic",
        trestbps=150,
        chol=290,
        chol_unknown=False,
        fbs=1.0,
        restecg="lv hypertrophy",
        thalch=112,
        exang=1.0,
        oldpeak=2.6,
        slope="flat",
        ca=2,
        thal="reversable defect",
    ),
    # Deliberately included: reproduces the known limitation from Phase 6. She's
    # cleared at the check-up, yet imaging would show 2 blocked vessels.
    "Known limitation": dict(
        age=57,
        sex="Female",
        cp="atypical angina",
        trestbps=132,
        chol=310,
        chol_unknown=False,
        fbs=1.0,
        restecg="lv hypertrophy",
        thalch=150,
        exang=0.0,
        oldpeak=0.2,
        slope="upsloping",
        ca=2,
        thal="normal",
    ),
}
DEFAULTS = dict(
    age=55,
    sex="Male",
    cp="non-anginal",
    trestbps=130,
    chol=240,
    chol_unknown=False,
    fbs=0.0,
    restecg="normal",
    thalch=150,
    exang=0.0,
    oldpeak=0.0,
    slope="upsloping",
    ca=0,
    thal="normal",
)


def set_inputs(values: dict):
    for key, value in values.items():
        st.session_state[key] = value
    st.session_state.results = {}


def load_example():
    choice = st.session_state.example
    if choice in EXAMPLES:
        set_inputs(EXAMPLES[choice])


def reset_all():
    # Runs as a button callback, i.e. BEFORE the page is redrawn. That's the
    # only point where Streamlit lets us change the example selector's value
    # (changing a widget after it's drawn raises an error), so the selector
    # and its note are cleared together with the form.
    set_inputs(DEFAULTS)
    st.session_state.example = NO_EXAMPLE


if "results" not in st.session_state:
    set_inputs(DEFAULTS)

# ----------------------------------------------------------------------------
# Sidebar
# ----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Try an example")
    st.selectbox(
        "Example patient",
        [NO_EXAMPLE] + list(EXAMPLES),
        key="example",
        on_change=load_example,
        label_visibility="collapsed",
    )
    if st.session_state.example in EXAMPLE_DESCRIPTIONS:
        st.caption(EXAMPLE_DESCRIPTIONS[st.session_state.example])
    if st.session_state.example == "Known limitation":
        st.info(
            "This example shows a known weakness. At the basic check-up, 'female' and "
            "'atypical chest pain' both lower the estimate, so she's cleared, but "
            "imaging would reveal 2 blocked vessels. Open the optional later stages "
            "to see it. (See the About page.)",
            icon="🧪",
        )
    st.button("Reset all inputs", width="stretch", on_click=reset_all)
    st.divider()
    st.caption(DISCLAIMER)

# ----------------------------------------------------------------------------
# Header
# ----------------------------------------------------------------------------
st.title("🫀 CardioStage")
st.markdown(
    "##### Heart-disease risk screening that orders tests the way doctors do: cheapest first."
)
st.caption(
    "Start with a basic check-up. CardioStage only suggests the next, more involved "
    "test when it's likely to change the answer."
)
st.warning(DISCLAIMER, icon="⚕️")

predictor = load_predictor_or_stop()


def patient() -> dict:
    s = st.session_state
    return {
        "age": s.age,
        "sex": 1.0 if s.sex == "Male" else 0.0,
        "cp": s.cp,
        "trestbps": s.trestbps,
        "chol": None if s.chol_unknown else s.chol,
        "fbs": s.fbs,
        "restecg": s.restecg,
        "thalch": s.thalch,
        "exang": s.exang,
        "oldpeak": s.oldpeak,
        "slope": s.slope,
        "ca": s.ca,
        "thal": s.thal,
    }


def run_stage(stage: int):
    # Abuse protection (SEC-02): cap assessments per browser session.
    allowed, st.session_state.assessment_times, wait = ratelimit.check_and_record(
        st.session_state.get("assessment_times", []), time.time()
    )
    if not allowed:
        st.warning(
            f"Too many assessments in a short time. Please wait {wait:.0f} seconds and try again.",
            icon="⏳",
        )
        return

    # Re-assessing a stage invalidates any later stages built on old inputs.
    st.session_state.results = {k: v for k, v in st.session_state.results.items() if k < stage}
    try:
        # Core result only (~0.1 s): the plausible range and the explanation are
        # filled in progressively by render_assessment, so the decision shows
        # immediately instead of after ~6 seconds.
        st.session_state.results[stage] = predictor.assess(
            patient(), stage, explain=False, with_range=False
        )
    except InvalidInputError as e:
        st.error(f"Some inputs aren't valid, so no assessment was made: {e}", icon="🚫")
    except Exception:
        # Never show tracebacks (local paths, code) to users (SEC-03). The full
        # error still goes to the server console for the developer.
        logging.getLogger("cardiostage.app").exception("Assessment failed")
        st.error(
            "Something went wrong while assessing this patient. No result was "
            "produced. Please check the inputs and try again.",
            icon="🚫",
        )


# ----------------------------------------------------------------------------
# Stage forms
# ----------------------------------------------------------------------------
def stage1_form():
    with st.form("stage1"):
        st.markdown("#### Stage 1 · Basic check-up")
        st.caption(
            "Available from a routine clinic visit and blood test. Tip: drag a slider, "
            "or click it and use the arrow keys for an exact value."
        )
        c1, c2, c3 = st.columns(3)
        c1.slider("Age (years)", 18, 100, key="age")
        c1.radio("Sex", ["Female", "Male"], key="sex", horizontal=True)
        c2.selectbox(
            "Chest pain type",
            list(CP),
            format_func=CP.get,
            key="cp",
            help="How the chest pain behaves. 'Typical angina' is the textbook "
            "pattern of heart-related pain.",
        )
        c2.slider(
            "Resting blood pressure (mm Hg, top number)",
            60,
            250,
            key="trestbps",
            help="Normal is about 120; 140 or above is high.",
        )
        c3.slider(
            "Cholesterol (mg/dl)",
            80,
            700,
            key="chol",
            help="Total cholesterol. Under 200 is desirable; 240+ is high.",
        )
        c3.checkbox("Cholesterol not measured", key="chol_unknown")
        c3.selectbox(
            "Fasting blood sugar",
            list(FBS),
            format_func=FBS.get,
            key="fbs",
            help="Above 120 mg/dl after fasting suggests diabetes.",
        )
        if st.form_submit_button("Assess risk"):
            run_stage(1)


def stage2_form():
    with st.form("stage2"):
        st.markdown("#### Stage 2 · Treadmill stress test")
        st.caption("Needs an ECG and a supervised exercise test.")
        c1, c2, c3 = st.columns(3)
        c1.selectbox("Resting ECG", list(RESTECG), format_func=RESTECG.get, key="restecg")
        c1.slider(
            "Max heart rate reached (bpm)",
            60,
            230,
            key="thalch",
            help="A healthy heart speeds up a lot under exercise.",
        )
        c2.selectbox(
            "Chest pain during exercise?", list(YES_NO), format_func=YES_NO.get, key="exang"
        )
        c2.slider(
            "ST depression (mm)",
            -3.0,
            7.0,
            step=0.1,
            key="oldpeak",
            help="How far the ECG's ST segment dips during exercise compared "
            "with rest. 0 is normal; larger dips suggest the heart "
            "muscle isn't getting enough blood.",
        )
        c3.selectbox(
            "ST segment slope at peak exercise",
            list(SLOPE),
            format_func=SLOPE.get,
            key="slope",
            help="Upsloping is usually normal; flat or downsloping are warning signs.",
        )
        if st.form_submit_button("Add treadmill results"):
            run_stage(2)


def stage3_form():
    with st.form("stage3"):
        st.markdown("#### Stage 3 · Invasive imaging")
        st.caption(
            "Hospital tests: dye X-ray of the arteries (fluoroscopy) and a nuclear (thallium) scan."
        )
        c1, c2 = st.columns(2)
        c1.selectbox(
            "Major vessels coloured by fluoroscopy",
            list(CA),
            format_func=CA.get,
            key="ca",
            help="Number of major vessels (0-3) visible with dye.",
        )
        c2.selectbox("Thallium scan result", list(THAL), format_func=THAL.get, key="thal")
        if st.form_submit_button("Add imaging results"):
            run_stage(3)


FORMS = {1: stage1_form, 2: stage2_form, 3: stage3_form}
NEXT_NAME = {2: "the treadmill stress test", 3: "invasive imaging"}

stage1_form()
for stage in (1, 2, 3):
    # Read fresh each time: submitting a later form inside this loop replaces
    # the results dictionary.
    results = st.session_state.results
    if stage not in results:
        break
    render_assessment(results[stage], predictor)
    if stage == 3:
        st.success("Screening complete: all three stages assessed.", icon="🏁")
        break
    nxt = stage + 1
    if results[stage].suggests_next_test:
        st.markdown(f"### ➡️ Recommended next step: {NEXT_NAME[nxt]}")
        FORMS[nxt]()
    else:
        with st.expander(f"Add {NEXT_NAME[nxt]} results anyway (optional)"):
            st.caption(
                "CardioStage doesn't expect this test to change the decision, but you "
                "can add the results to see the updated estimate."
            )
            FORMS[nxt]()
