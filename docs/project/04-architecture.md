# CardioStage: Architecture Document

How the code is organised, how data flows from the raw CSV to an on-screen explanation, how it's secured, and why it's built this way.

| | |
|---|---|
| **Last updated** | 2026-11-23 (premium redesign: landing site + app restyle) |
| **Stack** | Landing site: static HTML/CSS/JS with vendored GSAP 3 (ScrollTrigger, DrawSVG, SplitText), Lenis 1.3.27, three.js r134 + Vanta 0.5.24 NET, self-hosted Fraunces/Inter · App: Python 3.12 · pandas 3.1 · scikit-learn 1.9 · XGBoost 3.4 · SHAP 0.54 · Streamlit 1.67 (Starlette/Uvicorn server) · Plotly 7.1 · matplotlib/seaborn · pytest 9.2 · ruff 0.17 · pip-audit 2.10 |
| **Related docs** | [PRD](01-product-requirements.md) · [Models](02-models.md) · [Design system](03-design-system.md) · Security: [`brain/security/`](../../brain/security/threat-model.md) |

---

## 1. System overview

```
             ┌────────────────────────── OFFLINE: training & evaluation ──────────────────────────┐
 data/raw/   │  data.py ─► preprocessing.py ─► models.py ─► staging.py ─► calibration.py           │
 heart_      │  (clean,     (per-stage        (pipelines,   (nested CV,    (calibration,          │
 disease_    │   split)      transformer)      grids)        zones,         uncertainty copies,    │
 uci.csv ───►│                                               policy)        novelty, manifest)     │
             │                                                   │               │                 │
             │   external_validation.py · fairness.py · explanations.py · final_evaluation.py     │
             └───────────────────────────────────┬────────────────┼─────────────────────────────────┘
                                                 ▼                ▼
                                      reports/ (CSV, JSON,   models/stage{1,2,3}.joblib + manifest.json
                                      figures/*.png)         (git-ignored, ~170 MB; SHA-256 fingerprints)
                                                                  │ integrity.load (verify → unpickle)
             ┌──────────────────── ONLINE: the app (127.0.0.1:8501 only) ─────────────────────────┐
             │  app/streamlit_app.py (navigation)                 ▼                                 │
             │     ├─ views/screener.py ─ rate limit ─► predictor.py (validate → assess) ► explain │
             │     ├─ views/results.py  ──► reports/*.csv, figures                                  │
             │     └─ views/about.py         ui.py: cached loading, result card, chart, disclaimer │
             └─────────────────────────────────────────────────────────────────────────────────────┘

 reports/ + models/ ──► site_data.py ──► site/assets/data/site-data.{json,js}
                                                   │
             ┌──────────── PUBLIC: landing site (static, GitHub Pages) ────────────┐
             │  site/index.html + assets/{css,js} + vendor/ (GSAP, Lenis, Vanta)    │
             │  no backend, no patient input, no third-party requests (strict CSP)  │
             └──────────────────────────────────────────────────────────────────────┘
```

Everything runs **locally**. There's no server-side database and no external API. The app server listens on **localhost only** (`.streamlit/config.toml` `server.address = "localhost"`), so it isn't reachable from other devices. Because of that specific address, Streamlit also **skips its startup public-IP lookup** (`checkip.amazonaws.com`), which it performs only when bound to all interfaces in headless mode. No network calls are made during inference.

The **landing site** (`site/`) is a separate, purely static page that explains the project; it's published to GitHub Pages by `.github/workflows/pages.yml`. It never runs the model and takes no input: its numbers are exported from the real reports by `python -m cardiostage.site_data`. Lenis/GSAP/Vanta live only on the site, because Streamlit pages can't host custom scripts outside iframes.

