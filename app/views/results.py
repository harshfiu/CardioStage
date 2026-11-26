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

st.info(
    "**Stage 1 is now version 2**, learned from five hospitals (Cleveland, Hungary, "
    "Switzerland, VA Long Beach, Iran). Stages 2-3 are unchanged. The first tab shows the v2 "
    "evidence; the other tabs document the original v1 analysis (Cleveland only).",
    icon="🆕",
)

tabv2, tabllm, tab0, tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "Version 2",
        "vs chatbots",
        "Sealed test set",
        "Staged screening",
        "Calibration",
        "New hospitals",
        "Fairness",
        "Explanations",
    ]
)

with tabv2:
    st.markdown("#### Version 2: learning from five hospitals")
    st.markdown(
        "Tested on 303 modern patients from Iran, v1 (trained on 1980s Cleveland) missed about "
        "a third of sick patients, mainly because it had learned that *typical angina* means "
        "low risk. Version 2's check-up model learned from all five hospitals instead."
    )
    second = pd.read_csv(REP / "v2_final_second_look_stage1.csv")
    chart(
        charts.v2_vs_v1(second),
        caption="Same 245 sealed-test patients for both versions (20% of every hospital; "
        "Cleveland's are v1's original test patients).",
    )
    show = second[second["hospital"] == "All hospitals"].set_index("version")
    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Ranking quality (AUC)",
        f"{show.loc['v2', 'auc_value']:.2f}",
        f"{show.loc['v2', 'auc_value'] - show.loc['v1', 'auc_value']:+.2f} vs v1",
        delta_color="normal",  # higher is better: green when up
    )
    c2.metric(
        "Calibration error (ECE)",
        f"{show.loc['v2', 'ece']:.3f}",
        f"{show.loc['v2', 'ece'] - show.loc['v1', 'ece']:+.3f} vs v1",
        delta_color="inverse",
    )
    c3.metric(
        "Sick patients wrongly cleared",
        f"{int(show.loc['v2', 'cleared_but_sick'])} of 145",
        # Fewer is better: show the change from v1 so the arrow points the right way.
        f"{int(show.loc['v2', 'cleared_but_sick']) - int(show.loc['v1', 'cleared_but_sick']):+d} vs v1",
        delta_color="inverse",
    )
    per = second[second["hospital"] != "All hospitals"].pivot(
        index="hospital", columns="version", values="cleared_but_sick"
    )
    per.columns = ["Sick wrongly cleared (v1)", "Sick wrongly cleared (v2)"]
    st.dataframe(per, width="stretch")
    ta = pd.read_csv(REP / "v2_final_second_look_typical_angina.csv").set_index("group")
    ta = ta.rename(
        columns={
            "n": "Patients",
            "actual": "Actually sick",
            "predicted_v1": "v1 predicted",
            "predicted_v2": "v2 predicted",
        }
    )
    st.markdown("##### Typical angina: actual vs predicted")
    st.dataframe(
        ta.style.format(
            {"Actually sick": "{:.0%}", "v1 predicted": "{:.0%}", "v2 predicted": "{:.0%}"}
        ),
        width="stretch",
    )
    st.markdown(
        "- **Honest weak spot: VA Long Beach.** v2 ranks its 40 sealed patients worse than v1 "
        "(0.71 vs 0.83). v1 was unusually lucky there (0.69 on VA's other 159 patients); on "
        "hospitals it never saw, both versions score about 0.70 at VA.\n"
        "- **A flaw found and fixed:** pooling first taught the model that *lower* cholesterol "
        "means more risk, because Iran's cholesterol is estimated and low in a modern population. "
        "Iran's estimated cholesterol is now treated as not measured.\n"
        "- **Typical angina is still underestimated** in modern patients (Iran: 97% sick, v2 "
        "predicts ~81%), so the app keeps its warning.\n"
        "- **Two looks at the sealed test:** the first look is the unbiased exam of the first v2 "
        "(AUC 0.84, 1 sick patient wrongly cleared). The numbers above are a **second look** at "
        "the fixed model, slightly optimistic because the first look prompted the fix. The cost "
        "of v2: at Cleveland, 92% of patients need the treadmill test (v1: 69%)."
    )

with tabllm:
    st.markdown("#### Why not just ask a chatbot? We tested it.")
    st.markdown(
        "The same 245 sealed-test patients and the same six check-up facts were pasted, 14-15 "
        "patients per fresh chat, into **free ChatGPT** and **paid Claude (Opus 5.5)**, asking "
        "each for the chance of significant coronary artery disease. The prompt and every "
        "metric were committed before any patient was sent, and each chatbot got one try."
    )
    llm = pd.read_csv(REP / "llm_compare.csv")
    chart(
        charts.chatbots(llm),
        caption="Ranking quality (ROC-AUC) with 95% intervals, same patients for all three.",
    )
    allh = llm[llm["group"] == "All hospitals"].set_index("source")
    names = {s: n for s, n, _ in charts.CHATBOT_SERIES}
    table = pd.DataFrame(
        {
            "Ranking (AUC) [95% CI]": allh["roc_auc"],
            "AUC vs CardioStage [95% CI]": allh["auc_vs_cardiostage"].fillna(""),
            "Calibration error": allh["ece"].map("{:.3f}".format),
            "Average predicted": allh["mean_predicted"].map("{:.0%}".format),
            "Reassured (below 14.4%)": allh["share_cleared"].map("{:.0%}".format),
            "Sick among the reassured": allh["cleared_but_sick"].astype(int),
        }
    ).loc[[s for s, _, _ in charts.CHATBOT_SERIES]]
    table.index = [names[s] for s in table.index]
    st.dataframe(table, width="stretch")
    st.caption(
        f"Actually sick: {allh.loc['CardioStage v2', 'disease_rate']:.0%} of the 245. "
        "A confidence interval for a difference that includes 0 means no clear difference."
    )
    st.markdown(
        "- **Ranking:** paid Claude ranked patients as well as CardioStage (no clear "
        "difference); free ChatGPT was clearly worse, especially at Hungary and Switzerland.\n"
        "- **Honest percentages:** both chatbots under-estimated risk across the board "
        "(about 50% predicted where 59% were sick). CardioStage's calibration error was about "
        "three times smaller.\n"
        "- **Safety:** CardioStage reassured the most patients (11%) and none were sick; the "
        "chatbots reassured fewer and included 1 (Claude) or 3 (ChatGPT) sick patients. "
        "Small numbers, and the 14.4% cut-off was tuned for CardioStage, but a chatbot's "
        "percentages come with no tested cut-off at all.\n"
        "- **Where the chatbots win:** among typical-angina patients (CardioStage's known weak "
        "spot) both chatbots told sick from healthy better, although Claude's average estimate "
        "for them was far too low (54% vs 82% actually sick).\n"
        "- **A memorisation hint:** Claude did slightly better than CardioStage on Cleveland, a "
        "famous public dataset, and worse on the lesser-known Iranian data. Consistent with "
        "having seen Cleveland in training, but the groups are small: a hint, not proof."
    )
    st.caption(
        "What this is: what a person gets from these chatbots, not the best any AI can do. "
        "Free ChatGPT vs paid Claude; one try each; several patients per message. "
        "CardioStage's numbers are its labelled second look at the sealed test. "
        "Prompts, replies and log: data/llm_compare/."
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
