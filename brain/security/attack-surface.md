# CardioStage: Attack Surface

| | |
|---|---|
| **Assessment date** | 2026-11-23 (initial at commit `8b6571f`; updated after remediation) |
| **Runtime examined** | `streamlit run app/streamlit_app.py` on port 8501 (Streamlit 1.67.0, Starlette/Uvicorn server), Windows, Python 3.12.10 |
| **Companion docs** | [threat-model.md](threat-model.md) · [secrets.md](secrets.md) · [security-checklist.md](security-checklist.md) |

The only network-facing component is the **Streamlit server**, and it now listens **on localhost only**. Everything else (training, evaluation, reports) is offline CLI code, plus CI that runs on GitHub's infrastructure. Endpoint behaviour was confirmed by read-only probes against the local server.

---

## 1. Reachable endpoints
**Exposure change:** before remediation the server bound all interfaces (`0.0.0.0:8501`, `[::]:8501`), so every endpoint below was reachable from any device on the same network. Now `server.address = "localhost"`: `netstat` shows only `127.0.0.1:8501`, and a request to the machine's LAN address fails. The endpoints are therefore reachable **from this computer only**.

| Endpoint | Method | Purpose | Auth | Probe result / notes |
|---|---|---|---|---|
| `/` and `/results`, `/about` | GET | Streamlit frontend | None | Served on localhost |
| `/_stcore/stream` | WebSocket | All app interaction | None | Inputs validated in `predictor.to_frame`; per-session rate limit; plaintext but loopback-only |
| `/_stcore/health` | GET | Liveness | None | **200** |
| `/_stcore/host-config` | GET | Frontend configuration | None | Framework default |
| `/media/<id>` | GET | Images shown via `st.image` | None | Unknown id → **404** |
| `/_stcore/upload_file/<session>/<file>` | PUT/DELETE | Framework upload route (**no uploader in the app**) | XSRF token | Unauthenticated PUT → **403**, re-verified after remediation |
| `/_stcore/agent/openapi.json` | GET | Describes the experimental agent API | None | States the API is switched off |
| `/_stcore/agent/interact`, `/_stcore/agent/mcp` | POST/… | Experimental agent API | – | **Disabled** (default `enableAgentApi = false`); POST → **403** |
| Static serving (`/app/static/…`) | – | – | – | Disabled (default) |

**Deliberate sharing:** running with `--server.address 0.0.0.0` re-exposes all of the above to the network **without TLS or login**. Documented as an operator choice in `.streamlit/config.toml` and `docs/project/04-architecture.md`.

## 2. Internal endpoints
None. No internal API, service, queue or admin port.

## 3. Authentication and authorization surfaces
- **None implemented** (SEC-09, ⚪ accepted for local use). Anyone who can reach the server, now only local users, has full use of all pages.
- Developer toolbar (rerun, clear cache, settings): localhost viewers only (`client.toolbarMode = "auto"`).
- GitHub push access and CI are the only authorization boundaries in the lifecycle. CI runs with `permissions: contents: read`.

## 4. User inputs
All arrive as widget values over `/_stcore/stream` (`app/views/screener.py`). They're validated **twice**: by Streamlit widgets and by the engine (`predictor.to_frame`), so crafted messages can't bypass the UI's limits.

| Input | Widget constraint | Engine validation (`predictor.py`) |
|---|---|---|
| Example patient | 5 options | Acts only if value `in EXAMPLES` |
| Age | 18–100 (Streamlit clamps server-side) | finite, 18–100 (`PLAUSIBLE_RANGES`) |
| Sex | Female / Male | mapped to 0.0/1.0; checked ∈ {0, 1} (`ALLOWED_CODES`) |
| Chest pain type | 4 options | ∈ `CHOICES["cp"]` |
| Resting BP | 60–250 | finite, 60–250 |
| Cholesterol / not measured | 80–700 | finite, 80–700, or missing |
| Fasting blood sugar | 0/1/None | ∈ {0, 1} or missing |
| Resting ECG, ST slope, Thallium | fixed options | ∈ `CHOICES` or missing |
| Max heart rate | 60–230 | finite, 60–230 |
| Exercise chest pain | 0/1 | ∈ {0, 1} |
| ST depression | −3.0–7.0 | finite, −3.0–7.0 |
| Vessels (ca) | 0–3/None | ∈ {0, 1, 2, 3} or missing |

Invalid values → `InvalidInputError` → friendly message, no model call, no traceback (tests: 11 attack values + app error-handling tests). Values inside the plausible range but outside the training range are accepted and **flagged** by the novelty detector. Outputs reach Markdown only after validation and numeric formatting. No HTML rendering (`unsafe_allow_html` absent).

**Abuse limit:** each session may run at most **20 assessments per 60 seconds** (`config.RATE_LIMIT_*`); beyond that a "please wait" warning is shown.

