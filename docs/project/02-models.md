# CardioStage: Models Document

Everything about the data, models, thresholds and evaluation: enough to understand, audit or reproduce every number CardioStage produces.

| | |
|---|---|
| **Last updated** | 2026-11-23 |
| **Model version** | v1.0 (built by `python -m cardiostage.train_all`) |
| **Related docs** | [PRD](01-product-requirements.md) · [Design system](03-design-system.md) · [Architecture](04-architecture.md) |

---

## 1. Model card (summary)
| | |
|---|---|
| **Task** | Binary classification: probability of angiographic coronary disease (>50% narrowing in any major vessel) |
| **Intended use** | Education and portfolio demonstration of staged, calibrated, explainable screening |
| **Not intended for** | Any clinical decision about a real person |
| **Training data** | 243 Cleveland patients (UCI Heart Disease, 1980s), 46% with disease |
| **Final models** | Stage 1: logistic regression · Stages 2–3: Platt-calibrated soft-voting ensemble (LR + RF + XGBoost) |
| **Headline performance** | Sealed test (61 pts): 0/28 sick missed, recall 1.000 [0.877, 1.000], 49% needed invasive tests · CV: 40% fewer invasive tests than testing everyone, at matched recall |
| **Key limitations** | Small, old, single-site data; referral population; local thresholds; stage 3 not externally validated; atypical presentations in women (see §11) |

## 2. Data
### 2.1 Source
UCI Heart Disease dataset (Janosi, Steinbrunn, Pfisterer, Detrano, 1988; CC BY 4.0), combined four-hospital version via Kaggle `redwankarimsony/heart-disease-data`. File: `data/raw/heart_disease_uci.csv` (920 rows × 16 columns; never edited).

| Hospital | Raw rows | After cleaning | Disease rate |
|---|---|---|---|
| Cleveland | 304 | 304 | 46% |
| Hungary | 293 | 292 | 36% |
| VA Long Beach | 200 | 199 | 74% |
| Switzerland | 123 | 123 | 93% |

### 2.2 Columns
| Column | Meaning | Type | Values / units |
|---|---|---|---|
| `id` | Row identifier | id | not used |
| `age` | Age | numeric | years (29–77 in training) |
| `sex` | Sex | binary | Male → 1.0, Female → 0.0 |
| `dataset` | Hospital | split key | **never a model input** |
| `cp` | Chest pain type | categorical | typical angina, atypical angina, non-anginal, asymptomatic |
| `trestbps` | Resting blood pressure | numeric | mm Hg |
| `chol` | Serum cholesterol | numeric | mg/dl |
| `fbs` | Fasting blood sugar > 120 mg/dl | binary | 1.0 / 0.0 |
| `restecg` | Resting ECG | categorical | normal, st-t abnormality, lv hypertrophy |
| `thalch` | Max heart rate on treadmill | numeric | bpm |
| `exang` | Exercise-induced angina | binary | 1.0 / 0.0 |
| `oldpeak` | ST depression (exercise vs rest) | numeric | mm (negative = ST elevation) |
| `slope` | ST segment slope at peak | categorical | upsloping, flat, downsloping |
| `ca` | Major vessels coloured by fluoroscopy | numeric | 0–3 |
| `thal` | Thallium scan | categorical | normal, fixed defect, reversable defect |
| `num` | Angiographic diagnosis | target source | 0 (healthy) – 4 |

### 2.3 Cleaning rules (`data.py::clean_data`), applied row-wise, safe before splitting
| # | Rule | Reason |
|---|---|---|
| 1 | `chol == 0` and `trestbps == 0` → NaN (172 + 1 values) | Physiologically impossible; zeros encode "not recorded" (all Swiss cholesterol) |
| 2 | Drop exact duplicates ignoring `id` (920 → 918) | Prevents a patient being in both train and test |
| 3 | `sex`, `fbs`, `exang` → 1.0 / 0.0 (NaN kept) | Consistent numeric binaries |
| 4 | `has_disease = (num > 0)` | Binary target |
| Kept | `oldpeak = 0` (normal) and 12 negative `oldpeak` (ST elevation) | Real clinical values |

