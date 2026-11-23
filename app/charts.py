"""
Plotly charts for the app, in the dark theme (docs/project/03-design-system.md).

The Results page used to show the static PNGs from reports/figures/ (light
background). These builders redraw the same evidence natively, so the
charts match the theme, scale to the page and show exact values on hover.
They read only committed files: the result tables in reports/ and
reports/chart_data.json (from `python -m cardiostage.chart_data`).
The PNGs remain the versions used in the README and docs.
"""

import re

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from cardiostage.explain import LABELS
from cardiostage.stats import parse_ci

# ---- Colour tokens (validated for the #080B12 surface) -----------------------
# Meaning colours, same as the landing site:
UP, DOWN = "#FF8A65", "#5B8FE8"  # coral raises risk, blue lowers it
MINT = "#8EE6C2"  # reassured / cleared
ONWARD = "rgba(91, 143, 232, 0.55)"  # sent on to the next test
# Categorical series, fixed order, never cycled. Passed the dataviz palette
# validator in dark mode (lightness band, chroma, CVD separation, contrast):
SERIES = ["#5B8FE8", "#D95926", "#199E70", "#C98500"]  # blue, orange, aqua, yellow
NEUTRAL = "#A9A196"  # reference series (e.g. "All patients", Cleveland)
# Text and structure:
TEXT_PRIMARY, TEXT_SECONDARY = "#F3EEE6", "#A9A196"  # warm off-white, warm grey
DARK_TEXT = "#1A0F06"  # text on light fills (mint, coral)
GRID = "rgba(243, 238, 230, 0.08)"
AXIS = "rgba(243, 238, 230, 0.22)"
REFERENCE = "rgba(243, 238, 230, 0.35)"  # diagonals, chance lines
SURFACE = "#080B12"  # used for 2 px gaps between touching fills
FONT = "Inter, system-ui, sans-serif"

MODEL_ORDER = ["Logistic Regression", "Random Forest", "XGBoost", "Ensemble (average of 3)"]


def _style(fig: go.Figure, height: int, legend: bool = True, panels: bool = False) -> go.Figure:
    """Shared dark styling: transparent background, recessive grid, readable text.

    panels=True (multi-panel charts with subplot titles): the legend gets its own
    row above the titles so the two never collide.
    """
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=20, t=100 if panels and legend else 50, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=13, color=TEXT_SECONDARY),
        hoverlabel=dict(
            bgcolor="#14161D", bordercolor=AXIS, font=dict(family=FONT, color=TEXT_PRIMARY)
        ),
        showlegend=legend,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.16 if panels else 1.06,
            xanchor="left",
            x=0,
            font=dict(size=13, color=TEXT_PRIMARY),
            bgcolor="rgba(0,0,0,0)",
        ),
    )
    # Tick text inherits the secondary ink from layout.font, so charts can still
    # promote category labels to primary ink (they're content, not decoration).
    axis = dict(gridcolor=GRID, linecolor=AXIS, zerolinecolor=AXIS)
    fig.update_xaxes(**axis, title_font=dict(size=13, color=TEXT_SECONDARY))
    fig.update_yaxes(**axis, title_font=dict(size=13, color=TEXT_SECONDARY))
    # Subplot titles are annotations: give them heading ink.
    fig.update_annotations(font=dict(family=FONT, size=14, color=TEXT_PRIMARY))
    return fig


def _diagonal(fig, row=None, col=None, name="Perfectly honest", show=True):
    fig.add_trace(
        go.Scatter(
            x=[0, 1],
            y=[0, 1],
            mode="lines",
            line=dict(color=REFERENCE, dash="dash", width=1),
            name=name,
            hoverinfo="skip",
            showlegend=show,
            legendgroup="diag",
        ),
        row=row,
        col=col,
    )


def signed(v: float) -> str:
    """'+4.2' / '−3.1'; values that round to zero show as '0.0', never '-0.0'."""
    return "0.0" if round(v, 1) == 0 else f"{v:+.1f}"


def _ci_error(values: list[dict], axis: str) -> dict:
    return {
        f"error_{axis}": dict(
            type="data",
            symmetric=False,
            array=[v["high"] - v["value"] for v in values],
            arrayminus=[v["value"] - v["low"] for v in values],
            thickness=2,
            width=5,
        )
    }


