"""
Tests for the Results page's native charts (app/charts.py) and their data
export (reports/chart_data.json, from `python -m cardiostage.chart_data`).

None of these need the trained models: the chart data is committed.
"""

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from cardiostage import config

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))  # the app's modules import each other by name

import charts  # noqa: E402

REP = config.REPORTS_DIR
DATA = json.loads((REP / "chart_data.json").read_text(encoding="utf-8"))


# ---- the exported data agrees with the published reports ---------------------
def test_calibration_ece_matches_phase5_report():
    table = pd.read_csv(REP / "phase5_calibration.csv")
    for stage, entry in DATA["calibration"].items():
        for variant, v in entry["variants"].items():
            ref = table[(table.stage == int(stage)) & (table.variant == variant)].ece.item()
            assert v["ece"] == pytest.approx(ref, abs=1e-4)
            assert all(0 <= p["predicted"] <= 1 and 0 <= p["actual"] <= 1 for p in v["points"])


def test_chosen_calibration_matches_zones_file():
    zones = json.loads((REP / "phase5_zones.json").read_text())
    for stage, entry in DATA["calibration"].items():
        assert entry["chosen"] in entry["variants"]
        if "methods" in zones:
            assert entry["chosen"] == zones["methods"][stage]


def test_external_calibration_matches_phase6_report():
    ext = pd.read_csv(REP / "phase6_external.csv")
    assert set(DATA["external_calibration"]) == set(config.EXTERNAL_HOSPITALS)
    for hospital, e in DATA["external_calibration"].items():
        row = ext[(ext.stage == 1) & (ext.hospital == hospital)].iloc[0]
        assert e["n"] == row.n
        assert e["as_trained"]["ece"] == pytest.approx(row.ece, abs=1e-4)
        assert e["after_prior_shift"]["ece"] == pytest.approx(row.ece_after_prior_shift, abs=1e-4)


def test_flow_matches_site_and_strategy_report():
    site = json.loads((ROOT / "site" / "assets" / "data" / "site-data.json").read_text())
    assert DATA["flow"] == site["flow"]
    staged = pd.read_csv(REP / "phase5_strategies.csv", index_col=0).loc[
        "CardioStage staged policy"
    ]
    flow = DATA["flow"]
    assert flow[2]["reached"] / flow[0]["reached"] == pytest.approx(staged["needed_invasive"])


def test_case_study_is_the_cleared_woman():
    stage1, stage3 = DATA["case_study"]
    assert (stage1["stage"], stage3["stage"]) == (1, 3)
    zones = json.loads((REP / "phase5_zones.json").read_text())["zones"]
    # Cleared at the check-up by her honest out-of-fold risk...
    assert stage1["oof_risk"] < zones["1"]["rule_out_below"]
    # ...while the final model (which saw her in training) explains a nearby value.
    assert abs(stage1["risk"] - stage1["oof_risk"]) < 0.05
    sex = {c["label"]: c["value"] for c in stage1["contributions"]}["Sex"]
    assert sex == "female"
    assert all(len(c["contributions"]) <= 8 for c in DATA["case_study"])


# ---- every chart builds from committed files ----------------------------------
def test_all_results_charts_build():
    figs = [
        charts.final_test(pd.read_csv(REP / "final_test_stages.csv")),
        charts.policy_flow(DATA["flow"]),
        charts.auc_by_stage(pd.read_csv(REP / "phase4_stage_auc.csv", index_col=0)),
        charts.calibration(DATA["calibration"], config.STAGE_NAMES),
        charts.external_auc(pd.read_csv(REP / "phase6_external.csv")),
        charts.external_calibration(DATA["external_calibration"]),
        charts.fairness(pd.read_csv(REP / "phase6_fairness.csv", index_col=0)),
        charts.importance(
            pd.read_csv(REP / "phase7_importance.csv", index_col=0), config.STAGE_NAMES
        ),
        charts.case_study(DATA["case_study"]),
        charts.v2_vs_v1(pd.read_csv(REP / "v2_final_second_look_stage1.csv")),
        charts.chatbots(pd.read_csv(REP / "llm_compare.csv")),
    ]
    for fig in figs:
        assert fig.data, "chart has no traces"
        assert fig.layout.paper_bgcolor == "rgba(0,0,0,0)"  # dark page shows through


def test_signed_never_shows_negative_zero():
    assert charts.signed(-0.04) == "0.0"
    assert charts.signed(4.21) == "+4.2"
    assert charts.signed(-3.06) == "-3.1"


def test_results_page_renders_without_models():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app" / "views" / "results.py"), default_timeout=60).run()
    assert not at.exception
    assert len(at.get("plotly_chart")) == 11  # 9 v1 charts + Version 2 + vs chatbots
    assert not at.get("imgs")  # no static PNGs on the Results page any more
