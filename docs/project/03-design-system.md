# CardioStage: Design System

The visual and content rules for CardioStage's charts, app and written outputs. Follow these so every new chart, screen or sentence looks and sounds like the rest of the project.

| | |
|---|---|
| **Last updated** | 2026-11-23 |
| **Applies to** | `reports/figures/*`, the Streamlit app (`app/`), README and docs |
| **Related docs** | [PRD](01-product-requirements.md) · [Models](02-models.md) · [Architecture](04-architecture.md) |

---

## 1. Principles
1. **Honest before impressive.** Show uncertainty (confidence intervals, plausible ranges, "undetermined") rather than bare numbers. Never round away a limitation.
2. **Plain language first, jargon second.** Every medical or ML term is explained where it appears ("ST depression: how far the ECG dips during exercise").
3. **Safety is part of the design.** Disclaimers are visible, never hidden; wording never diagnoses.
4. **One meaning per colour.** Orange always means *disease / raises risk*; blue always means *healthy / lowers risk*.
5. **Colour is never the only signal.** Every coloured element also has a label, icon or text.
6. **Show the mechanism.** Prefer charts that explain *why* (contributions, flows) over decoration.

## 2. Colour tokens
### 2.1 Semantic colours (charts and app)
| Token | Hex | Meaning | Used in |
|---|---|---|---|
| `disease` / `raises-risk` | `#eb6834` (orange) | Heart disease, a factor raising risk, "referred" | Disease KDEs/bars, SHAP positive bars, referred segments |
| `healthy` / `lowers-risk` | `#2a78d6` (blue) | No disease, a factor lowering risk, "cleared" | Healthy KDEs, SHAP negative bars, cleared segments, primary colour |
| `pending` | `#d0cfca` (warm grey) | Needs the next test | Policy flow "needs next test" |
| `text-secondary` | `#52514e` | Annotations, value labels, captions | All chart labels |
| `reference` | `#b5b4ae` | Reference lines (diagonal, coin flip, zero) | Calibration diagonal, ROC chance line |
| `grid` | `#ebeae6` | Gridlines | All charts |
| `axis` | `#d0cfca` | Axis edges (seaborn charts) | EDA charts |

### 2.2 Categorical series (fixed order, never cycled)
Taken from a validated colour-blind-safe palette; assign in this order:

| Slot | Hex | Series in this project |
|---|---|---|
| 1 | `#2a78d6` blue | Logistic regression · Stage 1 · Hungary · "sigmoid" |
| 2 | `#eb6834` orange | Random forest · Stage 2 · VA Long Beach · "uncalibrated" |
| 3 | `#1baf7a` aqua | XGBoost · Stage 3 · Switzerland · "isotonic" |
| 4 | `#eda100` yellow | Ensemble |
| neutral | `#52514e` dark grey | Cleveland internal reference, "All patients" |

Within the **same chart**, a categorical series must not reuse a semantic colour with a different meaning. (Example: the fairness chart uses blue for sex groups and orange for age groups because no disease/healthy meaning is present there.)

### 2.3 Sequential
Single-hue **Blues** (light → dark) for magnitudes, e.g. the missing-data heatmap (0–100% missing). Never a rainbow.

### 2.4 App theme (`.streamlit/config.toml`)
| Setting | Value |
|---|---|
| `base` | light |
| `primaryColor` | `#2a78d6` |
| `backgroundColor` | `#fcfcfb` |
| `secondaryBackgroundColor` | `#f1f0ec` |
| `textColor` | `#1a1a19` |

