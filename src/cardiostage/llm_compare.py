"""
CardioStage vs free chatbots (ChatGPT and Claude.ai) on the v2 sealed test.

The question (asked by a faculty member): why would anyone use CardioStage
instead of asking ChatGPT or Claude? This module measures what a person
actually gets from the FREE chat websites, on the same 245 sealed-test
patients and the same check-up facts CardioStage's stage 1 uses.

How it works (Option A: free, manual):
  1. `python -m cardiostage.llm_compare prompts` writes paste-ready messages
     (data/llm_compare/prompts/batch_NN.txt). Patients are shuffled (seeded)
     so every batch mixes hospitals, and get anonymous IDs (P001...).
  2. The project owner pastes each batch into a FRESH chat (memory and web
     search off) on chatgpt.com and claude.ai, and saves each reply to
     data/llm_compare/responses/<chatbot>/batch_NN.txt.
  3. `python -m cardiostage.llm_compare score` scores both chatbots and
     CardioStage on exactly the same patients.

Pre-registration: this file and the prompts were committed BEFORE any
sealed patient was sent to a chatbot. Rules fixed in advance:
  - One try per batch. A reply may be re-requested only if it's unusable
    as a whole (e.g. no numbers at all); every re-request is logged in
    data/llm_compare/log.md. The prompt is never changed to get better scores.
  - Missing or unreadable answers for single patients are counted and
    reported, never filled in or guessed.
  - Metrics (all on the same patients):
      ranking quality   AUC, bootstrap 95% CI; difference vs CardioStage v2
                        with a paired bootstrap CI (same resampled patients)
      honesty           calibration error (ECE, 5 bins), mean predicted vs
                        actual disease rate
      safety            sick patients "wrongly cleared": predicted below
                        CardioStage v2's clearing cut-off (14.4%)
      by group          each hospital; typical angina; women vs men
      memorisation hint each chatbot's AUC gap vs CardioStage at Cleveland
                        (a famous public dataset) vs Iran (much less known).
                        Descriptive only: groups are small.
  - What this is NOT: the best any LLM can do (free tiers, several patients
    per message, one try each). It's "what a person gets from the free
    chatbots", and is reported that way.
"""

import re
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from cardiostage import config
from cardiostage.calibration import expected_calibration_error
from cardiostage.pooled import STAGE_HOSPITALS, load_pooled, split_v2
from cardiostage.stats import bootstrap_ci, fmt_ci

BASE = config.PROJECT_ROOT / "data" / "llm_compare"
PROMPTS_DIR = BASE / "prompts"
RESPONSES_DIR = BASE / "responses"
CHATBOTS = ("chatgpt", "claude")
N_BATCHES = 17  # 245 patients -> batches of 14-15
SHUFFLE_SEED = 2026

CP_TEXT = {
    "typical angina": "typical angina",
    "atypical angina": "atypical angina",
    "non-anginal": "non-anginal chest pain",
    "asymptomatic": "no chest pain (asymptomatic)",
}

PROMPT_HEADER = """\
I'm working on a student research project that compares heart-disease risk estimates. \
Below are {n} anonymised patients from research data (nobody's care depends on your answer).

All of them were referred for coronary angiography because a doctor suspected coronary artery disease.

For each patient, estimate the probability (0-100%) that their angiography shows significant \
coronary artery disease (at least 50% narrowing of a major coronary artery), using only the \
information given. "not recorded" means the value is unknown.

Reply with ONLY one line per patient, in exactly this format, inside a code block, \
and nothing else:
{example}

Patients:
"""


def sealed_patients() -> pd.DataFrame:
    """The 245 sealed-test patients in a fixed shuffled order, with anonymous IDs."""
    _, test = split_v2(load_pooled())
    test = test.sample(frac=1, random_state=SHUFFLE_SEED)
    test.insert(0, "patient_id", [f"P{i:03d}" for i in range(1, len(test) + 1)])
    return test


def _value(x, fmt="{:.0f}", suffix=""):
    return "not recorded" if pd.isna(x) else fmt.format(x) + suffix


def describe(row) -> str:
    """One patient as a plain-English line (the six stage-1 facts only)."""
    sex = "male" if row["sex"] == 1 else "female"
    fbs = "not recorded" if pd.isna(row["fbs"]) else ("yes" if row["fbs"] == 1 else "no")
    return (
        f"{row['patient_id']}: age {row['age']:.0f}, {sex}, chest pain: {CP_TEXT[row['cp']]}, "
        f"resting blood pressure: {_value(row['trestbps'], suffix=' mm Hg')}, "
        f"total cholesterol: {_value(row['chol'], suffix=' mg/dL')}, "
        f"fasting blood sugar above 120 mg/dL: {fbs}"
    )


def batches(patients: pd.DataFrame) -> list[pd.DataFrame]:
    idx = np.array_split(np.arange(len(patients)), N_BATCHES)
    return [patients.iloc[i] for i in idx]


def build_prompt(batch: pd.DataFrame) -> str:
    ids = list(batch["patient_id"])
    example = "```\n" + f"{ids[0]}: <number>\n{ids[1]}: <number>\n...\n" + "```"
    lines = "\n".join(describe(r) for _, r in batch.iterrows())
    return PROMPT_HEADER.format(n=len(batch), example=example) + lines + "\n"