## 2. Repository layout
```
CardioStage/
├── .github/
│   ├── workflows/ci.yml        CI: ruff, pytest, pip-audit; gitleaks secret scan (read-only permissions)
│   ├── workflows/pages.yml     deploys site/ to GitHub Pages (pages: write, id-token: write)
│   └── dependabot.yml          weekly dependency / GitHub Actions update PRs
├── .streamlit/config.toml      dark theme + self-hosted fonts + security settings (localhost bind, hidden error details, XSRF/CORS on, static serving for fonts)
├── app/
│   ├── streamlit_app.py        entry point: set_page_config + st.navigation
│   ├── ui.py                   shared UI: get_predictor (cached; handles missing/tampered models), render_assessment, contribution_chart, DISCLAIMER
│   ├── views/                  screener.py (rate limit + error handling) · results.py · about.py
│   └── static/fonts/           Fraunces + Inter woff2 (OFL), served at /app/static/ (fonts only)
├── brain/security/             threat model, secrets, attack surface, security checklist
├── data/
│   ├── raw/heart_disease_uci.csv   original data (committed, never edited)
│   ├── processed/              generated cleaned CSV (git-ignored)
│   └── README.md               source, licence, hospital counts
├── docs/
│   ├── learning/               9 beginner guides + index
│   └── project/                these 4 living documents + index
├── models/                     generated artefacts + manifest.json (git-ignored except .gitkeep)
├── reports/                    result CSV/JSON (committed) + figures/ (committed)
├── site/                       landing site: index.html · assets/{css,js,img,data} · vendor/ (pinned, sha512-verified libs) · fonts/ · licenses/ (+ NOTICES.html)
├── src/cardiostage/            the installable package (see §3)
├── tests/                      98 pytest tests (see §7)
├── .gitattributes / .gitignore line endings (LF) / ignored paths
├── constraints.txt             exact versions of all 76 installed packages (transitive pinning)
├── pyproject.toml              package metadata, pytest + ruff config
├── requirements.txt            pinned direct dependencies
├── LICENSE                     MIT (code); CC BY 4.0 note (data)
└── README.md
```

## 3. Package modules (`src/cardiostage/`)
| Module | Responsibility | Key API | Depends on |
|---|---|---|---|
| `config.py` | **Single source of truth**: paths, seed, target, hospitals, stage feature lists, feature types, CV settings, decision targets, uncertainty settings, rate limits | constants | – |
| `data.py` | Load raw CSV, cleaning rules, sealed split, stage feature selection | `load_raw`, `clean_data`, `load_clean`, `split_cleveland`, `get_features_and_target` | config |
| `preprocessing.py` | Per-stage `ColumnTransformer` (impute/scale/one-hot), pandas output | `build_preprocessor(stage)` | config |
| `models.py` | Candidate classifiers, tuning grids, pipelines | `MODEL_NAMES`, `PARAM_GRIDS`, `build_pipeline(name, stage)` | preprocessing |
| `thresholds.py` | Pure decision functions | `threshold_for_recall`, `threshold_for_precision`, `decision_metrics` | numpy |
| `staging.py` | Phase 4: per-stage nested CV + ensemble, OOF predictions, zones, policy simulation, bootstrap, final-model fitting | `collect_out_of_fold`, `compute_zones`, `simulate_policy`, `fit_final_model` | data, models, thresholds |
| `uncertainty.py` | Subsample ensemble ranges; novelty detection | `SubsampleEnsemble`, `NoveltyDetector`, `straddles` | preprocessing |
| `calibration.py` | Phase 5: calibration comparison, uncertainty evaluation, final bundles + integrity manifest (`--report-only` mode) | `make_variant`, `expected_calibration_error`, `main` | staging, uncertainty, integrity |
| `integrity.py` | **SHA-256 manifest** for every pickle the code loads; verify-before-unpickle | `write_manifest`, `verify`, `load`, `IntegrityError`; CLI `python -m cardiostage.integrity` | config |
| `ratelimit.py` | Pure sliding-window limiter (per browser session) | `check_and_record(timestamps, now)` | config |
| `stats.py` | Bootstrap CIs, exact proportion CIs, prior shift | `bootstrap_ci`, `exact_proportion_ci`, `prior_shift` | scipy, numpy |
| `explain.py` | SHAP permutation explainer on original features, text formatting | `StageExplainer`, `explanation_text`, `format_value` | shap |
| `predictor.py` | **App decision engine** (no UI code): integrity-checked loading, strict input validation, assessment in a fast core + optional add-ons | `CardioStagePredictor.load()`, `.assess(patient, stage, explain=, with_range=)` → `Assessment`; `.add_range()`, `.add_explanation()`; `InvalidInputError` | data, explain, integrity |
| `external_validation.py` | Phase 6a analysis | `main` | stats, calibration, integrity |
| `fairness.py` | Phase 6b analysis | `main`, `age_band` | stats, staging, integrity |
| `explanations.py` | Phase 7 analysis | `main` | explain, integrity |
| `final_evaluation.py` | Phase 9 sealed test | `main` | stats, staging, integrity |
| `eda.py`, `train_baselines.py`, `from_scratch.py` | Phases 2–3 analyses | `main` | data, models |
| `train_all.py` | Rebuild deployable models: staging → calibration (writes manifest) | `main` | staging, calibration |