def _ci_label(fig, x_high: float, y, text: str, row: int, col: int):
    """Value label just past the end of the error bar, so text never sits on the whisker."""
    fig.add_trace(
        go.Scatter(
            x=[x_high + 0.012],
            y=[y],
            mode="text",
            text=[text],
            textposition="middle right",
            textfont=dict(color=TEXT_PRIMARY, size=12),
            hoverinfo="skip",
            showlegend=False,
            cliponaxis=False,
        ),
        row=row,
        col=col,
    )


# ---- Sealed test ------------------------------------------------------------
def final_test(stages) -> go.Figure:
    """Sealed-test ROC-AUC (95% CI) per stage vs the cross-validation estimate."""
    ci = [parse_ci(t) for t in stages["test_roc_auc"]]
    s = stages["stage"].tolist()
    ticks = [f"Stage {n}<br>{name}" for n, name in zip(s, stages["name"])]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=[n - 0.08 for n in s],
            y=stages["cv_roc_auc"],
            mode="markers",
            marker=dict(symbol="diamond", size=12, color=SERIES[1]),
            name="Cross-validation estimate (243 patients)",
            hovertemplate="Cross-validation: %{y:.3f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[n + 0.08 for n in s],
            y=[c["value"] for c in ci],
            mode="markers+text",
            marker=dict(size=12, color=SERIES[0]),
            text=[f"{c['value']:.3f}" for c in ci],
            textposition="middle right",
            textfont=dict(color=TEXT_PRIMARY),
            name="Sealed test set (61 patients, 95% CI)",
            customdata=[[c["low"], c["high"]] for c in ci],
            hovertemplate="Sealed test: %{y:.3f} [%{customdata[0]:.3f}, %{customdata[1]:.3f}]<extra></extra>",
            **_ci_error(ci, "y"),
        )
    )
    fig.update_xaxes(tickvals=s, ticktext=ticks, range=[0.5, 3.6], showgrid=False)
    fig.update_yaxes(title_text="ROC-AUC (1.0 = perfect ranking)", range=[0.6, 1.02])
    return _style(fig, 420)


# ---- Staged screening ---------------------------------------------------------
def policy_flow(flow: list) -> go.Figure:
    """Where the 243 training patients stop: reassured, referred or sent onward."""
    labels = [f"Stage {f['stage']}: {f['name'].lstrip('+ ')}" for f in flow]
    fig = go.Figure()
    for key, name, color, ink in [
        ("cleared", "Reassured (low risk)", MINT, DARK_TEXT),
        ("referred", "Referred (high risk)", UP, DARK_TEXT),
        ("onward", "Sent on to the next test", ONWARD, TEXT_PRIMARY),
    ]:
        values = [f[key] for f in flow]
        fig.add_trace(
            go.Bar(
                y=labels,
                x=values,
                orientation="h",
                name=name,
                marker=dict(color=color, line=dict(color=SURFACE, width=2)),
                text=[str(v) if v else "" for v in values],
                textposition="inside",
                insidetextanchor="middle",
                textfont=dict(color=ink, size=13),
                customdata=[f["reached"] for f in flow],
                hovertemplate=f"%{{y}}<br>{name}: %{{x}} of %{{customdata}}<extra></extra>",
            )
        )
    fig.update_layout(barmode="stack", bargap=0.35)
    fig.update_yaxes(
        autorange="reversed", tickfont=dict(size=14, color=TEXT_PRIMARY), showgrid=False
    )
    fig.update_xaxes(title_text="Patients", range=[0, flow[0]["reached"]])
    return _style(fig, 300)


