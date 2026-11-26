# Phase 14: New Data and Version 2

**Goal:** find out whether CardioStage works on patients unlike its 1980s Cleveland training data, and, when it didn't, build a better version without fooling ourselves along the way.

This phase is mostly about **scientific honesty under pressure**: rejecting data that looks useful, admitting a model failed, judging fixes on the right data, and labelling results truthfully when a test set has been looked at more than once.

**Files in this phase**

| File | Job |
|---|---|
| `data/raw/external/` | The Iranian Z-Alizadeh Sani cohort (+ README: provenance, and why the Indian dataset was rejected) |
| `src/cardiostage/external_iran.py` | Maps the Iranian columns onto CardioStage; tests v1 on them |
| `src/cardiostage/pooled.py` | Five hospitals in one table; the v2 sealed-test split; the leave-one-hospital-out experiment |
| `src/cardiostage/v2_stage1.py` | Trains v2's stage-1 model; sanity checks |
| `src/cardiostage/v2_final.py` | The v2 final exam (first and second look) |
| `src/cardiostage/predictor.py` | `known_cautions`: the typical-angina warning |
| `tests/test_external_iran.py`, `test_pooled.py` | Mapping rules, split, leakage guard |

```bash
python -m cardiostage.external_iran     # v1 on modern Iranian patients
python -m cardiostage.pooled            # does pooling help? (leave-one-hospital-out)
python -m cardiostage.v2_stage1         # train v2 stage 1
python -m cardiostage.v2_final second_look
```

---

## 1. Finding data, and rejecting most of it

Searching for "heart disease dataset" finds dozens of results. Most are the **same UCI data re-uploaded**: renamed, merged or even duplicated. The popular Kaggle "Heart Failure Prediction" set (918 patients) is literally the four UCI hospitals plus Statlog, which is itself Cleveland. Testing on a re-upload means testing on patients the model trained on, which makes results look falsely good. So **checking provenance is step one**.

Two genuinely new datasets were downloaded. Before trusting either, we checked whether they *behave like real patients*:

| Check | India (1,000 rows) | Iran (303 rows) |
|---|---|---|
| Does the data match its own documentation? | **No** (slope 0 doesn't exist in the docs; cholesterol 0 in 53 rows) | Yes |
| Are ages spread like a real clinic? | **No**, uniformly spread (p = 0.11) | Yes |
| Does age predict disease? | **No** (AUC 0.51) | Yes (0.72) |
| Does one code decide everything? | **Yes**: slope 0 → 0% sick, slope 3 → 100% | No |

India was **rejected** (possibly synthetic or rule-labelled), and the reasons were recorded in `data/raw/external/README.md`.

> **Lesson:** a dataset with the right column names isn't the same as real patients. Check that it behaves the way medicine says it should.

## 2. The external test: v1 fails on modern patients

The Iranian cohort uses our exact outcome (≥50% artery narrowing on angiography). Only stage 1 could be tested fairly (no treadmill data). The result:

| | Cleveland | Iran |
|---|---|---|
| Stage-1 AUC | 0.84 | **0.68** |
| Sick patients caught (97% setting) | 97% | **68%** |

The cause was one feature. **Typical angina**: 94% sick in Iran, but v1 predicted 23%. In the 1980s Cleveland data, typical-angina patients were mostly healthy (a quirk of who got referred), and the model learned exactly that.

The first response was **protecting people now**: a red warning above the estimate for every typical-angina patient in the live app, verified working online, before any fix existed. The owner's rule: *the warning stays until it is completely unnecessary.*

## 3. Does pooling hospitals actually help? Measure before building

Instead of assuming "more data is better", we ran a **leave-one-hospital-out** (LOHO) experiment. For each hospital, train two ways *without* it, then test on it:

| Unseen hospital | Cleveland-only | Pooled |
|---|---|---|
| Iran | 0.67 | **0.74** |
| Cleveland | **0.84** | 0.80 |
| Hungary | **0.85** | 0.83 |
| Average (5 hospitals) | 0.75 | 0.76 |

Pooling was a **trade-off, not a free gain**: much better for modern patients, slightly worse for the 1980s hospitals. Because the populations genuinely differ, a model can't fit all of them perfectly. The owner chose pooling for stage 1 (it agrees with modern medicine and serves today's visitors) and kept v1's stages 2–3, where pooling showed no clear benefit.

## 4. Two traps avoided before training

- **Leakage:** v2 reuses v1's stage-2/3 models, which trained on 243 specific Cleveland patients. A fresh random split would have put many of *them* into v2's test set. So Cleveland keeps **exactly v1's split**, and a test proves no v2 test patient trained any model.
- **A name collision:** the integrity manifest keys files by *name*, so a backup at `models/v1/stage1.joblib` would have overwritten the fingerprint of `models/stage1.joblib`. The backup is named `v1_stage1.joblib` instead.

## 5. The final exam, and the "second look" problem

