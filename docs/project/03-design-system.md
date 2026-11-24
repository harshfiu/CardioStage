# CardioStage: Design System

The visual and content rules for CardioStage's charts, app and written outputs. Follow these so every new chart, screen or sentence looks and sounds like the rest of the project.

| | |
|---|---|
| **Last updated** | 2026-11-23 |
| **Applies to** | the landing site (`site/`), the Streamlit app (`app/`), `reports/figures/*`, README and docs |
| **Related docs** | [PRD](01-product-requirements.md) · [Models](02-models.md) · [Architecture](04-architecture.md) |

---

## 1. Principles
1. **Honest before impressive.** Show uncertainty (confidence intervals, plausible ranges, "undetermined") rather than bare numbers. Never round away a limitation.
2. **Plain language first, jargon second.** Every medical or ML term is explained where it appears ("ST depression: how far the ECG dips during exercise").
3. **Safety is part of the design.** Disclaimers are visible, never hidden; wording never diagnoses.
4. **One meaning per colour.** Orange/coral always means *disease / raises risk*; blue always means *healthy / lowers risk*; mint means *reassured*. Peach is the brand/action colour and never carries a medical meaning.
5. **Colour is never the only signal.** Every coloured element also has a label, icon or text.
6. **Show the mechanism.** Prefer charts that explain *why* (contributions, flows) over decoration.
7. **Calm, warm, human.** The product voice is reassuring, not alarming; hand-drawn single-line illustrations and a personal note make it feel made by a person. Motion is tasteful and never sits next to a risk number.

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

