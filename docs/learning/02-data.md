# Phase 2: Data Exploration & Cleaning

**Goal:** understand the data deeply, fix what's broken, and turn it into something models can use, without fooling ourselves along the way.

> "Garbage in, garbage out." Most real ML work is this phase. A fancy model trained on misunderstood data produces confident nonsense.

**Files in this phase**

| File | Job |
|---|---|
| `src/cardiostage/data.py` | Load the raw CSV and apply data-quality fixes |
| `src/cardiostage/preprocessing.py` | Fill gaps, encode text, scale numbers, *learned from training data only* |
| `src/cardiostage/eda.py` | Draw the exploration charts in `reports/figures/` |
| `tests/test_data.py` | 12 checks that cleaning and preprocessing behave correctly |

Run it yourself:
```bash
python -m cardiostage.data   # creates data/processed/heart_clean.csv
python -m cardiostage.eda    # creates the 4 charts
pytest
```

---

## 1. The medical columns, in plain English

| Column | What it is | How to read it |
|---|---|---|
| `age` | Age in years | Risk rises with age |
| `sex` | 1 = male, 0 = female | Men develop heart disease earlier on average |
| `cp` | **Chest pain type** | See below. The most surprising column |
| `trestbps` | Resting blood pressure (mm Hg) | Normal is about 120; 140+ is high |
| `chol` | Cholesterol in the blood (mg/dl) | Under 200 is desirable; 240+ is high |
| `fbs` | Fasting blood sugar > 120 mg/dl | 1 suggests diabetes, a major heart risk factor |
| `restecg` | Resting ECG (heart's electrical trace) | `normal`, `st-t abnormality` (irregular waves), `lv hypertrophy` (thickened heart wall, often from high blood pressure) |
| `thalch` | **Max heart rate** on the treadmill | A healthy heart speeds up a lot; a diseased one often can't |
| `exang` | Chest pain *during exercise* | When the heart works harder and its blood supply is blocked, it hurts |
| `oldpeak` | **ST depression** | How far a specific part of the ECG trace (the "ST segment") dips under exercise. A dip suggests the heart muscle isn't getting enough blood |
| `slope` | Shape of that ST segment at peak exercise | `upsloping` is usually normal; `flat` / `downsloping` are warning signs |
| `ca` | Number of major vessels (0–3) visible with dye on X-ray (fluoroscopy) | Relates to how many arteries are affected |
| `thal` | Thallium nuclear scan | `normal`; `fixed defect` (permanently damaged area, e.g. old heart attack); `reversable defect` (area that lacks blood under stress but recovers: active blockage) |
| `num` | Diagnosis from **angiography** (the gold-standard test) | 0 = <50% artery narrowing (healthy); 1–4 = >50% narrowing in an increasing number of vessels |

**Chest pain types, from most to least "classic":**
- `typical angina`: the textbook pattern: pressure-like chest pain triggered by exertion, relieved by rest.
- `atypical angina`: some, but not all, of those features.
- `non-anginal`: chest pain that doesn't look heart-related.
- `asymptomatic`: no chest pain at all.

## 2. What we found (and the chart for each)

### Finding 1: The hospitals are very different (`01_disease_rate_by_hospital.png`)
| Hospital | Disease rate |
|---|---|
| Hungary | 36% |
| Cleveland | 46% |
| VA Long Beach | 74% |
| Switzerland | 93% |

Each hospital referred different kinds of patients. A model trained on Hungary (mostly healthy) and tested on Switzerland (mostly sick) faces a very different world. This difference between training and real-world data is called **dataset shift**, and it's exactly what our cross-hospital experiment (feature B) will measure.

### Finding 2: Hospitals recorded different tests (`02_missing_by_hospital.png`)
The single most important chart of the project so far:
- **Cleveland** recorded almost everything.
- **Switzerland never recorded cholesterol** (it was stored as 0, see Fix 1 below).
- **Stage 3 tests (`ca`, `thal`) are almost entirely missing outside Cleveland**: 96–99% missing for `ca`.
- VA Long Beach is missing ~28% of its treadmill results.

This directly shapes how we can train the staged models (a decision for Phase 3, see the end of this guide).

### Finding 3: What separates sick from healthy (`03`, `04`)
- **Max heart rate** is clearly lower in sick patients: their hearts can't reach high rates under stress.
- **ST depression** is near 0 for healthy patients and spread out higher for sick ones.
- **Age** is shifted higher for sick patients.
- **Blood pressure and cholesterol barely differ.** Surprising, but common in referral datasets: everyone sent for testing already tends to have elevated values.
- **Exercise chest pain:** 84% disease when present vs 36% when absent.
- **Thallium scan:** a `reversable defect` means 80% disease; `normal` means 30%.

### Finding 4: The "no chest pain" paradox
Patients with **no chest pain (`asymptomatic`) have the HIGHEST disease rate (79%)**, while `atypical angina` has only 14%.
How? These are all patients *referred to a cardiology clinic*. Someone without chest pain who still got referred probably had other alarming signs (an abnormal ECG, a failed stress test). Heart disease can also be "silent", especially in people with diabetes.
**Lesson:** a dataset reflects *how patients were selected*, not just biology. A model learns these patterns faithfully, which is why we'll need explanations (feature C) to spot them.

## 3. The cleaning fixes (in `data.py`)

| # | Problem found | Fix | Why it matters |
|---|---|---|---|
| 1 | 172 cholesterol values and 1 blood-pressure value are **0** | Convert to missing (`NaN`) | Nobody alive has cholesterol 0. Since most Swiss patients are sick, leaving zeros would teach *"cholesterol 0 = sick"*, a nonsense shortcut |
| 2 | **2 pairs of identical patients** | Drop the copies (920 → 918 rows) | If one copy lands in training and the other in testing, the model is "tested" on a patient it memorised, inflating scores |
| 3 | Yes/no columns stored as text or True/False | Convert to 1.0 / 0.0 | Models need numbers |
| 4 | Target `num` is 0–4 | `has_disease = 1 if num > 0` | We answer a yes/no question |

**Things we deliberately did *not* "fix":**
- **`oldpeak` = 0** is a normal result for many patients, so it's not missing.
- **12 negative `oldpeak` values** mean ST *elevation*, a real ECG finding. Changing them would destroy real information.

## 4. Preprocessing and the #1 rule: no data leakage

After cleaning, data still has gaps and text. `preprocessing.py` fixes that with three treatments:

| Column type | Steps | Example |
|---|---|---|
| Numeric (`age`, `chol`, …) | Fill gaps with the **median** → **standardise** (mean 0, spread 1) | Cholesterol 233 → −0.24 ("slightly below average") |
| Binary (`sex`, `fbs`, `exang`) | Fill gaps with the **most common** value | Missing `fbs` → 0 |
| Categorical (`cp`, `thal`, …) | Fill gaps with the most common value → **one-hot encode** | `cp = asymptomatic` → `cp_asymptomatic=1`, the other three cp columns = 0 |

Why each step:
- **Median, not mean:** a few extreme values (cholesterol 603) drag the mean around, but not the median.
- **Standardising:** logistic regression compares features through their numbers. Unscaled, cholesterol (~200) would swamp ST depression (~1).
- **One-hot, not 1/2/3/4:** numbering chest-pain types would tell the model "type 4 is twice type 2", which is meaningless.

### Data leakage, the most important concept in this phase
**Leakage** = information from the test data sneaking into training. It makes a model look better than it really is.

Example: suppose we filled missing cholesterol with the median of **all 918 patients**, then split into train and test. The training data now contains a number partly computed *from the test patients*. The model has had a tiny peek at the exam.

That's why filling and scaling live in a scikit-learn **transformer** that we:
1. **`fit`** on training data only: it *learns* the medians, the scaling, the category list;
2. **`transform`** any data with what it learned: test patients, other hospitals, and later real users of the app.

`test_preprocessor_learns_only_from_training_data` proves this works: the fill value equals the median of the *training* rows, not of everyone.

(Cleaning in `data.py` is safe to do on everything, because each fix uses only the row itself. "This value is 0, so it's missing" doesn't depend on any other patient.)

### Why no "was missing" flag columns?
A common trick is adding columns like `chol_was_missing`. We deliberately **don't**. In this data, missingness reveals the hospital: missing cholesterol almost always means Switzerland (93% sick). The model would learn *"missing cholesterol → sick"*, a shortcut that encodes the hospital, not the patient.

## 5. Check your understanding
1. Why did we convert cholesterol 0 to missing instead of leaving it?
2. Why is filling missing values on the whole dataset *before* splitting a problem?
3. Why do asymptomatic patients have the highest disease rate here?
4. Why don't we one-hot encode `age`?

## Answers

**1.** Zero cholesterol is physically impossible, so it really means "not measured". All Swiss patients have it, and 93% of them are sick. Left in, the model would learn "cholesterol 0 → disease": a pattern about record-keeping, not biology, which would mislead it on any new patient.

**2.** That's data leakage. The fill values (medians) would be computed partly from test patients, so the model indirectly sees test information during training and its test score becomes over-optimistic. Fitting the preprocessor only on training data keeps the test set truly unseen, like a real future patient.

**3.** Selection effects. Everyone in this dataset was referred for heart testing. A person with no chest pain was only referred if something else looked wrong (abnormal ECG, risk factors), so this group is enriched with sick patients. Silent heart disease, common in diabetics, also contributes. The data reflects how patients were chosen, not just how disease works.

**4.** Age is a real number where order and distance are meaningful: 60 is older than 50 by the same amount 50 is older than 40. One-hot encoding is for categories with no natural order. Turning every age into its own yes/no column would throw away that ordering, and create dozens of sparse columns.

---

## Open decision for Phase 3: who do we train on?

Finding 2 creates a real design choice:

- **Option 1 (recommended): train all stages on Cleveland only.**
  Cleveland has nearly complete data for every stage, so all three stage models are trained and compared on **the same patients**. That makes "how much does each test add?" a fair comparison. Hungary, Switzerland and VA then become **completely unseen test hospitals** for Stages 1–2 (feature B). Downside: only 304 training patients, so we use cross-validation (Phase 3) to get reliable numbers.
- **Option 2: pool all hospitals for Stages 1–2, Cleveland only for Stage 3.** More training data for early stages, but the stages would be trained on different patients, so the stage comparison is no longer apples-to-apples.
- **Option 3: pool everything and fill the gaps.** Not recommended. About two-thirds of Stage 3 values would be invented by the imputer, which is why `ca = 3` came out as an extreme 4.41 after scaling on pooled data.