## 3. Chart rules
| Rule | Specification |
|---|---|
| Title | Bold; states the **finding** when there is one ("Disease rate varies hugely between hospitals"), not just the variables |
| Uncertainty | Point estimates carry error bars (95% CI or ±1 sd, stated in the title/legend). Sample sizes (`n=`) are shown next to estimates from small groups |
| Axes | Top and right spines removed; light grid on the value axis only where it aids reading |
| Labels | Direct value labels beside markers (e.g. `0.892  (n=292)`); text in `#52514e`, never in the series colour |
| Legends | Required for ≥ 2 series; placed where they cannot cover data (above panels or in empty corners) |
| Shared axes | Small multiples share y-axes; category names only on the leftmost panel |
| Line/marker | Lines 2 px; markers ≥ 7 px; error-bar caps 3–4 px |
| Diverging bars | Contributions: orange right (raises), blue left (lowers), zero line in `#52514e`, symmetric x-limits |
| Reference lines | Dashed `#b5b4ae` (chance, perfect calibration, zero); dotted `#52514e` for targets (e.g. 97% recall) |
| Log scales | Only when the range spans orders of magnitude; never hide the starting point (loss curve starts at step 1 = initial guess) |
| Output | PNG, 150 dpi, `bbox_inches="tight"`, saved to `reports/figures/NN_name.png` |
| Verification | Every chart is rendered and visually inspected before committing (clipping, overlaps, collisions) |

### 3.1 Figure inventory
| # | File | Shows | Produced by |
|---|---|---|---|
| 01 | `01_disease_rate_by_hospital.png` | Disease rate per hospital | `eda.py` |
| 02 | `02_missing_by_hospital.png` | % missing per feature × hospital, by stage | `eda.py` |
| 03 | `03_numeric_by_disease.png` | Healthy vs sick distributions | `eda.py` |
| 04 | `04_categorical_disease_rate.png` | Disease rate per category | `eda.py` |
| 05 | `05_model_comparison.png` | Nested-CV metrics of 3 models | `train_baselines.py` |
| 06 | `06_scratch_loss_curve.png` | From-scratch LR loss curve | `from_scratch.py` |
| 07 | `07_auc_by_stage.png` | ROC-AUC by stage and candidate | `staging.py` |
| 08 | `08_roc_by_stage.png` | ROC curves of chosen stage models | `staging.py` |
| 09 | `09_staged_policy_flow.png` | Where patients stop (cleared / referred / next) | `staging.py` |
| 10 | `10_calibration_curves.png` | Reliability: uncalibrated vs sigmoid, chosen marked | `calibration.py` |
| 11 | `11_not_confident_errors.png` | Uncertainty flag rate by outcome | `calibration.py` |
| 12 | `12_external_auc.png` | AUC at unseen hospitals | `external_validation.py` |
| 13 | `13_external_calibration.png` | External calibration before/after prior shift | `external_validation.py` |
| 14 | `14_fairness.png` | Recall/specificity by sex and age | `fairness.py` |
| 15 | `15_global_importance.png` | Mean \|SHAP\| per stage | `explanations.py` |
| 16 | `16_feature_effects.png` | SHAP dependence (thalch, oldpeak, age, chol) | `explanations.py` |
| 17 | `17_case_study.png` | Missed woman explained at stages 1 and 3 | `explanations.py` |
| 18 | `18_final_test.png` | Sealed test AUC vs CV estimates | `final_evaluation.py` |

## 4. App layout
| Page | Icon | Structure |
|---|---|---|
| **Screener** (default) | 🫀 | Title + tagline + caption → disclaimer box → Stage 1 form → result card → next-stage form ("➡️ Recommended next step" when uncertain, otherwise an "add … anyway (optional)" expander) → … → "🏁 Screening complete" |
| **Results** | 📊 | Title + method caption → 3 headline metrics → tabs: Sealed test set · Staged screening · Calibration · New hospitals · Fairness · Explanations → disclaimer |
| **About** | ℹ️ | Disclaimer → idea (stage table) → how it was built → known limitations → link to repo |
| **Sidebar** (Screener) | | "Try an example" selector → limitation note (when that example is chosen) → "Reset all inputs" → short disclaimer |

Layout: `layout="wide"`; forms use 3 columns (stage 1–2) or 2 columns (stage 3).

## 5. Components
### 5.1 Stage form
- Bordered `st.form`; heading `Stage N · Name`; caption saying what the stage requires ("Needs an ECG and a supervised exercise test").
- Every input has a `help=` tooltip in plain English with normal ranges where useful.
- "Not measured" is available wherever real data is often missing (cholesterol checkbox; blood sugar, ECG, slope, vessels, thallium options).
- Numeric bounds: age 18–100, BP 60–250, cholesterol 80–700, heart rate 60–230, ST depression −3.0–7.0 (step 0.1).
- One primary button per form: "Assess risk" / "Add treadmill results" / "Add imaging results".

