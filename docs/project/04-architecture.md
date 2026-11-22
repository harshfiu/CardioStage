# CardioStage: Architecture Document

How the code is organised, how data flows from the raw CSV to an on-screen explanation, and why it's built this way.

| | |
|---|---|
| **Last updated** | 2026-11-23 |
| **Stack** | Python 3.12 · pandas 3.1 · scikit-learn 1.9 · XGBoost 3.4 · SHAP 0.54 · Streamlit 1.67 · Plotly 7.1 · matplotlib/seaborn · pytest 9.2 · ruff 0.14 |
| **Related docs** | [PRD](01-product-requirements.md) · [Models](02-models.md) · [Design system](03-design-system.md) |

---

## 1. System overview

```
             ┌────────────────────────── OFFLINE: training & evaluation ──────────────────────────┐
 data/raw/   │  data.py ─► preprocessing.py ─► models.py ─► staging.py ─► calibration.py           │
 heart_      │  (clean,     (per-stage        (pipelines,   (nested CV,    (calibration,          │
 disease_    │   split)      transformer)      grids)        zones,         uncertainty copies,    │
 uci.csv ───►│                                               policy)        novelty detector)      │
             │                                                   │               │                 │
             │   external_validation.py · fairness.py · explanations.py · final_evaluation.py     │
             └───────────────────────────────────┬────────────────┼─────────────────────────────────┘
                                                 ▼                ▼
                                      reports/ (CSV, JSON,   models/stage{1,2,3}.joblib
                                      figures/*.png)         (git-ignored, ~170 MB total)
                                                                  │
             ┌──────────────────────────── ONLINE: the app ───────┼────────────────────────────────┐
             │  app/streamlit_app.py (navigation)                 ▼                                 │
             │     ├─ views/screener.py ──► predictor.py (CardioStagePredictor) ──► explain.py     │
             │     ├─ views/results.py  ──► reports/*.csv, figures                                  │
             │     └─ views/about.py         ui.py: cached loading, result card, chart, disclaimer │
             └─────────────────────────────────────────────────────────────────────────────────────┘
```

Everything runs **locally**. There's no server-side database, no network calls at inference, and no external APIs.

## 2. Repository layout
```
CardioStage/
├── app/
│   ├── streamlit_app.py        entry point: set_page_config + st.navigation
│   ├── ui.py                   shared UI: get_predictor (cached), render_assessment, contribution_chart, DISCLAIMER
│   └── views/                  screener.py · results.py · about.py
├── data/
│   ├── raw/heart_disease_uci.csv   original data (committed, never edited)
│   ├── processed/              generated cleaned CSV (git-ignored)
│   └── README.md               source, licence, hospital counts
├── docs/
│   ├── learning/               9 beginner guides + index
│   └── project/                these 4 living documents + index
├── models/                     generated artefacts (git-ignored except .gitkeep)
├── reports/                    result CSV/JSON (committed) + figures/ (committed)
├── src/cardiostage/            the installable package (see §3)
├── tests/                      59 pytest tests (see §7)
├── .streamlit/config.toml      app theme and settings
├── .gitattributes / .gitignore line endings (LF) / ignored paths
├── pyproject.toml              package metadata, pytest + ruff config
├── requirements.txt            pinned dependencies
├── LICENSE                     MIT (code); CC BY 4.0 note (data)
└── README.md
```

## 3. Package modules (`src/cardiostage/`)
| Module | Responsibility | Key API | Depends on |
|---|---|---|---|
| `config.py` | **Single source of truth**: paths, seed, target, hospitals, stage feature lists, feature types, CV settings, decision targets, uncertainty settings | constants | – |
| `data.py` | Load raw CSV, cleaning rules, sealed split, stage feature selection | `load_raw`, `clean_data`, `load_clean`, `split_cleveland`, `get_features_and_target` | config |
| `preprocessing.py` | Per-stage `ColumnTransformer` (impute/scale/one-hot), pandas output | `build_preprocessor(stage)` | config |
| `models.py` | Candidate classifiers, tuning grids, pipelines | `MODEL_NAMES`, `PARAM_GRIDS`, `build_pipeline(name, stage)` | preprocessing |
| `thresholds.py` | Pure decision functions | `threshold_for_recall`, `threshold_for_precision`, `decision_metrics` | numpy |
| `staging.py` | Phase 4: per-stage nested CV + ensemble, OOF predictions, zones, policy simulation, bootstrap, final-model fitting | `collect_out_of_fold`, `compute_zones`, `simulate_policy`, `fit_final_model` | data, models, thresholds |
| `uncertainty.py` | Subsample ensemble ranges; novelty detection | `SubsampleEnsemble`, `NoveltyDetector`, `straddles` | preprocessing |
| `calibration.py` | Phase 5: calibration comparison, uncertainty evaluation, final bundles (`--report-only` mode) | `make_variant`, `expected_calibration_error`, `main` | staging, uncertainty |
| `stats.py` | Bootstrap CIs, exact proportion CIs, prior shift | `bootstrap_ci`, `exact_proportion_ci`, `prior_shift` | scipy, numpy |
| `explain.py` | SHAP permutation explainer on original features, text formatting | `StageExplainer`, `explanation_text`, `format_value` | shap |
| `predictor.py` | **App decision engine** (no UI code) | `CardioStagePredictor.load()`, `.assess(patient, stage)` → `Assessment` | data, explain, bundles |
| `external_validation.py` | Phase 6a analysis | `main` | stats, calibration |
| `fairness.py` | Phase 6b analysis | `main`, `age_band` | stats, staging |
| `explanations.py` | Phase 7 analysis | `main` | explain |
| `final_evaluation.py` | Phase 9 sealed test | `main` | stats, staging |
| `eda.py`, `train_baselines.py`, `from_scratch.py` | Phases 2–3 analyses | `main` | data, models |
| `train_all.py` | Rebuild deployable models: staging → calibration | `main` | staging, calibration |

