"""
Tests for the landing site (site/) and the app's static files.

Guarantees checked:
  - strict Content-Security-Policy, no inline scripts/styles, no external
    resources (privacy: the site makes no third-party requests)
  - every number in the site data matches the project's real reports
  - vendored libraries and their licences are present
  - the app's static folder serves fonts only
"""

import json
import re
from pathlib import Path

import pandas as pd
import pytest

from cardiostage import config

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
DATA = json.loads((SITE / "assets" / "data" / "site-data.json").read_text(encoding="utf-8"))


def site_text_files():
    return [
        p
        for p in SITE.rglob("*")
        if p.suffix in {".html", ".css", ".js"} and "vendor" not in p.parts
    ]


# ---------------------------------------------------------------- security --
def test_index_has_strict_csp():
    html = (SITE / "index.html").read_text(encoding="utf-8")
    csp = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', html).group(1)
    assert "default-src 'self'" in csp and "script-src 'self'" in csp
    assert "object-src 'none'" in csp and "base-uri 'none'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp


@pytest.mark.parametrize("page", ["index.html", "licenses/NOTICES.html"])
def test_no_inline_scripts_or_style_attributes(page):
    html = (SITE / page).read_text(encoding="utf-8")
    inline_scripts = [
        s
        for s in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)
        if s.strip()
    ]
    assert inline_scripts == []
    assert re.search(r"\sstyle=\"", html) is None
    assert "<style" not in html


def test_no_external_resources_loaded():
    """Links (<a href>) may point anywhere; nothing may be LOADED from another origin."""
    pattern = re.compile(
        r"<(?:script|link|img|iframe|source|video|audio)[^>]+(?:src|href)=\"(?:https?:)?//"
        r"|url\(\s*['\"]?(?:https?:)?//"
        r"|@import\s+['\"]?(?:https?:)?//"
        r"|fetch\(\s*['\"](?:https?:)?//",
        re.I,
    )
    offenders = [
        str(p.relative_to(SITE))
        for p in site_text_files()
        if pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_vendored_libraries_and_licences_present():
    for name in [
        "gsap.min.js",
        "ScrollTrigger.min.js",
        "DrawSVGPlugin.min.js",
        "SplitText.min.js",
        "lenis.min.js",
        "lenis.css",
        "three.min.js",
        "vanta.net.min.js",
    ]:
        assert (SITE / "vendor" / name).is_file(), name
    for lic in ["lenis", "three", "vanta", "fontsource__fraunces", "fontsource__inter"]:
        assert (SITE / "licenses" / f"{lic}-LICENSE.txt").is_file(), lic
    assert (SITE / "licenses" / "NOTICES.html").is_file()


def test_app_static_folder_serves_fonts_only():
    files = [p for p in (ROOT / "app" / "static").rglob("*") if p.is_file()]
    assert files, "fonts missing"
    assert all(p.suffix == ".woff2" for p in files), [p.name for p in files]


# ------------------------------------------------- data matches the reports --
def test_strategy_numbers_match_reports():
    cv = pd.read_csv(config.REPORTS_DIR / "phase5_strategies.csv", index_col=0)
    staged = cv.loc["CardioStage staged policy"]
    s = DATA["strategies"]["cv"]["staged"]
    assert s["needed_invasive"] == pytest.approx(staged["needed_invasive"])
    assert s["recall"] == pytest.approx(staged["recall"])
    assert s["sick_missed"] == int(staged["fn"])
    assert DATA["strategies"]["cv"]["invasive_difference"]["value"] == pytest.approx(-0.399)


def test_sealed_test_numbers_match_split():
    from cardiostage.data import load_clean, split_cleveland

    _, test = split_cleveland(load_clean())
    t = DATA["strategies"]["sealed_test"]
    assert t["n_patients"] == len(test) == 61
    assert t["n_sick"] == int(test[config.TARGET_COLUMN].sum())
    assert t["recall"]["low"] == pytest.approx(0.877)


def test_patient_flow_adds_up():
    flow = DATA["flow"]
    for f in flow:
        assert f["cleared"] + f["referred"] + f["onward"] == f["reached"]
    for prev, nxt in zip(flow, flow[1:]):
        assert nxt["reached"] == prev["onward"]
    assert flow[-1]["onward"] == 0
    # Share reaching invasive imaging equals the reported needed_invasive.
    assert flow[2]["reached"] / flow[0]["reached"] == pytest.approx(
        DATA["strategies"]["cv"]["staged"]["needed_invasive"]
    )


def test_js_data_matches_json():
    js = (SITE / "assets" / "data" / "site-data.js").read_text(encoding="utf-8")
    payload = js.split("window.CARDIOSTAGE_DATA = ", 1)[1].rstrip().rstrip(";")
    assert json.loads(payload) == DATA


def test_external_hospitals_match_reports():
    ext = pd.read_csv(config.REPORTS_DIR / "phase6_external.csv")
    for h in DATA["external"]:
        row = ext[(ext["stage"] == 1) & (ext["hospital"] == h["hospital"])].iloc[0]
        assert h["stage1"]["value"] == pytest.approx(row["auc_value"])


def test_version2_numbers_match_reports():
    second = pd.read_csv(config.REPORTS_DIR / "v2_final_second_look_stage1.csv")
    v2 = DATA["v2"]
    assert v2["hospitals"] == ["Cleveland", "Hungary", "Switzerland", "VA Long Beach", "Iran"]
    for r in v2["sealed_test_second_look"]:
        row = second[(second.hospital == r["hospital"]) & (second.version == r["version"])].iloc[0]
        assert r["cleared_but_sick"] == row["cleared_but_sick"]
        assert r["auc"]["value"] == pytest.approx(row["auc_value"], abs=5e-4)
    ta = pd.read_csv(config.REPORTS_DIR / "v2_final_second_look_typical_angina.csv")
    iran = ta[ta.group == "Iran"].iloc[0]
    assert v2["typical_angina_iran"]["v2"] == pytest.approx(iran["predicted_v2"])


def test_chatbot_numbers_match_reports():
    table = pd.read_csv(config.REPORTS_DIR / "llm_compare.csv")
    bots = DATA["chatbots"]
    assert set(bots["sources"]) == {"CardioStage v2", "claude", "chatgpt"}
    for r in bots["rows"]:
        row = table[(table.group == r["group"]) & (table.source == r["source"])].iloc[0]
        assert r["auc"]["value"] == pytest.approx(row["auc_value"], abs=5e-4)
        assert r["cleared_but_sick"] == row["cleared_but_sick"]
        assert r["ece"] == pytest.approx(row["ece"])
    # The page names three series and the chart container exists.
    html = (SITE / "index.html").read_text(encoding="utf-8")
    assert 'data-chart="chatbots"' in html and "ChatGPT, free" in html