**Dependency rules:** analysis scripts depend on core modules, never the reverse. `predictor.py` depends only on core modules and saved bundles. The app depends only on `predictor`, `ratelimit`, `integrity` (error type), `config` and `reports/`. **No module calls `joblib.load` directly**: every pickle goes through `integrity.load`.

## 4. Data flow
### 4.1 Training pipeline (`python -m cardiostage.train_all`, ~10 min)
1. `load_clean()` → 918 rows; `split_cleveland()` → 243 train / 61 sealed test (seed 42).
2. **staging.main** – per stage: 15 outer folds × (grid search LR/RF/XGB + ensemble) → OOF probabilities, AUC table, chosen candidate → `reports/phase4_*.csv`, `phase4_zones.json`, figures 07–09, `models/phase4_oof.joblib`.
3. **calibration.main** – reads `phase4_zones.json` → per stage: re-tune per fold, fit uncalibrated/sigmoid/isotonic → pooled Brier picks method → zones from calibrated OOF → uncertainty ranges → reports + figures 10–11 → **final bundles** `models/stage{1,2,3}.joblib` = {model, uncertainty, novelty, model_name, calibration, features, zones} → **`models/manifest.json`** with the SHA-256 of `stage{1,2,3}.joblib`, `phase4_oof.joblib` and `phase5_oof.joblib`.

### 4.2 Evaluation scripts (read bundles / OOF via `integrity.load`, write reports)
`external_validation` → figures 12–13 · `fairness` → 14 · `explanations` → 15–17 · `final_evaluation` → 18 (sealed test).

### 4.3 Runtime: app start and one assessment
```
app start ─► ui.get_predictor()  (@st.cache_resource, once per server process)
   └► CardioStagePredictor.load()
        • missing bundle  → ModelsNotFoundError → friendly st.error + stop
        • integrity.load(stage{s}.joblib): SHA-256 vs manifest.json
              mismatch / unlisted / no manifest → IntegrityError → friendly st.error + stop (never unpickled)

user submits form ─► screener.run_stage(stage)
   1. ratelimit.check_and_record(session timestamps, now)  ── over 20/60 s → st.warning, stop
   2. predictor.assess(patient_dict, stage, explain=False, with_range=False)   (try/except; ~0.1 s)
        a. to_frame(): categories ∈ CHOICES · codes ∈ ALLOWED_CODES (sex/fbs/exang/ca)
           · numbers finite and within PLAUSIBLE_RANGES · missing → NaN   ── else InvalidInputError
        b. bundle.model.predict_proba → risk
        c. zone(stage, risk) using frozen bundle.zones → headline + recommendation
        d. bundle.novelty.check → unusual reasons;  not_measured list
      (range and explanation are NOT computed here)
   3. InvalidInputError → st.error("inputs aren't valid…")
      any other exception → logged to server console; generic st.error (no traceback to user)
   └► Assessment stored in st.session_state.results[stage]
render_assessment(result, predictor) ─► progressive:
   risk metric + decision box  (drawn immediately)
   → spinner → predictor.add_range(result)        (~2 s; stored on the Assessment)
   → threshold caption, unusual/not-measured notes
   → spinner → predictor.add_explanation(result)  (~3 s; SHAP re-seeded per call → reproducible)
   → summary text, Plotly chart, breakdown table
   (each add-on wrapped: failure → friendly st.error; never a traceback)
```