### 2.4 Missingness (after cleaning)
Stage-3 features are 96–99% (`ca`) and 42–90% (`thal`) missing outside Cleveland; Swiss cholesterol 100% missing; VA ~28% missing on BP, cholesterol and treadmill values. Hence **training on Cleveland only** (owner decision, 2026-11-23).

### 2.5 Splits
| Split | Patients | Definition |
|---|---|---|
| Train | 243 (111 sick) | Cleveland, stratified 80%, `random_state = 42` (`split_cleveland`) |
| Sealed test | 61 (28 sick) | Remaining 20%; opened once in Phase 9 |
| External | 614 | All Hungary, Switzerland, VA Long Beach patients |
| CV | 5 folds × 3 repeats | `RepeatedStratifiedKFold(5, 3, random_state=42)`; inner `StratifiedKFold(5, shuffle, 42)` |

## 3. Features and stages
| Stage | Name | Features (cumulative) | Count |
|---|---|---|---|
| 1 | Basic check-up | age, sex, cp, trestbps, chol, fbs | 6 |
| 2 | + Treadmill stress test | + restecg, thalch, exang, oldpeak, slope | 11 |
| 3 | + Invasive imaging | + ca, thal | 13 |

Defined once in `config.STAGES`.

## 4. Preprocessing (`preprocessing.py::build_preprocessor(stage)`)
A `ColumnTransformer` inside each pipeline, **fitted on training folds only** (no leakage):

| Type | Columns | Steps |
|---|---|---|
| Numeric | age, trestbps, chol, thalch, oldpeak, ca | `SimpleImputer(median)` → `StandardScaler` |
| Binary | sex, fbs, exang | `SimpleImputer(most_frequent)` |
| Categorical | cp, restecg, slope, thal | `SimpleImputer(most_frequent)` → `OneHotEncoder(handle_unknown="ignore")` |

Output: pandas DataFrame with readable names (9 / 18 / 22 columns at stages 1 / 2 / 3). **No missing-indicator columns**: missingness encodes the hospital (a shortcut).

## 5. Candidate models and tuning (`models.py`)
| Model | Fixed settings | Grid (`model__` prefix) | Combos |
|---|---|---|---|
| Logistic regression | `max_iter=5000` | C ∈ {0.01, 0.03, 0.1, 0.3, 1, 3, 10} | 7 |
| Random forest | 300 trees, seed 42 | max_depth ∈ {3, 5, None}; min_samples_leaf ∈ {1, 5, 10}; max_features ∈ {sqrt, 0.5} | 18 |
| XGBoost | logloss, seed 42 | n_estimators ∈ {100, 300}; max_depth ∈ {2, 3, 4}; learning_rate ∈ {0.03, 0.1}; min_child_weight ∈ {1, 5}; subsample 0.8; colsample 0.8 | 24 |
| Ensemble | soft voting (mean probability) of the three tuned models | – | – |

**Selection:** nested CV, inner grid search scored by ROC-AUC, outer 15 folds graded. Per stage, the candidate with the highest mean outer ROC-AUC wins.

### 5.1 Model comparison (nested CV, outer-fold mean ± sd ROC-AUC)
| Candidate | Stage 1 | Stage 2 | Stage 3 |
|---|---|---|---|
| Logistic regression | **0.840 ± 0.046** | 0.855 ± 0.040 | 0.899 ± 0.028 |
| Random forest | 0.832 ± 0.040 | 0.849 ± 0.037 | 0.894 ± 0.021 |
| XGBoost | 0.829 ± 0.048 | 0.850 ± 0.043 | 0.892 ± 0.025 |
| Ensemble | 0.837 ± 0.046 | **0.856 ± 0.038** | **0.900 ± 0.024** |

All candidates are within noise of each other.

