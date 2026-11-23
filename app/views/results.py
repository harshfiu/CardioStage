"""Results page: how well CardioStage works, with the evidence behind each claim."""

import json

import pandas as pd
import streamlit as st

import charts
from cardiostage import config
from ui import DISCLAIMER

REP = config.REPORTS_DIR
# Extra chart data (calibration curves, case study, patient flow), exported by
# `python -m cardiostage.chart_data`. Committed, so this page needs no models.
CHART_DATA = json.loads((REP / "chart_data.json").read_text(encoding="utf-8"))


def chart(fig, caption: str | None = None):
    """Show a Plotly chart at full width, without the toolbar (hover still works)."""
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    if caption:
        st.caption(caption)


st.title("📊 How well does CardioStage work?")
st.caption(
    "All numbers are honest estimates on patients the models never trained on "
    "(out-of-fold cross-validation on 243 Cleveland patients, plus 614 patients "
    "from three unseen hospitals), plus the 61-patient sealed test set opened once "
    "at the end (see the 'Sealed test set' tab)."
)

# ---- Headline -----------------------------------------------------------------
strategies = pd.read_csv(REP / "phase5_strategies.csv", index_col=0)
staged = strategies.loc["CardioStage staged policy"]
everyone = strategies.loc["Everyone: stage 3 only"]
c1, c2, c3 = st.columns(3)
c1.metric(
    "Sick patients caught (recall)",
    f"{staged['recall']:.1%}",
    f"{(staged['recall'] - everyone['recall']) * 100:+.1f} pts vs everyone gets every test",
    delta_color="off",
)
c2.metric(
    "Patients needing invasive tests",
    f"{staged['needed_invasive']:.0%}",
    f"{(staged['needed_invasive'] - 1) * 100:.0f} pts vs everyone",
    delta_color="inverse",
)
c3.metric(
    "Healthy patients correctly cleared",
    f"{staged['specificity']:.0%}",
    f"{(staged['specificity'] - everyone['specificity']) * 100:+.1f} pts vs everyone",
    delta_color="off",
)

tab0, tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "Sealed test set",
        "Staged screening",
        "Calibration",
        "New hospitals",
        "Fairness",
        "Explanations",
    ]
)

with tab0:
    st.markdown("#### The final exam: 61 patients never used during development")
    final = pd.read_csv(REP / "final_test_strategies.csv", index_col=0)
    show_final = final[
        ["recall", "specificity", "sick_missed", "healthy_flagged", "needed_invasive"]
    ].copy()
    show_final["needed_invasive"] = show_final["needed_invasive"].map("{:.0%}".format)
    show_final.columns = [
        "Recall [95% CI]",
        "Specificity [95% CI]",
        "Sick missed",
        "Healthy flagged",
        "Need invasive",
    ]
    st.dataframe(show_final, width="stretch")
    chart(charts.final_test(pd.read_csv(REP / "final_test_stages.csv")))
    st.markdown(
        "No sick patient was missed (28 of 28), and the staged policy needed invasive "
        "tests for only half of the patients. Catching 28 of 28 does **not** prove 100% "
        "recall: the exact 95% interval is 87.7%–100%. Test scores came out above the "
        "cross-validation estimates; with 61 patients that's most likely chance, so the "
        "cross-validation numbers remain the honest expectation."
    )

with tab1:
    st.markdown("#### The staged policy matches all-tests accuracy with far fewer invasive tests")
    chart(charts.policy_flow(CHART_DATA["flow"]))
    st.markdown(
        "Every patient starts with a basic check-up. Low-risk patients are cleared and "
        "high-risk patients referred; only uncertain patients go on to the treadmill and "
        "then invasive imaging. All strategies are tuned to catch **97% of sick patients**."
    )
    show = strategies[["recall", "specificity", "fn", "fp", "needed_treadmill", "needed_invasive"]]
    show.columns = [
        "Recall",
        "Specificity",
        "Sick missed",
        "Healthy flagged",
        "Need treadmill",
        "Need invasive",
    ]
    st.dataframe(
        show.style.format(
            {
                "Recall": "{:.3f}",
                "Specificity": "{:.3f}",
                "Sick missed": "{:.0f}",
                "Healthy flagged": "{:.0f}",
                "Need treadmill": "{:.0%}",
                "Need invasive": "{:.0%}",
            }
        ),
        width="stretch",
    )
    chart(
        charts.auc_by_stage(pd.read_csv(REP / "phase4_stage_auc.csv", index_col=0)),
        caption="Ranking quality (ROC-AUC) by stage and model: invasive imaging adds the most.",
    )

with tab2:
    st.markdown("#### Predicted risk matches observed disease rates")
    chart(
        charts.calibration(CHART_DATA["calibration"], config.STAGE_NAMES),
        caption=charts.calibration_caption(CHART_DATA["calibration"]),
    )
    st.markdown(
        "Points near the diagonal mean honest probabilities: of patients told "
        '"30%", about 30% had heart disease. Average error: 3–5 percentage points.'
    )

with tab3:
    st.markdown("#### Tested unchanged at three hospitals it never saw")
    chart(charts.external_auc(pd.read_csv(REP / "phase6_external.csv")))
    st.markdown(
        "- **Hungary:** performance transfers fully.\n"
        "- **VA Long Beach:** clear drop (different population, ~28% of values missing).\n"
        "- **Switzerland:** undetermined: only 8 of 123 patients were healthy.\n\n"
        "Probabilities under-predict at high-disease hospitals; adjusting for the local "
        "disease rate fixes this (below). Decision cutoffs should be re-checked locally."
    )
    chart(
        charts.external_calibration(CHART_DATA["external_calibration"]),
        caption=charts.external_calibration_caption(CHART_DATA["external_calibration"]),
    )

with tab4:
    st.markdown("#### Performance by sex and age")
    chart(charts.fairness(pd.read_csv(REP / "phase6_fairness.csv", index_col=0)))
    st.markdown(
        "Ranking is equally good for women and men. Recall for women looks lower, but "
        "rests on 2 missed women out of 18: one with atypical chest pain cleared early "
        "(mirroring real-world under-diagnosis of women), one exactly at the threshold. "
        'Documented as a limitation rather than "fixed" with a rule fitted to two people.'
    )

with tab5:
    st.markdown("#### What drives each stage's predictions")
    chart(
        charts.importance(
            pd.read_csv(REP / "phase7_importance.csv", index_col=0), config.STAGE_NAMES
        )
    )
    st.markdown(
        "As test results arrive, the model relies less on demographics: the "
        "influence of sex falls from 13 → 7 → 4 percentage points."
    )
    st.markdown("#### Case study: a sick woman with atypical chest pain, cleared at the check-up")
    chart(
        charts.case_study(CHART_DATA["case_study"]),
        caption="Coral raises the estimate, blue lowers it. Describes what drove the model, "
        "not what causes disease.",
    )
    first = CHART_DATA["case_study"][0]
    st.markdown(
        f"In the honest evaluation (models that never saw her), her check-up risk was "
        f"**{first['oof_risk']:.1%}**, below the clearing cut-off, so the staged policy "
        f"reassured her even though she had heart disease. The bars explain the final model, "
        f"which was trained on all 243 patients including her, so it puts her slightly higher "
        f"({first['risk']:.1%}). Either way, her atypical chest pain and being female pulled "
        f"the estimate down: the same pattern behind real-world under-diagnosis of women."
    )

st.divider()
st.caption(DISCLAIMER)