## 5. State, caching and performance
| Concern | Mechanism | Numbers |
|---|---|---|
| Model loading | `@st.cache_resource` on `get_predictor()`, once per server process; includes SHA-256 verification | ~14–15 s (hashing adds <1 s for ~170 MB) |
| Explainers | Lazily built per stage, cached in the predictor | built on first explanation |
| Session state | `st.session_state`: input widget keys, `results` {stage: Assessment}, `example`, `assessment_times` (rate limiter) | per browser session |
| Forms | `st.form` so predictions run only on submit | – |
| Rate limit | `RATE_LIMIT_MAX_ASSESSMENTS = 20` per `RATE_LIMIT_WINDOW_SECONDS = 60` per session | a full screening uses 3 |
| Assessment latency | core (validation + risk + zone + novelty) / + range / + SHAP | core ~0.1 s; range ~2.2 s and SHAP ~2.5–3 s at stages 2–3 (≈5.5 s total), rendered **progressively** so the decision shows at once |
| Training | parallel grid search (`n_jobs=-1`), parallel replicas/SHAP chunks (joblib) | full rebuild ~10 min on 20 cores |

## 6. Configuration
**Python (`config.py`):** `RANDOM_SEED=42`, `TEST_SIZE=0.2`, `CV_FOLDS=5`, `CV_REPEATS=3`, `SCREENING_RECALL=0.97`, `RULE_OUT_RECALL=0.99`, `RULE_IN_PRECISION=0.90`, `CALIBRATION_METHODS`, `N_REPLICAS=20`, `REPLICA_FRACTION=0.8`, `UNCERTAINTY_PERCENTILES=(10, 90)`, `USE_UNCERTAINTY_GUARD=False`, `NOVELTY_QUANTILE=0.01`, `RATE_LIMIT_MAX_ASSESSMENTS=20`, `RATE_LIMIT_WINDOW_SECONDS=60`, stage feature lists, feature types, paths. Input validation limits (`CHOICES`, `ALLOWED_CODES`, `PLAUSIBLE_RANGES`) live in `predictor.py`.

**Streamlit (`.streamlit/config.toml`):**
| Setting | Value | Purpose |
|---|---|---|
| `server.address` | `"localhost"` | Local-only listening; skips external-IP lookup (SEC-01, SEC-04) |
| `server.headless` | `true` | Don't auto-open a browser |
| `server.enableXsrfProtection` | `true` (explicit) | Cross-site request forgery protection |
| `server.enableCORS` | `true` (explicit) | Cross-origin protection |
| `server.enableStaticServing` | `true` | Serves `app/static/` (font files only, enforced by a test) so the app needs no Google Fonts |
| `[theme]` | dark, peach primary, Fraunces/Inter `fontFaces` | See Design system §2.5 |
| `client.showErrorDetails` | `"none"` | No tracebacks shown to users (SEC-03) |
| `browser.gatherUsageStats` | `false` | No telemetry |
| `server.enableAgentApi` | not set (default `false`) | Experimental agent API stays off |

To share deliberately on a trusted network: `streamlit run app/streamlit_app.py --server.address 0.0.0.0` (no TLS or login; see `brain/security/`).

Changing model-related values requires re-running `train_all` (and evaluations) and **updating these docs**.

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
| `test_predictor.py` | 10 | assessments, zones, missing/unusual input, invalid input, **full app flow via AppTest**, fast path + progressive add-ons, reproducible explanations, reset clears example | yes |
| `test_security.py` | 25 | config hardening, rate limiter, integrity (tamper/unlisted/missing manifest, refuse-before-unpickle, real bundles), input validation (11 attack values), app shows friendly errors without tracebacks | 3 need models |
| `test_site.py` | 11 | site CSP is strict, no inline scripts/styles, nothing loaded from other origins, vendored libs + licences present, `app/static` holds fonts only, site numbers match reports/split, patient flow adds up, JS data = JSON | no (site data is committed) |
| **Total** | **98** | 85 run without models; 13 skip with a "trained models missing" reason | |

Run `pytest` (~1 min). Lint: `ruff check src tests app`; format: `ruff format src tests app`; audit: `pip-audit -r requirements.txt`.