## 6. Final models (trained on all 243 training patients)
| Stage | Model | Calibration | Tuned hyperparameters |
|---|---|---|---|
| 1 | Logistic regression | none (sigmoid worsened Brier) | C = 3.0 |
| 2 | Ensemble in `CalibratedClassifierCV(method="sigmoid", cv=5)` | Platt | LR C = 0.3 · RF max_depth 3, min_samples_leaf 10, max_features sqrt · XGB 300 trees, depth 2, lr 0.03, min_child_weight 5 |
| 3 | Ensemble in `CalibratedClassifierCV(method="sigmoid", cv=5)` | Platt | LR C = 0.1 · RF max_depth None, min_samples_leaf 10, max_features sqrt · XGB 300 trees, depth 4, lr 0.03, min_child_weight 5 |

### 6.1 Calibration comparison (pooled out-of-fold, 729 predictions per stage)
| Stage | Variant | Brier | ECE | ROC-AUC |
|---|---|---|---|---|
| 1 | **uncalibrated** | **0.1643** | 0.044 | 0.835 |
| 1 | sigmoid | 0.1664 | 0.041 | 0.831 |
| 1 | isotonic | 0.1676 | 0.066 | 0.826 |
| 2 | uncalibrated | 0.1568 | 0.035 | 0.851 |
| 2 | **sigmoid** | **0.1564** | 0.031 | 0.851 |
| 2 | isotonic | 0.1588 | 0.036 | 0.850 |
| 3 | uncalibrated | 0.1293 | 0.052 | 0.896 |
| 3 | **sigmoid** | **0.1265** | 0.047 | 0.898 |
| 3 | isotonic | 0.1281 | 0.039 | 0.892 |

Chosen by lowest Brier. ECE uses 10 equal-count bins; per-fold ECE is unreliable (~5 patients per bin).

## 7. Decision thresholds (frozen)
Derived from calibrated out-of-fold probabilities (mean of 3 repeats) on the training set (`staging.compute_zones`, `thresholds.py`).

| Stage | Rule-out (clear) below | Rule-in (refer) from | Rule |
|---|---|---|---|
| 1 | **8.97%** | **82.97%** | Rule-out: highest t keeping ≥ 99% of sick patients ≥ t · Rule-in: lowest t with precision ≥ 90% |
| 2 | **13.36%** | **78.24%** | same |
| 3 | – | **14.85%** (screening) | Highest t catching ≥ 97% of sick patients |

Config: `SCREENING_RECALL = 0.97`, `RULE_OUT_RECALL = 0.99`, `RULE_IN_PRECISION = 0.90`.

**Policy** (`staging.simulate_policy`): stage 1 → refer if ≥ rule-in, clear if < rule-out, else stage 2 → same → stage 3 screening threshold.

## 8. Uncertainty and novelty
### 8.1 Plausible range (`uncertainty.SubsampleEnsemble`)
20 copies of each final model (`N_REPLICAS`), each fitted on a random 80% of training patients **without replacement** (`REPLICA_FRACTION`), including the calibrator. The range is the 10th–90th percentile of their predictions (`UNCERTAINTY_PERCENTILES`).
**Evaluation** (stage-3 decision, out-of-fold): flagged 2/11 missed sick, 19/216 false alarms, 3/322 correctly referred, 46/180 correctly cleared; median range width 6.7 pts → **weak error signal**, so it's **display-only** (`USE_UNCERTAINTY_GUARD = False`). As a guard it would recover 1 more sick patient of 111, at a cost of invasive tests 60% → 72%.

### 8.2 Unusual-patient detector (`uncertainty.NoveltyDetector`)
- **Range check:** numeric inputs outside the training min–max. Training ranges: age 29–77, trestbps 94–200, chol 126–564, thalch 71–202, oldpeak 0.0–6.2 (**negative values are always flagged**), ca 0–3.
- **Combination check:** Isolation Forest (300 trees, seed 42) on the stage's preprocessed features; flagged if score < 1st percentile of training scores (`NOVELTY_QUANTILE = 0.01`). Thresholds: −0.6174 / −0.6175 / −0.6003 (stages 1/2/3).
- **Flag rates:** Cleveland training 1.2%; Hungary 1.4–2.4%; VA 2.0–7.5%; Switzerland 0.8% (stage 1) / 13.0% (stages 2–3).
- **Validity:** external flagged patients had worse Brier scores (stage 1: 0.221 vs 0.161, n = 12; stage 2: 0.198 vs 0.148, n = 28).