### 5.2 Result card (`ui.render_assessment`)
Bordered container, top to bottom:
1. Subheader `Stage N result · Name`.
2. Row: **Estimated risk** metric (`34%`) · **Plausible range** metric (`28% – 39%`) · decision box (2× width).
3. Threshold caption ("This stage clears below 9.0% and refers from 83.0%…").
4. Unusual-patient warning (only when triggered).
5. "Not measured" caption (only when inputs are missing).
6. **Why this estimate?** summary sentence + contribution chart (top 8).
7. Expander "Full breakdown and how to read it": table + caveat.

### 5.3 Decision boxes
| Zone | Component | Icon | Headline |
|---|---|---|---|
| low / clear | `st.success` | ✅ | "Low estimated risk" / "Below the screening threshold" |
| high / refer | `st.error` | ⚠️ | "High estimated risk" / "Above the screening threshold" |
| uncertain | `st.info` | 🔎 | "Uncertain" (+ suggested next test) |

### 5.4 Other callouts
| Callout | Component | Icon |
|---|---|---|
| Disclaimer (main) | `st.warning` | ⚕️ |
| Unusual patient | `st.warning` | 🧭 |
| Known-limitation example note | `st.info` (sidebar) | 🧪 |
| Screening complete | `st.success` | 🏁 |
| Invalid input ("Some inputs aren't valid, so no assessment was made: …") | `st.error` | 🚫 |
| Unexpected failure ("Something went wrong while assessing this patient…"): never a traceback | `st.error` | 🚫 |
| Rate limit ("Too many assessments in a short time. Please wait N seconds…") | `st.warning` | ⏳ |
| Model integrity failure ("**Model integrity check failed.** … Rebuild the models with `python -m cardiostage.train_all`.") | `st.error` (stops the page) | – |

**Error-message rules:** say what happened and what to do next, in plain English; never show stack traces, file paths or internal values (`client.showErrorDetails = "none"`); no result is shown when an assessment fails.

### 5.5 Contribution chart (`ui.contribution_chart`, Plotly)
Horizontal bars, labels `Measurement = value`, orange positive / blue negative, values `+12.3` outside bars, symmetric x-range (≥ ±5 pts), hover shows "percentage points", no mode bar, transparent background.

## 6. Content and voice
| Rule | Do | Don't |
|---|---|---|
| Never diagnose | "Estimated risk 34%", "Referral to a cardiologist is suggested" | "You have heart disease" |
| Explain terms in place | "ST depression (treadmill ECG)" + tooltip | Raw column names like `oldpeak` |
| State uncertainty | "1.000 [0.877, 1.000]", "undetermined: only 8 healthy patients" | "100% recall" |
| Explanations caveat | "Describes what drove the model, not what causes disease" | "Being female protects you" |
| Units | percentage points ("+12 pts") for contributions; % for risks; mm Hg, mg/dl, bpm, mm | Unitless numbers |
| Tone | Calm, factual, second person sparingly | Alarmist or overconfident |

**Canonical disclaimer** (`ui.DISCLAIMER`):
> **Educational project, not a medical device.** CardioStage was trained on 243 patients from a single 1980s US hospital dataset. It must not be used to diagnose, treat, or make decisions about any real person. If you have chest pain or heart concerns, contact a doctor or emergency services.

**Value formatting** (`explain.format_value`): age "58 years"; sex "male"/"female"; BP "136 mm Hg"; cholesterol "319 mg/dl"; blood sugar "above 120 mg/dl"/"normal"; heart rate "152 bpm"; ST depression "1.2 mm"; missing → "not measured"; categories → descriptive text (e.g. "reversible defect (reduced blood flow under stress)").

## 7. Accessibility
- The categorical palette is colour-blind-validated for adjacent series; charts with more than 4 series are avoided.
- Every status box carries an icon **and** a text headline; charts carry direct labels.
- Light theme with dark text (`#1a1a19` on `#fcfcfb`); secondary text `#52514e`.
- Tooltips supplement, never replace, visible labels.

## Changelog
| Date | Change |
|---|---|
| 2026-11-23 | Added error, rate-limit and integrity callouts and error-message rules (security hardening) |
| 2026-11-23 | Document created at v1.0 |