**Dependency rule:** analysis scripts depend on core modules, never the reverse. `predictor.py` depends only on core modules and saved bundles, never on analysis scripts. The app depends only on `predictor`, `config` and `reports/`.

## 4. Data flow
### 4.1 Training pipeline (`python -m cardiostage.train_all`, ~10 min)
1. `load_clean()` → 918 rows; `split_cleveland()` → 243 train / 61 sealed test (seed 42).
2. **staging.main** – for each stage: 15 outer folds × (grid search LR/RF/XGB + ensemble) → OOF probabilities, AUC table, chosen candidate → `reports/phase4_*.csv`, `phase4_zones.json`, figures 07–09, `models/phase4_oof.joblib`.
3. **calibration.main** – reads `phase4_zones.json` (chosen candidates) → per stage: re-tune per fold, fit uncalibrated/sigmoid/isotonic → pooled Brier picks method → zones from calibrated OOF → uncertainty ranges via subsample ensembles per fold → reports + figures 10–11 → **final bundles** `models/stage{1,2,3}.joblib` = {model, uncertainty, novelty, model_name, calibration, features, zones}.

### 4.2 Evaluation scripts (read bundles / OOF, write reports)
`external_validation` → figures 12–13 · `fairness` → 14 · `explanations` → 15–17 · `final_evaluation` → 18 (sealed test).

### 4.3 Runtime: one assessment
```
user submits form ─► screener.run_stage(stage)
   └► predictor.assess(patient_dict, stage)
        1. to_frame(): validate categories, NaN for missing → 1-row DataFrame (stage features)
        2. bundle.model.predict_proba → risk
        3. bundle.uncertainty.predict_interval → range (10th–90th pct of 20 copies)
        4. zone(stage, risk) using frozen bundle.zones → headline + recommendation
        5. bundle.novelty.check → unusual reasons;  not_measured list
        6. StageExplainer(stage) (built once, cached) → SHAP values → describe() → summary text
   └► Assessment stored in st.session_state.results[stage]
render_assessment(result) ─► metrics, decision box, warnings, Plotly chart, breakdown table
```

## 5. State, caching and performance
| Concern | Mechanism | Numbers |
|---|---|---|
| Model loading | `@st.cache_resource` on `get_predictor()`, once per server process | ~15 s (stage 3 bundle ~7 s) |
| Explainers | Lazily built per stage, cached in the predictor | built on first explanation |
| Session state | `st.session_state`: input widget keys, `results` {stage: Assessment}, `example` | per browser session |
| Forms | `st.form` so predictions run only on submit | – |
| Assessment latency | prediction + interval + SHAP | ~0.3 s (stage 1), ~3–5 s (stages 2–3) |
| Training | parallel grid search (`n_jobs=-1`), parallel replicas/SHAP chunks (joblib) | full rebuild ~10 min on 20 cores |

## 6. Configuration
All tunables live in `config.py`: `RANDOM_SEED=42`, `TEST_SIZE=0.2`, `CV_FOLDS=5`, `CV_REPEATS=3`, `SCREENING_RECALL=0.97`, `RULE_OUT_RECALL=0.99`, `RULE_IN_PRECISION=0.90`, `CALIBRATION_METHODS`, `N_REPLICAS=20`, `REPLICA_FRACTION=0.8`, `UNCERTAINTY_PERCENTILES=(10, 90)`, `USE_UNCERTAINTY_GUARD=False`, `NOVELTY_QUANTILE=0.01`, stage feature lists, feature types, paths. Changing a value requires re-running `train_all` (and the evaluation scripts) and **updating these docs**.