def auc_by_stage(table) -> go.Figure:
    """Nested-CV ROC-AUC (mean ± sd over 15 outer folds) per candidate model and stage."""
    stages = [1, 2, 3]
    fig = go.Figure()
    offsets = [-0.15, -0.05, 0.05, 0.15]
    for color, off, model in zip(SERIES, offsets, MODEL_ORDER):
        parsed = [
            [float(x) for x in re.findall(r"\d+\.\d+", table.loc[model, f"stage_{s}"])]
            for s in stages
        ]
        means, sds = [p[0] for p in parsed], [p[1] for p in parsed]
        fig.add_trace(
            go.Scatter(
                x=[s + off for s in stages],
                y=means,
                mode="lines+markers",
                name=model,
                line=dict(color=color, width=2),
                marker=dict(size=9, color=color, line=dict(color=SURFACE, width=2)),
                error_y=dict(type="data", array=sds, thickness=1.5, width=4),
                customdata=sds,
                hovertemplate=f"{model}<br>ROC-AUC %{{y:.3f}} ± %{{customdata:.3f}}<extra></extra>",
            )
        )
    fig.update_xaxes(
        tickvals=stages,
        ticktext=["Stage 1<br>Basic check-up", "Stage 2<br>+ Treadmill", "Stage 3<br>+ Imaging"],
        range=[0.6, 3.4],
        showgrid=False,
    )
    fig.update_yaxes(title_text="ROC-AUC (nested CV, mean ± sd)", range=[0.6, 1.0])
    return _style(fig, 420)


# ---- Calibration --------------------------------------------------------------
_VARIANT_STYLE = {
    "sigmoid": (SERIES[0], "Calibrated (sigmoid)"),
    "uncalibrated": (SERIES[1], "Uncalibrated"),
}


def calibration(cal: dict, stage_names: dict) -> go.Figure:
    """Reliability curves per stage (729 pooled out-of-fold predictions each)."""
    stages = sorted(cal, key=int)
    fig = make_subplots(
        rows=1,
        cols=len(stages),
        shared_yaxes=True,
        horizontal_spacing=0.04,
        subplot_titles=[f"Stage {s}: {stage_names[int(s)].lstrip('+ ')}" for s in stages],
    )
    for i, s in enumerate(stages, start=1):
        _diagonal(fig, 1, i, show=i == 1)
        for variant in ("sigmoid", "uncalibrated"):
            color, name = _VARIANT_STYLE[variant]
            v = cal[s]["variants"][variant]
            fig.add_trace(
                go.Scatter(
                    x=[p["predicted"] for p in v["points"]],
                    y=[p["actual"] for p in v["points"]],
                    mode="lines+markers",
                    line=dict(color=color, width=2),
                    marker=dict(size=8, color=color, line=dict(color=SURFACE, width=2)),
                    name=name,
                    legendgroup=variant,
                    showlegend=i == 1,
                    hovertemplate=(
                        f"{name}<br>Predicted %{{x:.0%}} → actually sick %{{y:.0%}}<extra></extra>"
                    ),
                ),
                row=1,
                col=i,
            )
    fig.update_xaxes(range=[0, 1], tickformat=".0%", title_text="Predicted risk")
    fig.update_yaxes(range=[0, 1], tickformat=".0%")
    fig.update_yaxes(title_text="Actually had heart disease", row=1, col=1)
    return _style(fig, 470, panels=True)


# ---- New hospitals ------------------------------------------------------------
HOSPITAL_COLORS = {
    "Cleveland (internal, out-of-fold)": NEUTRAL,
    "Hungary": SERIES[0],
    "VA Long Beach": SERIES[1],
    "Switzerland": SERIES[2],
}
HOSPITAL_LABELS = {"Cleveland (internal, out-of-fold)": "Cleveland (home, unseen patients)"}