## 8. Tooling, CI and supply chain
- **Virtual environment** `.venv/`; `pip install -r requirements.txt -c constraints.txt && pip install -e .`.
- **Pinning:** `requirements.txt` pins direct dependencies; `constraints.txt` pins **all** installed packages (incl. transitive) to tested versions. Constraints only fix versions, so platform-specific packages aren't forced onto other OSes. No hash pinning (see §11).
- **CI** (`.github/workflows/ci.yml`, on push/PR to `main`, `permissions: contents: read`):
  - *quality* job (Ubuntu, Python 3.12): install with constraints → `ruff check` → `pytest -q -rs` (model tests skip) → `pip-audit -r requirements.txt`.
  - *secrets* job: `gitleaks/gitleaks-action@v3` (with `actions/checkout@v7`, `actions/setup-python@v7`) over the full history (`fetch-depth: 0`).
- **Pages** (`.github/workflows/pages.yml`, on push to `main` touching `site/**`, or manual): `configure-pages` → `upload-pages-artifact` (path `site`) → `deploy-pages`; permissions `contents: read, pages: write, id-token: write`; one deployment at a time. Requires Settings → Pages → Source: *GitHub Actions*.
- **Vendored front-end libraries** (`site/vendor/`): copied from release tarballs whose npm `sha512` integrity was verified; GSAP from the official `gsap` repo's `dist/`. Not covered by Dependabot: update manually (re-download, verify, re-test in a browser). Licences in `site/licenses/`.
- **Dependabot** (`.github/dependabot.yml`): weekly update PRs for pip and GitHub Actions.
- **Last audit** (2026-11-23): `pip-audit` found **no known vulnerabilities** in `requirements.txt` or the full environment.
- **Line endings** normalised to LF via `.gitattributes`. **Ignored:** `.venv/`, caches, `data/processed/*`, `models/*`, `.streamlit/secrets.toml`.
- **Git workflow:** commits on `main`, pushed to `github.com/harshfiu/CardioStage`.

## 9. Security and privacy
Full assessment: [`brain/security/`](../../brain/security/threat-model.md). Controls in place:
| Area | Control |
|---|---|
| Network exposure | Listens on `127.0.0.1` only (verified: not reachable via the LAN address); no startup third-party IP lookup |
| Request forgery / origins | XSRF and CORS protection explicitly enabled (unauthenticated upload PUT → 403) |
| Framework surfaces | Agent API off (default; 403); static serving **on for `app/static/` fonts only** (test-enforced); developer toolbar only for localhost |
| Landing site | Static only; strict CSP meta (`default-src 'self'`, no `unsafe-inline`/`unsafe-eval`, `object-src 'none'`, `base-uri 'none'`); DOM built with element APIs (no `innerHTML`); all scripts/fonts self-hosted (no third-party requests); no forms, cookies or analytics |
| Input validation | Categories, coded values, finite numbers and plausible ranges enforced in `predictor.to_frame`; measurements entered with sliders bounded to the same ranges |
| Error handling | `showErrorDetails = "none"`; assessments wrapped in try/except with friendly messages; details only in the server console |
| Abuse | Per-session rate limit (20 assessments / 60 s) |
| Deserialisation | SHA-256 manifest verified before any pickle is loaded (`integrity.load`) |
| Secrets | None used or stored; `.streamlit/secrets.toml` ignored; gitleaks in CI |
| Supply chain | Pinned direct + constrained transitive deps; pip-audit in CI; Dependabot |
| Privacy | No persistence or logging of patient inputs; inputs held only in session memory; telemetry off |
| Not implemented (by design for local use) | Authentication, TLS, multi-session rate limiting, access logging: required before any shared deployment |

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
| ADR-12 | Bind to localhost by default | all interfaces; TLS + auth proxy | Local educational use needs no network exposure; explicit flag to share |
| ADR-13 | SHA-256 manifest before unpickling | trust files; switch to skops | Cheap tamper/corruption detection with joblib; skops reserved for distribution |
| ADR-14 | Validation duplicated in engine (not only UI) | trust widget constraints | Defence in depth: crafted websocket values can bypass UI options |
| ADR-15 | Per-session in-app rate limit | proxy limits only | No proxy exists for local use; pure function is testable |
| ADR-17 | Progressive result rendering instead of speeding up inference | threads, all-core forests, fewer replicas | Measured: per-call overhead dominates, parallelism was slower; changing replicas/background would alter validated outputs |
| ADR-18 | Sliders for measurements | number inputs | Streamlit's number input calls `preventDefault()` on wheel events (`NumberInput.js`), blocking page scroll; sliders don't, and show the valid range |
| ADR-16 | Constraints file instead of hash lockfile | `pip-compile --generate-hashes` | Cross-platform safe pinning of transitive deps without per-platform hash maintenance |
| ADR-19 | Separate static landing site + restyled Streamlit app | animate inside Streamlit via components/iframes; rewrite the app in a JS framework | Streamlit can't host Lenis/GSAP/Vanta on its own pages; a static site gives full design control and free hosting, while the validated app stays unchanged |
| ADR-20 | Vendor all site libraries and fonts | CDNs, Google Fonts | No third-party requests (privacy), works offline, strict `script-src 'self'` CSP; versions pinned and integrity-checked |
| ADR-21 | Site numbers generated from reports (`site_data.py`) | hand-typed copy | Site can't drift from results; tests compare it to the reports |
| ADR-22 | Site data also emitted as `site-data.js` | `fetch()` the JSON only | Browsers block `fetch` from `file://`; a `<script src>` works locally and under the CSP |

