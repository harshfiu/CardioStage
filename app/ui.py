"""Shared pieces for the CardioStage Streamlit pages."""

import plotly.graph_objects as go
import streamlit as st

from cardiostage import config
from cardiostage.integrity import IntegrityError
from cardiostage.predictor import CardioStagePredictor, ModelsNotFoundError

UP, DOWN = "#eb6834", "#2a78d6"

DISCLAIMER = (
    "**Educational project, not a medical device.** CardioStage was trained on 243 patients "
    "from a single 1980s US hospital dataset. It must not be used to diagnose, treat, or "
    "make decisions about any real person. If you have chest pain or heart concerns, "
    "contact a doctor or emergency services."
)


@st.cache_resource(show_spinner="Loading CardioStage models (first time only, ~15 seconds)...")
def get_predictor() -> CardioStagePredictor:
    # cache_resource: load the models ONCE and share them across every page,
    # rerun and visitor, instead of reloading on each click.
    return CardioStagePredictor.load()


def load_predictor_or_stop() -> CardioStagePredictor:
    try:
        return get_predictor()
    except ModelsNotFoundError as e:
        st.error(f"{e}")
        st.stop()
    except IntegrityError as e:
        # A model file failed its SHA-256 check: never load it (SEC-05).
        st.error(
            f"**Model integrity check failed.** {e}  \n"
            "Rebuild the models with `python -m cardiostage.train_all`."
        )
        st.stop()


def contribution_chart(explanation, top: int = 8) -> go.Figure:
    """Horizontal bars: what pushed this patient's risk up (orange) or down (blue)."""
    t = explanation.head(top).iloc[::-1]
    labels = [f"{r.label} = {r.value}" for r in t.itertuples()]
    values = t["contribution"] * 100
    fig = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker_color=[UP if v > 0 else DOWN for v in values],
            text=[f"{v:+.1f}" for v in values],
            textposition="outside",
            hovertemplate="%{y}<br>%{x:+.1f} percentage points<extra></extra>",
        )
    )
    limit = max(abs(values).max() * 1.35, 5)
    fig.update_layout(
        height=40 * len(t) + 80,
        margin=dict(l=10, r=10, t=10, b=40),
        xaxis=dict(
            title="Contribution to risk (percentage points)",
            range=[-limit, limit],
            zeroline=True,
            zerolinecolor="#52514e",
            gridcolor="#ebeae6",
        ),
        yaxis=dict(automargin=True),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(size=13),
        showlegend=False,
    )
    return fig


ZONE_STYLE = {
    "low": (st.success, "✅"),
    "clear": (st.success, "✅"),
    "high": (st.error, "⚠️"),
    "refer": (st.error, "⚠️"),
    "uncertain": (st.info, "🔎"),
}


def render_assessment(result):
    """The result card for one stage."""
    with st.container(border=True):
        st.subheader(f"Stage {result.stage} result · {config.STAGE_NAMES[result.stage]}")
        c1, c2, c3 = st.columns([1, 1, 2])
        c1.metric(
            "Estimated risk",
            f"{result.risk:.0%}",
            help="Calibrated probability of heart disease (>50% narrowing of a "
            "major artery on angiography), for a patient like this in the "
            "training data.",
        )
        c2.metric(
            "Plausible range",
            f"{result.range_low:.0%} – {result.range_high:.0%}",
            help="Spread of predictions from 20 versions of the model, each trained "
            "on a different 80% of patients. Shown for transparency only: it "
            "proved a weak error detector, so it does not change decisions.",
        )
        with c3:
            box, icon = ZONE_STYLE[result.zone]
            box(f"**{result.headline}**  \n{result.recommendation}", icon=icon)

        z = result.thresholds
        if result.stage < 3:
            st.caption(
                f"This stage clears below {z['rule_out_below']:.1%} and refers from "
                f"{z['rule_in_from']:.1%}; in between, the next test is suggested."
            )
        else:
            st.caption(
                f"Final screening threshold: {z['screening_threshold']:.1%} "
                f"(set to catch 97% of sick patients)."
            )

        if result.unusual:
            st.warning(
                "**Unusual patient: treat this estimate with extra caution.** "
                "The model has seen few or no patients like this:\n\n"
                + "\n".join(f"- {r}" for r in result.unusual),
                icon="🧭",
            )
        if result.not_measured:
            names = ", ".join(
                result.explanation.set_index("feature").loc[result.not_measured, "label"]
            )
            st.caption(f"Not measured: {names}. The model assumed a typical value.")

        st.markdown("**Why this estimate?**")
        st.write(result.summary)
        st.plotly_chart(
            contribution_chart(result.explanation),
            width="stretch",
            config={"displayModeBar": False},
        )
        with st.expander("Full breakdown and how to read it"):
            table = result.explanation[["label", "value", "contribution"]].copy()
            table["contribution"] = (table["contribution"] * 100).map("{:+.1f} pts".format)
            table.columns = ["Measurement", "Value", "Effect on risk"]
            st.dataframe(table, hide_index=True, width="stretch")
            st.caption(
                f"Starting from a typical patient's risk ({result.baseline:.0%}), each "
                "measurement's effect is added; together they sum exactly to this "
                "patient's estimate (SHAP values). These describe what drove the "
                "**model**, not what causes disease: e.g. 'female: lower' reflects "
                "patterns in this referral dataset, not a protective effect you could change."
            )