def external_auc(table) -> go.Figure:
    """ROC-AUC with 95% CI at the home hospital and three unseen hospitals."""
    stages = [1, 2]
    fig = make_subplots(
        rows=1,
        cols=2,
        shared_yaxes=True,
        horizontal_spacing=0.04,
        subplot_titles=["Stage 1: Basic check-up", "Stage 2: + Treadmill stress test"],
    )
    for col, stage in enumerate(stages, start=1):
        sub = table[table["stage"] == stage]
        for _, r in sub.iterrows():
            label = HOSPITAL_LABELS.get(r["hospital"], r["hospital"])
            ci = [{"value": r["auc_value"], "low": r["auc_low"], "high": r["auc_high"]}]
            fig.add_trace(
                go.Scatter(
                    x=[r["auc_value"]],
                    y=[label],
                    mode="markers",
                    marker=dict(size=11, color=HOSPITAL_COLORS[r["hospital"]]),
                    hovertemplate=(
                        f"{label}, stage {stage}<br>ROC-AUC {r['auc_value']:.3f} "
                        f"[{r['auc_low']:.3f}, {r['auc_high']:.3f}]<br>"
                        f"{int(r['n'])} patients, {r['disease_rate']:.0%} with disease<extra></extra>"
                    ),
                    showlegend=False,
                    **_ci_error(ci, "x"),
                ),
                row=1,
                col=col,
            )
            _ci_label(fig, r["auc_high"], label, f"{r['auc_value']:.3f} (n={int(r['n'])})", 1, col)
        fig.add_vline(x=0.5, line=dict(color=REFERENCE, dash="dash", width=1), row=1, col=col)
    fig.update_xaxes(
        range=[0.4, 1.2],
        tickvals=[0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        title_text="ROC-AUC (95% CI) · dashed = coin flip",
    )
    fig.update_yaxes(
        autorange="reversed", tickfont=dict(size=13, color=TEXT_PRIMARY), showgrid=False
    )
    return _style(fig, 340, legend=False)


def external_calibration(ext: dict) -> go.Figure:
    """Stage-1 calibration at each unseen hospital, before and after the prior shift."""
    hospitals = list(ext)
    fig = make_subplots(
        rows=1,
        cols=len(hospitals),
        shared_yaxes=True,
        horizontal_spacing=0.04,
        subplot_titles=[f"{h} ({ext[h]['disease_rate']:.0%} with disease)" for h in hospitals],
    )
    styles = [
        ("as_trained", SERIES[1], "As trained (Cleveland's 46% disease rate)"),
        ("after_prior_shift", SERIES[0], "Adjusted for the local disease rate"),
    ]
    for i, h in enumerate(hospitals, start=1):
        _diagonal(fig, 1, i, show=i == 1)
        for key, color, name in styles:
            pts = ext[h][key]["points"]
            fig.add_trace(
                go.Scatter(
                    x=[p["predicted"] for p in pts],
                    y=[p["actual"] for p in pts],
                    mode="lines+markers",
                    line=dict(color=color, width=2),
                    marker=dict(size=8, color=color, line=dict(color=SURFACE, width=2)),
                    name=name,
                    legendgroup=key,
                    showlegend=i == 1,
                    hovertemplate=f"{name}<br>Predicted %{{x:.0%}} → actually sick %{{y:.0%}}<extra></extra>",
                ),
                row=1,
                col=i,
            )
    fig.update_xaxes(range=[0, 1], tickformat=".0%", title_text="Predicted risk")
    fig.update_yaxes(range=[0, 1.02], tickformat=".0%")
    fig.update_yaxes(title_text="Actually had heart disease", row=1, col=1)
    return _style(fig, 470, panels=True)


# ---- Fairness -----------------------------------------------------------------
def fairness(table) -> go.Figure:
    """Staged-policy recall and specificity (95% CI) by sex and age band."""
    groups = list(table.index)
    labels = [f"{g} (n={table.loc[g, 'n']}, sick={table.loc[g, 'n_sick']})" for g in groups]

    def color(g):
        return NEUTRAL if g == "All patients" else SERIES[0] if g.startswith("Sex") else SERIES[1]

    fig = make_subplots(
        rows=1,
        cols=2,
        shared_yaxes=True,
        horizontal_spacing=0.04,
        subplot_titles=["Recall: sick patients caught", "Specificity: healthy patients cleared"],
    )
    for col, metric in enumerate(["policy_recall", "policy_specificity"], start=1):
        for g, label in zip(groups, labels):
            ci = [parse_ci(table.loc[g, metric])]
            fig.add_trace(
                go.Scatter(
                    x=[ci[0]["value"]],
                    y=[label],
                    mode="markers",
                    marker=dict(size=11, color=color(g)),
                    hovertemplate=(
                        f"{g}<br>{ci[0]['value']:.3f} [{ci[0]['low']:.3f}, {ci[0]['high']:.3f}]"
                        "<extra></extra>"
                    ),
                    showlegend=False,
                    **_ci_error(ci, "x"),
                ),
                row=1,
                col=col,
            )
            _ci_label(fig, ci[0]["high"], label, f"{ci[0]['value']:.2f}", 1, col)
    fig.update_xaxes(
        range=[0, 1.13],
        tickvals=[0, 0.2, 0.4, 0.6, 0.8, 1.0],
        title_text="95% CI (Cleveland, out-of-fold)",
    )
    fig.update_yaxes(
        autorange="reversed", tickfont=dict(size=13, color=TEXT_PRIMARY), showgrid=False
    )
    return _style(fig, 380, legend=False)


# ---- Explanations -------------------------------------------------------------
def importance(table, stage_names: dict) -> go.Figure:
    """Mean |SHAP| per measurement and stage (percentage points), stacked vertically."""
    columns = ["stage_1", "stage_2", "stage_3"]
    counts = [int(table[c].notna().sum()) for c in columns]
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.07,
        row_heights=counts,
        subplot_titles=[f"Stage {i}: {stage_names[i].lstrip('+ ')}" for i in (1, 2, 3)],
    )
    for row, c in enumerate(columns, start=1):
        s = (table[c].dropna() * 100).sort_values()
        names = [LABELS.get(f, f) for f in s.index]
        fig.add_trace(
            go.Bar(
                x=s.values,
                y=names,
                orientation="h",
                marker=dict(color=SERIES[0]),
                text=[f"{v:.1f}" for v in s.values],
                textposition="outside",
                textfont=dict(color=TEXT_PRIMARY, size=12),
                cliponaxis=False,
                hovertemplate="%{y}: %{x:.1f} pts on average<extra></extra>",
                showlegend=False,
            ),
            row=row,
            col=1,
        )
    fig.update_yaxes(tickfont=dict(size=13, color=TEXT_PRIMARY), showgrid=False)
    fig.update_xaxes(range=[0, float(table.max().max()) * 100 * 1.18])
    fig.update_xaxes(title_text="Average impact on risk (percentage points)", row=3, col=1)
    fig.update_layout(bargap=0.3)
    return _style(fig, 34 * sum(counts) + 170, legend=False)


