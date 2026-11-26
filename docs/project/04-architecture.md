# CardioStage: Architecture Document

How the code is organised, how data flows from the raw CSV to an on-screen explanation, how it's secured, and why it's built this way.

| | |
|---|---|
| **Last updated** | 2026-11-26 (chatbot comparison) |
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
│   ├── charts.py               Plotly chart builders for the Results page (dark palette, colour tokens shared with ui.py)
│   ├── consent.py              consent screen shown before anything runs; local vs public wording (CARDIOSTAGE_DEPLOYMENT)
│   ├── ui.py                   shared UI: get_predictor (cached; handles missing/tampered models), render_assessment, contribution_chart, DISCLAIMER
│   ├── views/                  screener.py (rate limit + error handling) · results.py · about.py
│   └── static/fonts/           Fraunces + Inter woff2 (OFL), served at /app/static/ (fonts only)
├── brain/security/             threat model, secrets, attack surface, security checklist
├── data/
│   ├── raw/heart_disease_uci.csv   original data (committed, never edited)
│   ├── processed/              generated cleaned CSV (git-ignored)
│   └── README.md               source, licence, hospital counts
├── deploy/models.json          SHA-256 manifest of the released skops model archive + its 63 files (committed)
├── docs/
│   ├── learning/               14 beginner guides + index
│   ├── images/                 README screenshots (made by tools/screenshots.py)
│   └── project/                these 4 living documents + index
├── models/                     generated artefacts + manifest.json (git-ignored except .gitkeep)
├── reports/                    result CSV/JSON (committed) + figures/ (committed)
├── site/                       landing site: index.html · assets/{css,js,img,data} · vendor/ (pinned, sha512-verified libs) · fonts/ · licenses/ (+ NOTICES.html)
├── src/cardiostage/            the installable package (see §3)
├── tests/                      140 pytest tests (see §7)
├── tools/screenshots.py        dev tool: regenerates README screenshots via headless Chrome (DevTools protocol)
├── .gitattributes / .gitignore line endings (LF) / ignored paths
├── pyproject.toml              package metadata, pinned direct dependencies (+ dev group), pytest + ruff config
├── uv.lock                     every package (79) with exact version + SHA-256 checksums, all platforms
├── requirements.txt            generated from uv.lock (hashed) for plain-pip installs and hosting platforms
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
| `ratelimit.py` | Sliding-window limits: per browser session (pure function) and shared by all sessions (thread-safe) | `check_and_record(timestamps, now)`, `SharedLimiter.try_acquire(now)` | config |
| `model_store.py` | Safe model files for the public app: skops export, manifest (`deploy/models.json`), verified HTTPS download from a GitHub release, loading with an explicit trusted-types list | `export`, `write_manifest`, `download`, `available`, `load_bundles`, `TRUSTED_TYPES`; CLI | integrity, config |
| `stats.py` | Bootstrap CIs, exact proportion CIs, prior shift | `bootstrap_ci`, `exact_proportion_ci`, `prior_shift` | scipy, numpy |
| `explain.py` | SHAP permutation explainer on original features, text formatting | `StageExplainer`, `explanation_text`, `format_value` | shap |
| `predictor.py` | **App decision engine** (no UI code): integrity-checked loading, strict input validation, assessment in a fast core + optional add-ons | `CardioStagePredictor.load()`, `.assess(patient, stage, explain=, with_range=)` → `Assessment`; `.add_range()`, `.add_explanation()`; `InvalidInputError` | data, explain, integrity |
| `pooled.py` | v2 data: five hospitals in one table (Iran cholesterol not used), `split_v2` (Cleveland = v1's exact split; others 20%), stage hospital sets, leave-one-hospital-out comparison | `load_pooled`, `split_v2`, `stage_data`, `loho` | data, external_iran, staging |
| `v2_stage1.py` | Trains v2 stage 1: LOHO candidate comparison, calibration, zones, sanity checks, bundle (v1 backup `v1_stage1.joblib`) | `main`, `sanity_checks`, `MODEL_CHOICE` | pooled, calibration, staging, uncertainty, integrity |
| `v2_final.py` | v2 final exam, v1 vs v2 on the sealed test; `first_look` / `second_look` labels | `main(label)` | pooled, staging, stats |
| `llm_compare.py` | CardioStage vs free chatbots: paste-ready prompts (`data/llm_compare/prompts/`), strict reply parsing, scoring with paired bootstrap → `reports/llm_compare.csv`. No network access: chatbot replies are pasted by hand into `data/llm_compare/responses/` | `write_prompts`, `parse_reply`, `score` | pooled, stats, calibration |
| `external_iran.py` | External test on the Iranian Z-Alizadeh Sani cohort: column mapping (documented assumptions), stage-1 evaluation with `external_validation.evaluate` | `load_iran`, `to_cardiostage`, `main` | external_validation, predictor, stats |
| `external_validation.py` | Phase 6a analysis | `main` | stats, calibration, integrity |
| `fairness.py` | Phase 6b analysis | `main`, `age_band` | stats, staging, integrity |
| `explanations.py` | Phase 7 analysis | `main` | explain, integrity |
| `final_evaluation.py` | Phase 9 sealed test | `main` | stats, staging, integrity |
| `eda.py`, `train_baselines.py`, `from_scratch.py` | Phases 2–3 analyses | `main` | data, models |
| `train_all.py` | Rebuild deployable models: staging → calibration (writes manifest) | `main` | staging, calibration |
| `site_data.py` | Exports the landing site's numbers (`site/assets/data/site-data.{json,js}`); shared `patient_flow()` | `build`, `patient_flow`, `worked_example`; CLI | integrity, staging, predictor, stats |
| `chart_data.py` | Exports the extra data the Results page charts need (`reports/chart_data.json`): calibration curves, external calibration, case study (incl. out-of-fold risk), patient flow | `build`; CLI | calibration, explanations, site_data, stats |

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
**Python (`config.py`):** `RANDOM_SEED=42`, `TEST_SIZE=0.2`, `CV_FOLDS=5`, `CV_REPEATS=3`, `SCREENING_RECALL=0.97`, `RULE_OUT_RECALL=0.99`, `RULE_IN_PRECISION=0.90`, `CALIBRATION_METHODS`, `N_REPLICAS=20`, `REPLICA_FRACTION=0.8`, `UNCERTAINTY_PERCENTILES=(10, 90)`, `USE_UNCERTAINTY_GUARD=False`, `NOVELTY_QUANTILE=0.01`, `RATE_LIMIT_MAX_ASSESSMENTS=20`, `RATE_LIMIT_WINDOW_SECONDS=60`, `GLOBAL_RATE_LIMIT_MAX_ASSESSMENTS=40`, `GLOBAL_RATE_LIMIT_WINDOW_SECONDS=60`, stage feature lists, feature types, paths. Input validation limits (`CHOICES`, `ALLOWED_CODES`, `PLAUSIBLE_RANGES`) live in `predictor.py`.

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
| `test_predictor.py` | 14 | assessments, zones, missing/unusual input, invalid input, **full app flow via AppTest**, fast path + progressive add-ons, reproducible explanations, reset clears example, typical-angina caution rule + carried at every stage | yes (rule test: no) |
| `test_security.py` | 25 | config hardening, rate limiter, integrity (tamper/unlisted/missing manifest, refuse-before-unpickle, real bundles), input validation (11 attack values), app shows friendly errors without tracebacks | 3 need models |
| `test_site.py` | 12 | site CSP is strict, no inline scripts/styles, nothing loaded from other origins, vendored libs + licences present, `app/static` holds fonts only, site numbers match reports/split, patient flow adds up, JS data = JSON, v2 numbers match reports | no (site data is committed) |
| `test_charts.py` | 8 | chart data matches the reports (12 ECE values, flow, case study cleared by out-of-fold risk), all 9 Results charts build, no `-0.0` labels, Results page renders 9 Plotly charts and no PNGs (AppTest) | no (chart data is committed) |
| `test_public.py` | 7 | nothing runs before consent, `*.streamlit.app` counts as public (safety net), consent unlocks the app, local/public wording, error details forced to "none" despite a host override, shared limiter caps all sessions and is thread-safe | no |
| `test_model_store.py` | 9 | verified archive download extracted (archive not kept, nothing re-fetched), tampered archive / tampered member / oversized download rejected with no leftovers, plain HTTP and path-traversal names refused, mismatched local file refused before anything loads, trusted-types list unchanged, **skops models give identical results to the trained originals** (risk, range, zone, flags, explanation) | 1 (equivalence) |
| `test_external_iran.py` | 6 | published data fingerprint, shape/outcome, chest-pain/cholesterol/other mappings, every mapped patient passes the app's input validation | no |
| `test_llm_compare.py` | 9 | every patient in exactly one batch, fixed order, batches mix hospitals, prompts leak no hospital or outcome, committed prompts = code, strict parsing, scoring on fake replies | scoring only |
| `test_pooled.py` | 7 | five hospitals, 20% per hospital, stratified, reproducible, stage hospital sets, **Cleveland split = v1's exactly (no leakage)**, Iran cholesterol not used | no |
| **Total** | **140** | 123 run without models; 17 skip with a "trained models missing" reason | |

Run `uv run pytest` (~1 min). Lint: `uv run ruff check src tests app tools`; format: `uv run ruff format src tests app tools`; audit: `uv run pip-audit --skip-editable`.

## 8. Tooling, CI and supply chain
- **Environment:** `uv sync` builds `.venv/` exactly from `uv.lock` (the project is installed editable; dev tools from the `dev` group). Without uv: `pip install -r requirements.txt --require-hashes && pip install -e . --no-deps`.
- **Pinning:** `pyproject.toml` pins direct dependencies (`==`); `uv.lock` pins **every** package (79, incl. transitive and platform-specific ones such as Linux-only `nvidia-nccl-cu13`) with SHA-256 checksums for every platform; `requirements.txt` is exported from the lock (`uv export --no-dev --no-emit-project`), with `--hash` lines. The lock was created against the previously tested versions, so no library changed (all 76 earlier versions identical).
- **CI** (`.github/workflows/ci.yml`, on push/PR to `main`, `permissions: contents: read`):
  - *quality* job (Ubuntu, Python 3.12 via `astral-sh/setup-uv`): `uv sync --locked` (fails if the lock is stale) → `requirements.txt` must equal a fresh export → `ruff check` → `pytest -q -rs` (model tests skip) → `pip-audit --skip-editable`.
  - *secrets* job: `gitleaks/gitleaks-action` over the full history (`fetch-depth: 0`).
  - **Every action is pinned to a full commit SHA** with its version in a comment (e.g. `actions/checkout@3d3c42e… # v7.0.1`), in both `ci.yml` and `pages.yml`.
- **Pages** (`.github/workflows/pages.yml`, on push to `main` touching `site/**`, or manual): `configure-pages` → `upload-pages-artifact` (path `site`) → `deploy-pages`; permissions `contents: read, pages: write, id-token: write`; one deployment at a time. Requires Settings → Pages → Source: *GitHub Actions*.
- **Vendored front-end libraries** (`site/vendor/`): copied from release tarballs whose npm `sha512` integrity was verified; GSAP from the official `gsap` repo's `dist/`. Not covered by Dependabot: update manually (re-download, verify, re-test in a browser). Licences in `site/licenses/`.
- **Dependabot** (`.github/dependabot.yml`): weekly update PRs for pip and GitHub Actions.
- **Last audit** (2026-11-23): `pip-audit` found **no known vulnerabilities** in `requirements.txt` or the full environment.
- **Line endings** normalised to LF via `.gitattributes`. **Ignored:** `.venv/`, caches, `data/processed/*`, `models/*`, `.streamlit/secrets.toml`.
- **Git workflow:** commits on `main`, pushed to `github.com/harshfiu/CardioStage`.

## 8A. Public deployment (Streamlit Community Cloud)
**URL:** https://cardiostage.streamlit.app (free tier; US-hosted; sleeps after 12 h idle, any visitor can wake it).

```
GitHub repo (main) ──► Community Cloud build: uv sync from uv.lock ──► streamlit run app/streamlit_app.py
                                                                         │ secret CARDIOSTAGE_DEPLOYMENT=public
visitor ──HTTPS──► consent screen ──► screener ──► predictor.load_bundles (public → skops only)
                                                      │ first start: model_store.download()
GitHub release models-v1 ──HTTPS──► cardiostage-models.zip ──verify SHA-256 (archive + 63 files)──► skops.load(trusted=TRUSTED_TYPES)
```

| Concern | Implementation |
|---|---|
| Configuration | Community Cloud secret `CARDIOSTAGE_DEPLOYMENT = "public"` (exposed as an environment variable); a `*.streamlit.app` Host header also counts as public, so the privacy wording is right even if the secret is missing |
| Dependencies | Community Cloud picks `uv.lock` first (exact, checksummed); Python 3.12 |
| Models | `models-v1` GitHub pre-release asset `cardiostage-models.zip` (267 MB): 3 main skops files + 60 range files (one per range copy, because skops is extremely slow on one huge file); manifest `deploy/models.json` |
| Startup | First load: download (~30 s) + skops load (~60 s locally, about a minute measured live); cached for every visitor afterwards |
| Memory | ~0.7–0.8 GB with all models (host cap 2.7 GB) |
| Host overrides | `showErrorDetails` reset to `"none"` in code; XSRF off and usage statistics forced by the host (disclosed; see `brain/security/` SEC-13/14) |
| Updating models | retrain → `python -m cardiostage.model_store export <release URL>` → upload the new archive to a new release tag → commit `deploy/models.json` |

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
| ADR-16 | ~~Constraints file instead of hash lockfile~~ (superseded by ADR-24) | `pip-compile --generate-hashes` | Was: cross-platform pinning without per-platform hash maintenance |
| ADR-27 | v2: pool stage 1 only; stages 2–3 stay Cleveland | pool all stages; keep v1 | LOHO: pooling helps modern patients (Iran) at a small cost elsewhere; no clear gain for stage 2; stage 3 data exists only at Cleveland |
| ADR-28 | Treat Iran's estimated cholesterol as not measured | keep the estimate; adjust by hospital | The estimate confounds era and medication with risk (learned a backwards effect); training-data evidence only |
| ADR-29 | Logistic regression over the LOHO-preferred random forest, with automatic sanity checks | follow the rule strictly | Gap within noise; the forest learned a missing-value shortcut and a non-monotonic cholesterol curve |
| ADR-30 | Report the first and second look at the sealed test separately | silently replace the first result | The first look prompted changes; transparency about test reuse |
| ADR-31 | Compare with chatbots by hand-pasted, pre-registered prompts, not an API integration | API calls (cost, keys, a network dependency in the repo) | Free; measures what people actually use; no secrets or outbound calls in the codebase; the sealed test stays unseen by CardioStage |
| ADR-25 | Host the public app on Streamlit Community Cloud (free) | Hugging Face Spaces (needs PRO since Streamlit runs as a paid Docker Space); in-browser rewrite | Free, made for Streamlit, deploys from the repo and `uv.lock`; trade-offs (forced telemetry, settings overrides, no custom headers) accepted and disclosed by the owner |
| ADR-26 | skops models split per range copy, shipped as one SHA-pinned release archive | one skops file per stage; pickles + manifest; Git LFS | One-file conversion was pathologically slow (40+ min, unfinished); split files take ~6 s each; one archive keeps the release to a single upload; release assets avoid LFS bandwidth limits and keep Git history small |
| ADR-24 | `uv` lockfile with checksums; actions pinned to commit SHAs | pip-tools per-platform hashed files; keep constraints | One cross-platform lock with hashes for every wheel; `--locked` installs fail on drift; a hashed `requirements.txt` export keeps plain-pip installs (and hosting platforms) working; SHAs can't be re-pointed like tags |
| ADR-19 | Separate static landing site + restyled Streamlit app | animate inside Streamlit via components/iframes; rewrite the app in a JS framework | Streamlit can't host Lenis/GSAP/Vanta on its own pages; a static site gives full design control and free hosting, while the validated app stays unchanged |
| ADR-20 | Vendor all site libraries and fonts | CDNs, Google Fonts | No third-party requests (privacy), works offline, strict `script-src 'self'` CSP; versions pinned and integrity-checked |
| ADR-21 | Site numbers generated from reports (`site_data.py`) | hand-typed copy | Site can't drift from results; tests compare it to the reports |
| ADR-23 | Results page charts redrawn in Plotly from committed data (`charts.py` + `chart_data.json`) | dark re-render of the PNGs by re-running analyses with a theme flag | Analyses are slow and mix computation with plotting; a small export reuses the same functions (values tested equal to reports), charts become interactive and theme-matched, PNGs stay for README/docs |
| ADR-22 | Site data also emitted as `site-data.js` | `fetch()` the JSON only | Browsers block `fetch` from `file://`; a `<script src>` works locally and under the CSP |

## 11. Known technical debt
- Bundles are large (stages 2–3 ~80 MB each, mostly the 20 uncertainty copies of RF ensembles); deployment would need Git LFS / release assets or fewer replicas (and a safer format than pickle, e.g. skops).
- The integrity manifest lives beside the bundles in `models/`; it detects swapped/corrupted files but not an attacker who can rewrite both.
- The rate limit is per browser session; many parallel sessions would need a reverse proxy.
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
| Dependency upgrade | Change the pin in `pyproject.toml` (or merge a Dependabot PR), `uv lock`, then `uv export --locked --no-dev --no-emit-project --format requirements-txt -o requirements.txt` | `uv run pytest`, `uv run pip-audit --skip-editable` |

## Changelog
| Date | Change |
|---|---|
| 2026-11-26 | Chatbot comparison: `llm_compare.py`, `data/llm_compare/` (prompts, replies, log), `reports/llm_compare.csv`, `charts.chatbots`, Results 'vs chatbots' tab, site section, `site_data.chatbots`; ADR-31; 150 tests |
| 2026-11-24 | Version 2.0: `pooled.py`, `v2_stage1.py`, `v2_final.py`; models/stage1.joblib = v2 (v1 kept as `v1_stage1.joblib`); manifest covers both; Results 'Version 2' tab; site Version 2 section; ADR-27–30; 140 tests |
| 2026-11-24 | External test on Iran (`external_iran.py`, `data/raw/external/`), known-weakness cautions in the engine (`known_cautions`), external CSVs kept byte-exact via `.gitattributes`; 132 tests |
| 2026-11-24 | Public deployment: Streamlit Community Cloud (§8A), consent screen, `model_store` (skops, release archive, SHA-pinned manifest), shared rate limit, error-detail override, Host-based public detection; ADR-25/26 |
| 2026-11-23 | Supply chain (SEC-07 ✅): `uv.lock` with checksums replaces `constraints.txt`; dependencies moved to `pyproject.toml`; hashed `requirements.txt` export; CI on `uv sync --locked`; all actions pinned to commit SHAs; Dependabot on uv; `requires-python >=3.12`; ADR-24 |
| 2026-11-23 | Results page: native Plotly charts (`app/charts.py`, `chart_data.py` → `reports/chart_data.json`), README screenshots + `tools/screenshots.py`, learning guides 10–11; 106 tests; ADR-23 |
| 2026-11-23 | Premium redesign: landing site `site/` (vendored GSAP/Lenis/Vanta, strict CSP), `site_data.py` export, Pages workflow, dark app theme with self-hosted fonts (`enableStaticServing` for fonts only), 98 tests; ADR-19–22 |
| 2026-11-23 | UI polish: progressive rendering (`assess` fast core + `add_range`/`add_explanation`), sliders, reproducible SHAP, reset fix; latencies corrected; 87 tests; ADR-17/18 |
| 2026-11-23 | Merged Dependabot updates: ruff 0.17.6, actions/checkout v7, actions/setup-python v7, gitleaks-action v3 (lint, 84 tests and pip-audit re-verified locally) |
| 2026-11-23 | Security hardening: localhost binding, hidden error details, input validation, rate limiting, integrity manifest, constraints file, CI (ruff/pytest/pip-audit/gitleaks), Dependabot; 84 tests; ADR-12–16; corrected the network-call statement in §1 |
| 2026-11-23 | Document created at v1.0 |