## 11. Known technical debt
- Bundles are large (stages 2–3 ~80 MB each, mostly the 20 uncertainty copies of RF ensembles); deployment would need Git LFS / release assets or fewer replicas (and a safer format than pickle, e.g. skops).
- The integrity manifest lives beside the bundles in `models/`; it detects swapped/corrupted files but not an attacker who can rewrite both.
- The rate limit is per browser session; many parallel sessions would need a reverse proxy.
- No hash pinning of dependencies (constraints pin versions only).
- `calibration.main` re-tunes models per fold (duplicating Phase 4 work) for simplicity; ~6 min.
- Headless browser screenshots of the app are unreliable; the app is verified functionally with `AppTest`.
- `predictor.CHOICES` duplicates category lists implied by the data; a mismatch would be caught by tests but not prevented by design.

## 12. Extending CardioStage
| Change | Where | Then |
|---|---|---|
| New feature/stage | `config.STAGES`, `NUMERIC/BINARY/CATEGORICAL_FEATURES`, app forms, `explain.LABELS`, `predictor.CHOICES/ALLOWED_CODES/PLAUSIBLE_RANGES` | `train_all`, evaluations, tests, docs |
| New model type | `models.make_classifier` + `PARAM_GRIDS` (+ `MODEL_NAMES`) | `train_all` |
| Different recall target | `config.SCREENING_RECALL` / `RULE_OUT_RECALL` | `train_all`, evaluations, app text, docs |
| New page | `app/views/*.py` + `st.Page` in `streamlit_app.py` | AppTest smoke test |
| New pickle loaded by code | add to `integrity.stage_bundle_paths()`; load via `integrity.load` | `python -m cardiostage.integrity` or `train_all` |
| Dependency upgrade | `requirements.txt`, then `pip freeze --exclude-editable > constraints.txt` (keep header) | `pytest`, `pip-audit` |

## Changelog
| Date | Change |
|---|---|
| 2026-11-23 | Premium redesign: landing site `site/` (vendored GSAP/Lenis/Vanta, strict CSP), `site_data.py` export, Pages workflow, dark app theme with self-hosted fonts (`enableStaticServing` for fonts only), 98 tests; ADR-19–22 |
| 2026-11-23 | UI polish: progressive rendering (`assess` fast core + `add_range`/`add_explanation`), sliders, reproducible SHAP, reset fix; latencies corrected; 87 tests; ADR-17/18 |
| 2026-11-23 | Merged Dependabot updates: ruff 0.17.6, actions/checkout v7, actions/setup-python v7, gitleaks-action v3 (lint, 84 tests and pip-audit re-verified locally) |
| 2026-11-23 | Security hardening: localhost binding, hidden error details, input validation, rate limiting, integrity manifest, constraints file, CI (ruff/pytest/pip-audit/gitleaks), Dependabot; 84 tests; ADR-12–16; corrected the network-call statement in §1 |
| 2026-11-23 | Document created at v1.0 |