def case_study(cases: list) -> go.Figure:
    """The missed woman explained at stages 1 and 3 (top 8 contributions each)."""
    fig = make_subplots(
        rows=len(cases),
        cols=1,
        vertical_spacing=0.16,
        subplot_titles=[
            f"Stage {c['stage']}: {c['name'].lstrip('+ ')}: typical patient "
            f"{c['baseline']:.0%} → her estimate {c['risk']:.0%}"
            for c in cases
        ],
    )
    limit = max(max(abs(k["points"]) for k in c["contributions"]) for c in cases) * 1.35
    for row, c in enumerate(cases, start=1):
        items = c["contributions"][::-1]
        values = [k["points"] for k in items]
        fig.add_trace(
            go.Bar(
                x=values,
                y=[f"{k['label']} = {k['value']}" for k in items],
                orientation="h",
                marker=dict(color=[UP if v > 0 else DOWN for v in values]),
                text=[signed(v) for v in values],
                textposition="outside",
                textfont=dict(color=TEXT_PRIMARY, size=12),
                cliponaxis=False,
                hovertemplate="%{y}<br>%{x:+.1f} percentage points<extra></extra>",
                showlegend=False,
            ),
            row=row,
            col=1,
        )
    fig.update_xaxes(range=[-limit, limit], zeroline=True, zerolinecolor=TEXT_SECONDARY)
    fig.update_xaxes(title_text="Contribution to risk (percentage points)", row=len(cases), col=1)
    fig.update_yaxes(tickfont=dict(size=13, color=TEXT_PRIMARY), showgrid=False, automargin=True)
    fig.update_layout(bargap=0.3)
    return _style(fig, 2 * (36 * 8) + 200, legend=False)


# ---- Captions (numbers as text: readable at any width, and a text alternative) ----
def calibration_caption(cal: dict) -> str:
    parts = []
    for s in sorted(cal, key=int):
        v, chosen = cal[s]["variants"], cal[s]["chosen"]
        used = "calibrated" if chosen == "sigmoid" else "uncalibrated"
        parts.append(
            f"stage {s}: {v['sigmoid']['ece']:.3f} calibrated vs "
            f"{v['uncalibrated']['ece']:.3f} uncalibrated (app uses {used})"
        )
    return "Average calibration error (ECE, lower is better): " + "; ".join(parts) + "."


def external_calibration_caption(ext: dict) -> str:
    parts = [
        f"{h} {e['as_trained']['ece']:.3f} → {e['after_prior_shift']['ece']:.3f}"
        for h, e in ext.items()
    ]
    return "Calibration error (ECE) before → after adjusting: " + "; ".join(parts) + "."