## 9. Explanations (`explain.StageExplainer`)
- **Method:** SHAP `PermutationExplainer` (model-agnostic) in probability units, over the **13 original features**. Categoricals are integer-coded for SHAP and decoded before prediction.
- **Background:** 50 training patients, stratified by diagnosis (baselines 46–48% vs true 46%).
- **Guarantee:** baseline + contributions = predicted risk (additivity error ~1e-15).
- **Speed:** ~0.2 s (stage 1), ~3 s (stages 2–3) per patient.
- **Global importance** (mean |SHAP|, percentage points): stage 1 cp 21.9, sex 13.3, age 6.7 · stage 2 cp 13.1, sex 7.0, oldpeak 5.3, slope 5.3 · stage 3 thal 11.8, ca 10.0, cp 8.6. fbs ≈ 0 at all stages.
- **Direction checks:** 12/12 pass (e.g. higher thalch → lower risk, corr −0.96).

## 10. Performance summary
### 10.1 Staged policy vs alternatives (CV, 243 patients, calibrated)
| Strategy | Recall | Specificity | Missed | False alarms | Treadmill | Invasive |
|---|---|---|---|---|---|---|
| Everyone: stage 1 only | 0.973 | 0.242 | 3 | 100 | 0% | 0% |
| Everyone: stage 2 only | 0.973 | 0.288 | 3 | 94 | 100% | 0% |
| Everyone: all tests | 0.973 | 0.447 | 3 | 73 | 100% | 100% |
| **Staged policy** | **0.964** | **0.470** | **4** | **70** | **76%** | **60%** |

Bootstrap (2,000) staged − all tests: recall −0.009 [−0.029, 0.000]; specificity +0.023 [0.000, 0.052]; invasive −0.399 [−0.461, −0.333].

### 10.2 Sealed test set (61 patients, 28 sick, frozen thresholds)
| Stage | ROC-AUC [95% CI] | CV estimate | Brier |
|---|---|---|---|
| 1 | 0.857 [0.756, 0.949] | 0.837 | 0.151 |
| 2 | 0.942 [0.884, 0.988] | 0.855 | 0.108 |
| 3 | 0.960 [0.902, 0.996] | 0.899 | 0.085 |

| Strategy | Recall (exact CI) | Specificity (exact CI) | Missed | Invasive |
|---|---|---|---|---|
| Everyone: all tests | 1.000 [0.877, 1.000] | 0.455 [0.281, 0.636] | 0 | 100% |
| **Staged policy** | **1.000 [0.877, 1.000]** | **0.515 [0.335, 0.692]** | **0** | **49%** |

Test > CV is attributed to sampling variation; CV remains the expectation.

### 10.3 External validation (unchanged models)
| Hospital | n | Stage 1 AUC | Stage 2 AUC | Stage-1 ECE → after prior shift | Stage-1 clear-zone NPV |
|---|---|---|---|---|---|
| Hungary | 292 | 0.840 [0.787, 0.885] | 0.892 [0.848, 0.932] | 0.085 → 0.074 | 0.90 (6 sick cleared) |
| VA Long Beach | 199 | 0.718 [0.632, 0.800] | 0.741 [0.657, 0.826] | 0.121 → 0.101 | – |
| Switzerland | 123 (8 healthy) | 0.767 [0.483, 0.946] | 0.776 [0.583, 0.961] | 0.257 → 0.039 | – |

Prior shift: odds × (local odds / training odds), `stats.prior_shift` (demonstration; not in the app).

### 10.4 Fairness (CV, staged policy)
| Group | n (sick) | Stage-3 AUC | Recall | Missed | Specificity |
|---|---|---|---|---|---|
| Women | 78 (18) | 0.891 [0.804, 0.970] | 0.889 [0.722, 1.000] | 2 | 0.567 |
| Men | 165 (93) | 0.880 [0.823, 0.926] | 0.978 [0.944, 1.000] | 2 | 0.389 |
| Under 50 | 70 (21) | 0.930 | 0.952 | 1 | 0.714 |
| 50–59 | 100 (48) | 0.893 | 0.979 | 1 | 0.385 |
| 60+ | 73 (42) | 0.867 | 0.952 | 2 | 0.226 |