The static PNG figures above keep their light palette (they're also embedded in the README and docs, which most people read on white). In the dark app they're shown as white "cards".

### 2.4 Product palette: site and app ("dark medical-tech, warmed up")
Shared by `site/assets/css/site.css` (`:root` tokens) and `.streamlit/config.toml`.

| Token | Hex | Role |
|---|---|---|
| `--bg` | `#080B12` | Page background (near-black navy) |
| `--surface` / app secondary bg | `rgba(22,24,32,0.78)` / `#14161D` | Cards, inputs |
| `--ink` | `#F3EEE6` | Primary text (warm off-white) |
| `--ink-2` | `#C9C2B6` | Body text on dark |
| `--ink-3` | `#A9A196` | Captions, axis labels |
| `--warm` | `#F2B880` | Brand/action: primary buttons (site), eyebrows, links, sliders |
| `--blue` | `#5B8FE8` | Heartbeat line, "lowers risk", check-up stage, uncertain |
| `--coral` | `#FF8A65` | "Raises risk", referred |
| `--mint` | `#8EE6C2` | Reassured / cleared |
| `--line` | `rgba(242,184,128,0.14)` | Hairline borders |
| app `borderColor` | `#2A2620` | Widget borders |

### 2.5 App theme (`.streamlit/config.toml`)
| Setting | Value |
|---|---|
| `base` | dark |
| `primaryColor` / `linkColor` | `#F2B880` |
| `backgroundColor` | `#080B12` (sidebar `#0D0F15`) |
| `secondaryBackgroundColor` | `#14161D` (sidebar `#1A1D26`) |
| `textColor` | `#F3EEE6` |
| `greenColor` / `blueColor` / `redColor` / `orangeColor` | `#8EE6C2` / `#5B8FE8` / `#FF8A65` / `#F2B880` (status boxes keep the site's meanings) |
| `font` / `headingFont` | Inter / Fraunces (weight 500), self-hosted via `[[theme.fontFaces]]` from `app/static/fonts/` |
| `baseRadius`, `showWidgetBorder` | `12px`, true |

**Buttons:** Streamlit draws primary buttons with white text, which on peach is only **1.76:1** contrast (fails WCAG). App form buttons therefore use the default (secondary) style: peach border/text on hover, warm text on dark, readable. The site's peach buttons use dark text (`#1A0F06`, 10.7:1).

## 2A. Typography
| Use | Font | Notes |
|---|---|---|
| Headlines (site h1–h3, app headings), the personal note | **Fraunces** 400/500/600 (serif) | Warm, editorial; h1 `clamp(40px, 6vw, 76px)` on the site |
| Body, UI, numbers | **Inter** 400/500/600 | `font-variant-numeric: tabular-nums` for statistics |
| Eyebrows | Inter 600, 12–13 px, uppercase, letter-spacing 0.14em, peach | "HONEST BY DESIGN" |

Both fonts are **self-hosted** woff2 (SIL Open Font Licence, from @fontsource 5.3.0), so neither the site nor the app contacts Google Fonts.

## 2B. Illustrations and motion (site)
- **Illustrations:** hand-drawn-style single-line SVGs (heart held in a hand, stage icons, notebook with ECG and pen), 1.6–2 px strokes in `--ink`, with a peach or blue accent. Drawn on with GSAP DrawSVG.
- **Hero background:** Vanta NET (three.js) in blue on `--bg`, 9 points; it **runs only while the hero is on screen** (IntersectionObserver), to save battery.
- **Scrolling:** Lenis smooth scrolling synced to GSAP's ticker; anchor links scroll with a −72 px offset (sticky nav).
- **Reveals:** headline words rise in with SplitText (`mask: "words"`, accessible `aria: "auto"`); cards fade up; chart bars grow (`scaleX`); big stats count up. Small numbers (e.g. "3 hospitals") are shown directly, because a count-up reads "1 hospitals" mid-way.
- **How it works:** pinned for 1400 px of scroll at ≥ 900 px widths; a blue line and dot advance and each stage card lights up (`.is-active`). On narrower screens, cards activate as they scroll into view.
- **Reduced motion:** with `prefers-reduced-motion: reduce`, none of the motion code runs (no Lenis, GSAP or Vanta); all content is visible and static.
- **The app has no motion** beyond Streamlit's own spinners; nothing animates near a risk estimate.

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
| In-app display | The app's Results page no longer shows these PNGs: it redraws the same evidence in Plotly (§5.6). The PNGs remain for the README and docs |
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

## 3A. Landing site (`site/`)
A static page (no backend) published with GitHub Pages. Section order:

| # | Section | Content |
|---|---|---|
| 1 | Sticky nav | Logo · How it works · Results · Honest by design · Why I built this · GitHub (outline button) |
| 2 | Hero | Eyebrow "Explainable heart-disease screening"; h1 **"Fewer tests for those who don't need them. More care for those who do."**; lede; peach "Try the screener" + "See how it works"; heart-in-hand illustration; ECG line; Vanta NET background |
| 3 | Stats row | 40% fewer invasive tests · 0 sick patients missed on the sealed test (of 28) · 3 hospitals checked |
| 4 | How it works (pinned) | 3 stage cards with icons and the real patient-flow numbers |
| 5 | Results | Comparison card (staged vs everyone gets every test) + "Where people stop along the way" flow chart |
| 6 | Honest by design | 3 feature cards (calibrated / explains itself / open about limits) + "An example: why 33%?" contribution chart |
| 7 | Tested beyond home | Per-hospital ROC-AUC with 95% CIs, stage 1 (blue) and stage 2 (peach) |
| 8 | Limitations | 5 plain-language limitations |
| 9 | Why I built this | Notebook illustration + the builder's personal note, signed **Harsh Gupta · builder of CardioStage** |
| 10 | CTA | "Try it on your own computer." · "Setup guide on GitHub" (+ "Open the local app" only when the page is served from localhost) |
| 11 | Footer | Disclaimer, MIT licence, UCI data credit, Third-party notices |

**Charts on the site** are built with plain DOM elements (no chart library) from `window.CARDIOSTAGE_DATA` (generated by `python -m cardiostage.site_data`), so **no statistic on the site is hand-typed**. Each chart has an `aria-label`/`role="img"` text equivalent. The contribution chart uses a 3-column grid (label · bar · value) so values never collide with labels; on phones the label moves above the bar.

**Layout:** container max 1200 px (32 px gutters; 16 px on phones); breakpoints 640 / 760 / 900 px; no horizontal scrolling at 371 px (verified).

## 4. App layout
| Page | Icon | Structure |
|---|---|---|
| **Screener** (default) | 🫀 | Title + tagline + caption → disclaimer box → Stage 1 form → result card → next-stage form ("➡️ Recommended next step" when uncertain, otherwise an "add … anyway (optional)" expander) → … → "🏁 Screening complete" |
| **Results** | 📊 | Title + method caption → 3 headline metrics → tabs: Sealed test set · Staged screening · Calibration · New hospitals · Fairness · Explanations → disclaimer |
| **About** | ℹ️ | Disclaimer → idea (stage table) → how it was built → known limitations → link to repo |
| **Sidebar** (Screener) | | "Try an example" selector with **short names** (Low risk · Uncertain, then cleared · High risk · Known limitation) → one-line patient description (caption) → limitation note (only for that example) → "Reset all inputs" (also clears the example and its note) → short disclaimer |

Layout: `layout="wide"`; forms use 3 columns (stage 1–2) or 2 columns (stage 3).

## 5. Components
### 5.1 Stage form
- Bordered `st.form`; heading `Stage N · Name`; caption saying what the stage requires ("Needs an ECG and a supervised exercise test").
- Every input has a `help=` tooltip in plain English with normal ranges where useful.
- "Not measured" is available wherever real data is often missing (cholesterol checkbox; blood sugar, ECG, slope, vessels, thallium options).
- **Measurements use sliders**, not number boxes: age 18–100, BP 60–250, cholesterol 80–700, heart rate 60–230, ST depression −3.0–7.0 (step 0.1). Streamlit's number input blocks mouse-wheel page scrolling (`preventDefault()` on wheel); sliders don't, and they make the valid range visible. The Stage 1 caption tells users they can click a slider and use the arrow keys for exact values.
- One submit button per form: "Assess risk" / "Add treadmill results" / "Add imaging results" (secondary style for contrast, see §2.5).

### 5.2 Result card (`ui.render_assessment`)
Bordered container, top to bottom:
1. Subheader `Stage N result · Name`.
2. Row: **Estimated risk** metric (`34%`) · **Plausible range** metric (`28% – 39%`) · decision box (2× width). **Rendered progressively:** risk and decision box appear immediately; the range shows a spinner ("Checking how stable this estimate is…") until ready (~2 s at stages 2–3).
3. Threshold caption ("This stage clears below 9.0% and refers from 83.0%…").
4. Unusual-patient warning (only when triggered).
5. "Not measured" caption (only when inputs are missing).
6. **Why this estimate?** spinner ("Working out which measurements drove this estimate…", ~3 s at stages 2–3), then summary sentence + contribution chart (top 8). If an add-on fails: "The … couldn't be computed. The risk and decision above are unaffected." (🚫)
7. Expander "Full breakdown and how to read it": table + caveat.

### 5.3 Decision boxes
| Zone | Component | Icon | Headline |
|---|---|---|---|
| low / clear | `st.success` | ✅ | "Low estimated risk" / "Below the screening threshold" |
| high / refer | `st.error` | ⚠️ | "High estimated risk" / "Above the screening threshold" |
| uncertain | `st.info` | 🔎 | "Uncertain" (+ suggested next test) |

### 5.3a Consent screen (`app/consent.py`)
Shown once per browser session before any page runs: title → "Before you start" → `st.warning` (⚕️) *educational project, not a medical device; an estimate that can be wrong; not a diagnosis; chest pain → call your local emergency number* → plain-language data-handling text (local: "runs on this computer… never sent anywhere"; public: processed on Streamlit Community Cloud in the US only to compute the estimate, not stored/logged/shared by CardioStage, the host collects its own usage statistics and an anonymous viewer count, with a link to Streamlit's privacy notice; never asks for identifying details) → checkbox "I understand…" → primary **Continue** button, disabled until ticked. The same data-handling text appears on the About page under "Your privacy".

### 5.4 Other callouts
| Callout | Component | Icon |
|---|---|---|
| Disclaimer (main) | `st.warning` | ⚕️ |
| Known weakness (e.g. typical angina: "Known weakness: this estimate is probably too low…"): shown **first in the result card, above the risk number** | `st.error` | ⚠️ |
| Unusual patient | `st.warning` | 🧭 |
| Known-limitation example note | `st.info` (sidebar) | 🧪 |
| Screening complete | `st.success` | 🏁 |
| Invalid input ("Some inputs aren't valid, so no assessment was made: …") | `st.error` | 🚫 |
| Unexpected failure ("Something went wrong while assessing this patient…"): never a traceback | `st.error` | 🚫 |
| Rate limit ("Too many assessments in a short time. Please wait N seconds…") | `st.warning` | ⏳ |
| Shared limit ("CardioStage is busy with many assessments right now. Please wait N seconds…") | `st.warning` | ⏳ |
| Models unavailable ("The models couldn't be loaded right now. Please try again in a few minutes.") | `st.error` (stops the page) | – |
| Model integrity failure ("**Model integrity check failed.** … Rebuild the models with `python -m cardiostage.train_all`.") | `st.error` (stops the page) | – |

**Error-message rules:** say what happened and what to do next, in plain English; never show stack traces, file paths or internal values (`client.showErrorDetails = "none"`); no result is shown when an assessment fails.

### 5.5 Contribution chart (`ui.contribution_chart`, Plotly)
Horizontal bars, labels `Measurement = value`, coral `#FF8A65` positive / blue `#5B8FE8` negative (same as the site), values `+12.3` outside bars, symmetric x-range (≥ ±5 pts), hover shows "percentage points", no mode bar, transparent background, grid `rgba(243,238,230,0.08)`. **Text:** measurement labels 15 px in warm ink `#F3EEE6` (they're content, not axis decoration); value labels 14 px warm ink; axis ticks/title 13–14 px `#A9A196`; 44 px per row, bar gap 0.35.

### 5.6 Results charts (`app/charts.py`, Plotly)
Nine charts, one per figure the page used to show (sealed test, patient flow, AUC by stage, calibration, external AUC, external calibration, fairness, global importance, case study), drawn from committed data only (`reports/*.csv`, `reports/chart_data.json`).

| Rule | Specification |
|---|---|
| Background | Transparent (the page's `#080B12` shows through); grid `rgba(243,238,230,0.08)`; axes `rgba(243,238,230,0.22)` |
| Text | Category labels (hospitals, groups, measurements) in primary ink `#F3EEE6`; ticks and axis titles `#A9A196`; value labels primary ink, never series colour |
| Categorical series | Fixed order, validated for the dark surface (dataviz validator: lightness band, chroma, CVD ΔE ≥ 8, contrast ≥ 3:1): `#5B8FE8` blue · `#D95926` orange · `#199E70` aqua · `#C98500` yellow; neutral reference `#A9A196` (Cleveland, "All patients") |
| Meaning colours | Coral `#FF8A65` raises risk / referred; blue `#5B8FE8` lowers risk; mint `#8EE6C2` reassured; onward `rgba(91,143,232,0.55)` (same as the site) |
| Marks | Lines 2 px; markers 8–12 px with a 2 px surface ring; 2 px surface gaps between stacked segments; error bars 1.5–2 px |
| Labels | Selective direct labels; on CI charts the value sits **just past the upper whisker** (never on it); contribution labels use `signed()` (no `-0.0`) |
| Legends | Required for ≥ 2 series; on multi-panel charts the legend has its own row **above** the panel titles |
| Numbers that don't fit | Per-panel statistics (ECE values, which calibration the app uses) go in a **caption under the chart**, not inside panels, so they never collide at narrow widths and also serve as a text alternative |
| Interaction | Hover tooltips with exact values and CIs; no mode bar |
| Tables | The tabs keep their data tables (the table view for each chart) |

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
- Measured contrast (WCAG 2.1) on `#080B12`: ink 17.0:1, ink-2 11.1:1, ink-3 7.7:1 (7.1:1 on cards), peach 11.2:1, mint 13.4:1, coral 8.5:1, blue 6.1:1: all pass AA, most AAA. Dark text on peach buttons 10.7:1. White on peach (1.76:1) is **not used**.
- Site: skip link, semantic landmarks and headings, visible focus rings, SplitText keeps words readable to screen readers, decorative SVGs `aria-hidden`, full `prefers-reduced-motion` support, `<noscript>` note (all text content is in the HTML; only charts need JavaScript).
- Tooltips supplement, never replace, visible labels.

## Changelog
| Date | Change |
|---|---|
| 2026-11-24 | Known-weakness callout (⚠️ `st.error`, above the risk number) for typical angina, after the Iran external test |
| 2026-11-23 | Results page charts redrawn in Plotly (§5.6): dark categorical palette validated, labels beyond whiskers, legend row above panel titles, statistics in captions |
| 2026-11-23 | **Premium redesign:** new dark warm palette (§2.4–2.5), Fraunces + Inter self-hosted typography (§2A), illustrations and motion rules (§2B), landing site (§3A), app restyle (dark theme, coral/blue contribution chart, secondary submit buttons for contrast), measured contrast ratios |
| 2026-11-23 | UI polish: sliders for measurements, short example names + description, reset clears example, progressive result card, larger/darker chart text, Results figure widths |
| 2026-11-23 | Added error, rate-limit and integrity callouts and error-message rules (security hardening) |
| 2026-11-23 | Document created at v1.0 |