## 7. Testing
| File | Tests | Covers | Needs `models/` |
|---|---|---|---|
| `test_setup.py` | 4 | dataset shape, hospitals, stage definitions | no |
| `test_data.py` | 12 | cleaning rules, no input mutation, leakage-safe preprocessing, unseen categories | no |
| `test_models.py` | 8 | sealed split reproducibility/stratification, pipelines, from-scratch LR = scikit-learn | no |
| `test_staging.py` | 9 | threshold functions, decision metrics, policy routing | no |
| `test_uncertainty.py` | 7 | ECE, calibration wrapper, intervals, novelty detection | no |
| `test_stats.py` | 7 | bootstrap CI, exact CI, prior shift, fairness helpers | no |
| `test_explain.py` | 5 | encode/decode, SHAP additivity, baseline, text | no |
| `test_predictor.py` | 7 | assessments, zones, missing/unusual input, invalid input, **full app flow via AppTest** | yes (skipped with hint if absent) |
| **Total** | **59** | | |

Run `pytest` (~1 min). Lint: `ruff check src tests app`; format: `ruff format src tests app`.

## 8. Tooling and environment
- **Virtual environment** `.venv/`; `pip install -r requirements.txt && pip install -e .` (editable `src/` package).
- **Pinned versions** in `requirements.txt`.
- **Line endings** normalised to LF via `.gitattributes`.
- **Git workflow:** one commit per phase/change on `main`, pushed to `github.com/harshfiu/CardioStage`.
- **Ignored:** `.venv/`, caches, `data/processed/*`, `models/*`, `.streamlit/secrets.toml`.

## 9. Security and privacy
- No authentication, accounts, or data persistence: inputs live only in the browser session's server-side state and disappear when it ends.
- No outbound network calls during inference; Streamlit usage statistics disabled (`gatherUsageStats = false`).
- Model files are loaded with `joblib` (pickle). **Only load bundles you built yourself**: pickles can execute code.

## 10. Architecture decision records (ADRs)
| # | Decision | Alternatives | Why |
|---|---|---|---|
| ADR-1 | `src/` package layout + editable install | flat scripts | Clean imports everywhere; tests run against the package |
| ADR-2 | All constants in `config.py` | magic values per file | One source of truth |
| ADR-3 | Preprocessing inside sklearn pipelines | preprocess once up front | Prevents leakage; same transform at inference |
| ADR-4 | Cleveland-only training | pool hospitals with imputation | Only complete stage-3 data; fair stage comparison; others become external tests |
| ADR-5 | Nested CV + sealed test | single split / plain CV | Unbiased selection and final estimate |
| ADR-6 | Permutation SHAP on original features | TreeExplainer on one-hot columns | Works on calibrated ensembles; human-readable items |
| ADR-7 | Decision engine separate from UI (`predictor.py`) | logic in Streamlit script | Testable, reusable, readable |
| ADR-8 | `st.navigation` with `views/` | `pages/` auto-discovery | Proper page titles/icons; config set once |
| ADR-9 | Models git-ignored, rebuilt by `train_all` | commit ~170 MB of pickles | Repo size; reproducibility; pickle safety |
| ADR-10 | Uncertainty range display-only | use as decision guard | Weak error signal; large test cost (see Models §8.1) |
| ADR-11 | Exact (Clopper–Pearson) CIs for proportions | bootstrap everywhere | Bootstrap collapses at 0%/100% |

## 11. Known technical debt
- Bundles are large (stages 2–3 ~80 MB each, mostly the 20 uncertainty copies of RF ensembles); deployment would need Git LFS / release assets or fewer replicas.
- `calibration.main` re-tunes models per fold (duplicating Phase 4 work) for simplicity; ~6 min.
- Headless browser screenshots of the app are unreliable; the app is verified functionally with `AppTest`.
- `predictor.CHOICES` duplicates category lists implied by the data; a mismatch would be caught by tests but not prevented by design.

## 12. Extending CardioStage
| Change | Where | Then |
|---|---|---|
| New feature/stage | `config.STAGES`, `NUMERIC/BINARY/CATEGORICAL_FEATURES`, app forms, `explain.LABELS` | `train_all`, evaluations, tests, docs |
| New model type | `models.make_classifier` + `PARAM_GRIDS` (+ `MODEL_NAMES`) | `train_all` |
| Different recall target | `config.SCREENING_RECALL` / `RULE_OUT_RECALL` | `train_all`, evaluations, app text, docs |
| New page | `app/views/*.py` + `st.Page` in `streamlit_app.py` | AppTest smoke test |

## Changelog
| Date | Change |
|---|---|
| 2026-11-23 | Document created at v1.0 |