External by sex: women AUC 0.864 / 0.848, men 0.807 / 0.851 (stages 1 / 2). Missed women: one atypical-angina case cleared at stage 1 (female −21 pts, atypical −21 pts; stage 3 would refer via 2 blocked vessels), one exactly at the threshold. No mitigation applied (S6 in PRD).

## 11. Limitations
1. 243 training patients, one hospital, 1980s.
2. Referral population: associations such as "asymptomatic → higher risk" are selection effects.
3. Thresholds are population-specific (Hungary clear zone less safe).
4. Stage 3 not externally validated.
5. Atypical presentations, especially in women, may be cleared early.
6. SHAP explains the model, not causation; tree components create step-shaped effects (age ~57, chol ~230).
7. The plausible range is not a validated error detector.

## 12. Artefacts
| File | Size | Contents |
|---|---|---|
| `models/stage1.joblib` | 4.6 MB | `model`, `uncertainty` (20 copies), `novelty`, `model_name`, `calibration`, `features`, `zones` |
| `models/stage2.joblib` | 80 MB | same |
| `models/stage3.joblib` | 85 MB | same (load ~7 s) |
| `models/phase4_oof.joblib`, `phase5_oof.joblib` | <0.1 MB | out-of-fold predictions (analysis inputs) |
| `models/phase3_*.joblib`, `phase7_shap.joblib` | <1 MB | Phase 3 baselines, SHAP values (written only; never loaded by code) |
| `models/manifest.json` | <1 KB | SHA-256 of `stage{1,2,3}.joblib`, `phase4_oof.joblib`, `phase5_oof.joblib`; written by `calibration.main` or `python -m cardiostage.integrity` |
| `reports/*.csv`, `reports/phase*_zones.json` | small | every result table (committed) |

`models/` is git-ignored; rebuild with `python -m cardiostage.train_all` (~10 minutes), which also rewrites the manifest.

**Integrity:** every pickle the code loads goes through `integrity.load`, which compares the file's SHA-256 with `manifest.json` and refuses to unpickle unlisted or modified files (`IntegrityError`). Bundles from elsewhere are therefore rejected unless you regenerate the manifest yourself. Only do that for files you built.

### 12.1 Inference input contract (`predictor.to_frame`)
Before scoring, the engine validates every input and raises `InvalidInputError` otherwise:

| Input | Accepted values |
|---|---|
| `cp`, `restecg`, `slope`, `thal` | Exactly the training categories (`predictor.CHOICES`) |
| `sex`, `fbs`, `exang` | 0 or 1 |
| `ca` | 0, 1, 2 or 3 |
| `age` | 18–100 |
| `trestbps` | 60–250 mm Hg |
| `chol` | 80–700 mg/dl |
| `thalch` | 60–230 bpm |
| `oldpeak` | −3.0 to 7.0 mm |
| Any feature | Missing (`None`/NaN) → imputed with training median/mode; numbers must be finite |

Values inside these plausible limits but outside the training ranges (§8.2) are accepted and flagged as unusual.

## 13. Reproduction
```bash
python -m cardiostage.data                 # cleaned CSV
python -m cardiostage.eda                  # figures 01-04
python -m cardiostage.train_baselines      # Phase 3, figure 05
python -m cardiostage.from_scratch         # figure 06
python -m cardiostage.train_all            # Phases 4-5: deployable models, figures 07-11
python -m cardiostage.external_validation  # figures 12-13
python -m cardiostage.fairness             # figure 14
python -m cardiostage.explanations         # figures 15-17
python -m cardiostage.final_evaluation     # figure 18 (sealed test)
```

## Changelog
| Date | Change |
|---|---|
| 2026-11-23 | Added integrity manifest (§12) and the inference input contract (§12.1) after security hardening; models and metrics unchanged |
| 2026-11-23 | Document created at v1.0 (all phases complete) |