def write_prompts() -> None:
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    for bot in CHATBOTS:
        (RESPONSES_DIR / bot).mkdir(parents=True, exist_ok=True)
    for i, b in enumerate(batches(sealed_patients()), 1):
        path = PROMPTS_DIR / f"batch_{i:02d}.txt"
        path.write_text(build_prompt(b), encoding="utf-8", newline="\n")  # same bytes everywhere
    print(f"Wrote {N_BATCHES} prompts to {PROMPTS_DIR}")


# ------------------------------------------------------------------ parsing --
LINE = re.compile(r"\b(P\d{3})\b\s*[:=|,\-–]?\s*(\d{1,3}(?:\.\d+)?)\s*%?")


def parse_reply(text: str, expected_ids: list[str]) -> dict:
    """
    {patient_id: probability 0-1} for the expected IDs found in a reply.
    IDs that are missing, duplicated with different values, or out of
    range (above 100) are left out, so they're counted as missing answers.
    """
    found: dict[str, list[float]] = {}
    for pid, num in LINE.findall(text):
        if pid in expected_ids:
            found.setdefault(pid, []).append(float(num))
    out = {}
    for pid, values in found.items():
        if len(set(values)) == 1 and 0 <= values[0] <= 100:
            out[pid] = values[0] / 100
    return out


def load_answers(bot: str, patients: pd.DataFrame) -> pd.Series:
    """Chatbot probability per patient_id (NaN where there's no usable answer)."""
    answers = {}
    for i, b in enumerate(batches(patients), 1):
        path = RESPONSES_DIR / bot / f"batch_{i:02d}.txt"
        if path.is_file():
            answers.update(parse_reply(path.read_text(encoding="utf-8"), list(b["patient_id"])))
    return pd.Series(answers, dtype=float).reindex(patients["patient_id"])


# ------------------------------------------------------------------ scoring --
def _auc(y, p):
    return roc_auc_score(y, p)


def _auc_diff(y, p, q):
    return roc_auc_score(y, p) - roc_auc_score(y, q)


def score_group(name: str, y, preds: dict, clear_below: float) -> list[dict]:
    """Rows for one group of patients; preds = {source: probabilities}."""
    rows = []
    ref = preds["CardioStage v2"]
    both = 0 < y.sum() < len(y)
    for source, p in preds.items():
        ok = ~np.isnan(p)  # patients this source answered
        yy, pp, rr = y[ok], p[ok], ref[ok]
        auc = bootstrap_ci(_auc, yy, pp, need_both_classes=True) if both else (np.nan,) * 3
        diff = (
            bootstrap_ci(_auc_diff, yy, pp, rr, need_both_classes=True)
            if both and source != "CardioStage v2"
            else (np.nan,) * 3
        )
        cleared = pp < clear_below
        rows.append(
            {
                "group": name,
                "source": source,
                "n": len(y),
                "answered": int(ok.sum()),
                "n_sick": int(yy.sum()),
                "disease_rate": yy.mean() if len(yy) else np.nan,
                "mean_predicted": pp.mean() if len(pp) else np.nan,
                "roc_auc": fmt_ci(*auc) if not np.isnan(auc[0]) else "n/a",
                "auc_value": auc[0],
                "auc_vs_cardiostage": fmt_ci(*diff) if not np.isnan(diff[0]) else "",
                "ece": expected_calibration_error(yy, pp, n_bins=5) if len(yy) else np.nan,
                "share_cleared": cleared.mean() if len(pp) else np.nan,
                "cleared_but_sick": int((cleared & (yy == 1)).sum()),
            }
        )
    return rows


def score() -> pd.DataFrame:
    from cardiostage import integrity

    patients = sealed_patients()
    v2 = integrity.load(config.MODELS_DIR / "stage1.joblib")
    preds = {
        "CardioStage v2": v2["model"].predict_proba(patients[config.STAGES[1]])[:, 1],
        **{bot: load_answers(bot, patients).to_numpy() for bot in CHATBOTS},
    }
    clear_below = v2["zones"]["rule_out_below"]
    y = patients[config.TARGET_COLUMN].to_numpy()
    groups = [("All hospitals", np.ones(len(y), bool))]
    groups += [(h, (patients[config.HOSPITAL_COLUMN] == h).to_numpy()) for h in STAGE_HOSPITALS[1]]
    groups += [
        ("Typical angina", (patients["cp"] == "typical angina").to_numpy()),
        ("Women", (patients["sex"] == 0).to_numpy()),
        ("Men", (patients["sex"] == 1).to_numpy()),
    ]
    rows = []
    for name, m in groups:
        rows += score_group(name, y[m], {k: v[m] for k, v in preds.items()}, clear_below)
    out = pd.DataFrame(rows)
    out.to_csv(config.REPORTS_DIR / "llm_compare.csv", index=False)
    return out


def main(cmd: str) -> None:
    if cmd == "prompts":
        write_prompts()
    elif cmd == "score":
        out = score()
        pd.set_option("display.width", 250, "display.max_columns", 20)
        print(out.drop(columns=["auc_value"]).round(3).to_string(index=False))
    else:
        sys.exit("usage: python -m cardiostage.llm_compare [prompts|score]")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