## 5. File uploads
None in the application. The framework route rejects requests without a valid XSRF token (403).

## 6. Database access
None. CSV reads from fixed paths only, so there's no injection surface.

## 7. Storage
| Item | Location | Access | Protection |
|---|---|---|---|
| Model bundles (pickle) | `models/stage{1,2,3}.joblib` | `integrity.load` at app start and in analysis scripts | **SHA-256 verified** against `models/manifest.json` before unpickling (SEC-05, 🟡 residual: attacker able to rewrite both files) |
| OOF artefacts | `models/phase4_oof.joblib`, `phase5_oof.joblib` | Analysis scripts via `integrity.load` | In the manifest |
| Other artefacts | `models/phase3_*.joblib`, `phase7_shap.joblib` | Written only; **never loaded** by code | n/a |
| Integrity manifest | `models/manifest.json` | Written by `calibration.main` / `python -m cardiostage.integrity` | Not a secret |
| Reports/figures, training data | `reports/`, `data/raw/` (committed) | Read via fixed paths | Public |
| Session data | `st.session_state` (memory) | Per session | Not persisted |

## 8. Webhooks
None.

## 9. Third-party integrations
| Integration | When | Data sent | Status |
|---|---|---|---|
| `checkip.amazonaws.com` | ~~Every server start~~ | – | ✅ **No longer contacted**: the non-wildcard address skips Streamlit's lookup (startup log shows only the localhost URL) |
| Streamlit telemetry | – | – | Disabled |
| PyPI | `pip install` | Package downloads | Pinned + constrained; audited |
| PyPI/OSV advisory data | `pip-audit` (developer, CI) | Package names and versions | New (SEC-07 control) |
| GitHub | `git push`; CI runs; Dependabot | Source, commit metadata (SEC-08) | – |
| GitHub Actions (third-party code in CI) | Each CI run | Repo checkout (read-only token) | `actions/checkout@v4`, `actions/setup-python@v5`, `gitleaks/gitleaks-action@v2` (major-version tags) |
| Kaggle / UCI | One-time manual download | – | – |
| img.shields.io | Viewing the README on GitHub | Viewer's browser fetches badges | Not part of the app |

## 10. Admin surfaces
None in the app. Streamlit developer options are shown to localhost viewers only. The "Deploy" toolbar button links to Streamlit Community Cloud (no deployment config or credentials exist). Retraining needs shell access.

## 11. Network and deployment exposure
| Aspect | Before remediation | Now | Evidence |
|---|---|---|---|
| Bind address | All interfaces | **127.0.0.1 only** | `netstat`; LAN-address request → `URLError` |
| Startup URLs | Local + Network + External | **Local only** | Server log |
| Third-party call at start | Yes | **No** | Server log; `bootstrap.py` logic |
| TLS | None | None (not needed on loopback; required if shared) | `sslCertFile` unset |
| Error details to users | Full tracebacks | **None** | `showErrorDetails = "none"` |
| Reverse proxy / WAF | None | None (in-app per-session rate limit only) | – |
| CI | None | GitHub Actions, read-only permissions | `.github/workflows/ci.yml` |
| Firewall / router | Unverified | Largely moot (loopback socket) | – |

## 12. Dependencies and supply chain
- **Direct (pinned in `requirements.txt`):** pandas 3.1.1, numpy 2.5.5, scikit-learn 1.9.1, xgboost 3.4.1, shap 0.54.1, joblib 1.6.0, matplotlib 3.11.2, seaborn 0.13.2, plotly 7.1.0, streamlit 1.67.0, pytest 9.2.0, ruff 0.14.6, pip-audit 2.10.1.
- **All installed packages (76) pinned** in `constraints.txt`, used by CI via `-c constraints.txt`.
- **`pip-audit` (2026-11-23):** "No known vulnerabilities found" for `requirements.txt` and for the full environment (only the local `cardiostage` package is skipped, as it isn't on PyPI).
- **Continuous:** `pip-audit` on every push/PR; Dependabot weekly PRs for pip and GitHub Actions.
- **Residual (🟡):** no hash pinning; GitHub Actions referenced by major tag rather than commit SHA.
- **Deserialisation:** pickle via `integrity.load` only.

## 13. Surface summary
| Surface | Present? | Exposure now |
|---|---|---|
| HTTP/WebSocket app (no auth, no TLS) | ✅ | **Localhost only** |
| Framework upload route | Route only | XSRF-protected (403) |
| Experimental agent API | Route only | Disabled (403) |
| File uploads / DB / webhooks / admin / internal APIs | ❌ | – |
| Third-party calls from the app | ❌ | (startup lookup removed) |
| Deserialisation | Model pickles | Hash-verified before load |
| Supply chain | PyPI, GitHub Actions | Pinned, constrained, audited |