The exam script was **committed before the sealed test was opened**, fixing every metric in advance. First look: v2 was much safer (sick patients wrongly cleared 10 → 1) and much better calibrated, but **worse at VA Long Beach** (0.83 → 0.66).

The owner asked to investigate before shipping. Two findings:
1. **Part was luck:** v1 scored 0.83 on those 40 VA patients but only 0.69 on VA's other 159.
2. **Part was a real flaw:** v2's logistic regression had learned that **lower cholesterol means more risk** (coefficient −0.06; v1 +0.22). Iran's cholesterol is *estimated* and low (a modern population, many probably on cholesterol drugs) while 71% are sick. That's a classic **confounder**: two things move together because of a third, not because one causes the other.

**The fix** (Iran's estimated cholesterol treated as "not measured") was judged on **training data only**, because the sealed test can't be used to choose fixes without becoming biased.

That raised a methodological question with a clear answer: if the test prompted a fix, re-running the same test is a **second look**. It's still informative, but slightly optimistic. So both are reported, clearly labelled: the first look is the official unbiased exam, and the second look covers the fixed model.

## 6. When the rule picks the wrong model

After the fix, the selection rule ("best average on unseen hospitals") picked a **random forest** (0.769 vs 0.758). Checking it directly showed two problems:
- **A missing-value shortcut:** every Swiss and Iranian patient (both high-disease hospitals) gets the *same* filled-in cholesterol, and the forest gave that exact value about 3 extra points of risk.
- **A non-medical curve:** risk *fell* at very high cholesterol.

The gap was within noise, so logistic regression was chosen: one straight, correctly-upward cholesterol effect, and explainable. The decision is written into the code with its reason, and **automatic sanity checks** now run on every retrain: cholesterol never lowers risk, no missing-value shortcut, typical angina above non-anginal pain, older patients riskier.

> **Lesson:** a selection rule is a tool, not an oracle. When a model wins by a hair, check that it has learned medicine rather than artefacts.

## 7. Results (second look, 245 sealed patients)

| | v1 | v2 |
|---|---|---|
| AUC, all hospitals | 0.78 | **0.84** |
| Calibration error | 0.142 | **0.040** |
| Sick patients wrongly cleared at the check-up | 9 | **0** |
| Iran | 0.73 | **0.93** |
| VA Long Beach | 0.83 | 0.71 (the weak spot, shown openly) |
| Typical angina in Iran (97% sick) | predicted 28% | predicted **81%** |

The cost: v2 reassures fewer people early, so at Cleveland 92% need the treadmill test (v1: 69%). The warning stays, reworded, because 81% is still below 97%.

## 8. Check your understanding
1. Why is testing on the Kaggle 918-patient dataset a mistake, even though it's "external"?
2. Name two signs that suggested the Indian dataset wasn't real clinical data.
3. The LOHO experiment showed both strategies averaging about the same (0.75 vs 0.76). Why choose pooling anyway, and what did it cost?
4. Why must v2's Cleveland test patients be exactly v1's test patients?
5. Why couldn't the cholesterol fix be chosen by re-checking the sealed test?
6. What is a "second look", and why report it at all?
7. The rule picked random forest. Why was logistic regression used instead, and how does the project guard against the same problem in future?
8. v2 predicts 81% for typical angina in Iran. Why does the warning stay?

## Answers

**1.** It's a re-upload of the four UCI hospitals we trained or validated on, plus Statlog (which is Cleveland). Testing on it means testing on known patients, which inflates the results.

**2.** Any two of: the documentation contradicts the data (slope 0, cholesterol 0); ages are uniformly distributed; age and exercise angina show no link to disease; slope codes almost completely determine the outcome; no hospital or diagnosis method is stated.

**3.** It fixes the modern-patient failure (Iran 0.67 → 0.74 unseen; 0.93 in the final test), agrees with modern medicine about typical angina, and improves overall safety (wrongly cleared 9 → 0). The cost is slightly lower ranking at the 1980s hospitals, and more patients sent on to the treadmill test.

**4.** v2 reuses v1's stage-2/3 models, which trained on the other 243 Cleveland patients. Any other split would put some of their training patients into the test set (leakage), making results look better than they are.

**5.** Using the test to choose a fix lets the test shape the model, so the same test can no longer give an unbiased estimate. Fixes must be judged on training data (here, leave-one-hospital-out and coefficient direction).

**6.** A re-run of an already-opened test after making changes it prompted. It's still informative (the patients are still unseen by training) but slightly optimistic. Reporting it labelled, alongside the official first look, is transparent instead of quietly replacing the first result.

**7.** The forest's advantage was within noise, and it had a missing-value shortcut and a non-medical cholesterol curve. Logistic regression is monotonic, shortcut-free and explainable. The choice and its reason are pinned in `v2_stage1.py`, and automatic sanity checks fail any future retrain that learns backwards effects or a shortcut.

**8.** 81% is still noticeably below the 97% observed, so the estimate can still be too low for these patients. The owner's rule is to keep the warning until it's completely unnecessary.
