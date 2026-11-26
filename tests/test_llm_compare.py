"""
Tests for the chatbot comparison (llm_compare.py), using fake replies:
no chatbot is contacted.

Guarantees checked:
  - every sealed-test patient appears in exactly one prompt, in a fixed order
  - prompts contain only the six check-up facts: no outcome, no hospital name
  - replies are parsed strictly: wrong, duplicated-with-different-values or
    out-of-range answers count as missing, never guessed
  - scoring is correct on fake replies (perfect answers -> AUC 1.0)
"""

import pytest

from cardiostage import config
from cardiostage import llm_compare as lc

MODELS_PRESENT = (config.MODELS_DIR / "stage1.joblib").exists()


@pytest.fixture(scope="module")
def patients():
    return lc.sealed_patients()


def test_every_patient_in_exactly_one_batch(patients):
    assert len(patients) == 245
    ids = [pid for b in lc.batches(patients) for pid in b["patient_id"]]
    assert sorted(ids) == sorted(patients["patient_id"]) and len(set(ids)) == 245
    assert all(14 <= len(b) <= 15 for b in lc.batches(patients))


def test_order_is_fixed(patients):
    again = lc.sealed_patients()
    assert list(again.index) == list(patients.index)


def test_batches_mix_hospitals(patients):
    """Shuffling means no batch is a single hospital (which could hint at the era)."""
    for b in lc.batches(patients):
        assert b[config.HOSPITAL_COLUMN].nunique() >= 2


def test_prompts_leak_nothing(patients):
    for b in lc.batches(patients):
        text = lc.build_prompt(b).lower()
        for word in ["cleveland", "hungary", "switzerland", "long beach", "iran", "has_disease"]:
            assert word not in text
        for pid in b["patient_id"]:
            assert f"{pid.lower()}: age" in text


def test_committed_prompts_match_code(patients):
    """The prompt files on disk (the pre-registration) are exactly what the code builds."""
    for i, b in enumerate(lc.batches(patients), 1):
        path = lc.PROMPTS_DIR / f"batch_{i:02d}.txt"
        assert path.read_text(encoding="utf-8") == lc.build_prompt(b)


def test_missing_values_say_not_recorded(patients):
    row = patients[patients["chol"].isna()].iloc[0]
    assert "total cholesterol: not recorded" in lc.describe(row)


def test_parse_reply_strict():
    ids = ["P001", "P002", "P003", "P004", "P005"]
    text = """Here you go:
```
P001: 42
P002 - 7.5%
P003: 140
P004: 30
P004: 35
P009: 50
```"""
    got = lc.parse_reply(text, ids)
    assert got == {"P001": 0.42, "P002": 0.075}  # P003 >100, P004 conflicting, P005 missing


def test_parse_ignores_echoed_patient_lines():
    text = "P001: age 60, male, chest pain: typical angina\nP001: 55"
    assert lc.parse_reply(text, ["P001"]) == {"P001": 0.55}


@pytest.mark.skipif(not MODELS_PRESENT, reason="trained models missing")
def test_score_with_fake_replies(tmp_path, monkeypatch, patients):
    monkeypatch.setattr(lc, "RESPONSES_DIR", tmp_path)
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path)
    y = dict(zip(patients["patient_id"], patients[config.TARGET_COLUMN]))
    (tmp_path / "chatgpt").mkdir()
    (tmp_path / "claude").mkdir()
    for i, b in enumerate(lc.batches(patients), 1):
        perfect = "\n".join(f"{p}: {90 if y[p] else 10}" for p in b["patient_id"])
        (tmp_path / "chatgpt" / f"batch_{i:02d}.txt").write_text(perfect, encoding="utf-8")
        if i > 1:  # claude: batch 1 never answered
            (tmp_path / "claude" / f"batch_{i:02d}.txt").write_text(perfect, encoding="utf-8")
    out = lc.score().set_index(["group", "source"])
    allh = out.loc["All hospitals"]
    assert allh.loc["chatgpt", "auc_value"] == pytest.approx(1.0)
    assert allh.loc["chatgpt", "answered"] == 245
    assert allh.loc["claude", "answered"] == 245 - len(lc.batches(patients)[0])
    assert allh.loc["chatgpt", "cleared_but_sick"] == 0
    assert allh.loc["CardioStage v2", "auc_value"] == pytest.approx(0.841, abs=0.005)
    assert (tmp_path / "llm_compare.csv").is_file()
