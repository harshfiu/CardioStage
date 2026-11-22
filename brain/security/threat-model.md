# CardioStage: Threat Model

| | |
|---|---|
| **Assessment date** | 2026-11-23 (initial assessment at commit `8b6571f`; **updated after remediation** the same day) |
| **Scope** | Entire repository, the local Python environment (`.venv`), the Streamlit server as run locally, the GitHub remote and CI configuration |
| **Method** | Static review of all source/config/docs; Git history scan; inspection of the installed Streamlit 1.67.0 source for default behaviour; live, read-only probes against the local server; `pip-audit`; automated tests (`tests/test_security.py`) |
| **Companion docs** | [secrets.md](secrets.md) · [attack-surface.md](attack-surface.md) · [security-checklist.md](security-checklist.md) |

> **Classification legend** (all four documents): **Confirmed vulnerability** (exploitable flaw demonstrated) · **Security weakness** (confirmed config/design that lowers security) · **Missing control** · **Potential risk requiring verification** · **Recommendation**.
> **Severity:** Critical / High / Medium / Low / Info, rated for the current deployment (local app).
> **Status:** ✅ Remediated (verified) · 🟡 Partly remediated / residual risk · 🔵 Open: owner action · ⚪ Accepted for current scope.

**Result:** no confirmed vulnerabilities were found. Of the 11 findings (SEC-01–10, SEC-12), **5 are remediated and verified** (SEC-01, 03, 04, 06, 12), **4 are partly remediated** with residual risk documented (SEC-02, 05, 07, 08), and **2 are accepted** for local use (SEC-09, 10). See §6.

---

## 1. System summary (as implemented)
- A **single-process Streamlit app** (`app/streamlit_app.py`, views in `app/views/`) serving an educational heart-disease risk screener, run locally from the developer's virtual environment.
- **Listens on `127.0.0.1:8501` only** (`.streamlit/config.toml` `server.address = "localhost"`). Verified with `netstat` (`TCP 127.0.0.1:8501 LISTENING`) and an HTTP request to the machine's LAN address, which failed (`URLError`). Before remediation it listened on `0.0.0.0:8501` and `[::]:8501`.
- **No backend API, database, authentication, user accounts, file uploads, webhooks, cloud deployment or containers** exist.
- **CI exists** (`.github/workflows/ci.yml`: lint, tests, `pip-audit`, gitleaks) with read-only permissions, plus Dependabot (`.github/dependabot.yml`).
- Predictions come from **locally generated model bundles** (`models/stage{1,2,3}.joblib`, git-ignored), loaded with pickle **only after a SHA-256 check** against `models/manifest.json` (`src/cardiostage/integrity.py`).

## 2. Assets
| ID | Asset | Sensitivity | Where |
|---|---|---|---|
| A1 | **Patient inputs entered in the app** | High *if real people's data is entered* (health data); low for demo use | Browser ↔ local server websocket; server memory (`st.session_state`), never persisted or logged |
| A2 | **Risk outputs and explanations** | Same as A1 | Server memory; browser |
| A3 | **Model bundles** (`models/*.joblib`, 4.6–85 MB) + `manifest.json` | Integrity-critical (pickle can execute code) | Local disk, git-ignored |
| A4 | **Source code, reports, docs** | Public by intent (MIT) | Local disk; GitHub |
| A5 | **Training data** (`data/raw/heart_disease_uci.csv`) | Public, de-identified (CC BY 4.0) | Committed |
| A6 | **Developer identity data** (name, personal email in commit metadata) | Personal data | Git history, GitHub |
| A7 | **Host compute/availability** | Availability | Developer's PC |
| A8 | **Developer's GitHub account/push access** | High | OS credential store (not inspected) |

## 3. Actors
| Actor | Capability (current) | Relevance |
|---|---|---|
| **Developer/operator** (trusted) | Full local access | Owner |
| **Local browser user** (trusted) | Uses the app via `localhost` | Intended user |
| **Same-network user** (untrusted) | **Can no longer reach the app** (localhost binding), unless the operator deliberately runs with `--server.address 0.0.0.0` | Previously the main threat actor |
| **Internet user** (untrusted) | Not able to reach a localhost-bound socket | – |
| **Local malware / other local user** | Write access to the project folder | Can replace bundles; the manifest catches swapped files unless the attacker also rewrites the manifest |
| **Supply-chain attacker** | Compromises a PyPI package or GitHub Action | Code execution at install/CI time |
| **Third-party service** (`checkip.amazonaws.com`) | **No longer contacted** (non-wildcard address skips the lookup) | Previously received an HTTP request at each start |
| **GitHub viewers** | Read the remote repo (**public**: confirmed via the unauthenticated GitHub API) | Can read commit metadata (A6) |

## 4. Trust boundaries
| ID | Boundary | Crossed by | Current state |
|---|---|---|---|
| TB1 | **Browser ↔ Streamlit server** (HTTP + websocket `/_stcore/stream`, plaintext, no auth) | All app interaction | Loopback only, so traffic never leaves the machine |
| TB2 | **Host ↔ network** | – | Closed: socket bound to `127.0.0.1` |
| TB3 | **Server ↔ local filesystem** | `integrity.load`, `pd.read_csv`, `st.image` (fixed paths) | Pickles verified before load |
| TB4 | **Server ↔ third party** | – | Closed: no startup IP lookup |
| TB5 | **Developer/CI ↔ package index and GitHub Actions** | `pip install -r requirements.txt -c constraints.txt`; actions `checkout@v7`, `setup-python@v7`, `gitleaks-action@v3` | Pinned + constrained; audited |
| TB6 | **Local repo ↔ GitHub** | `git push` (HTTPS, no credentials in remote URL) | Unchanged |

## 5. Entry points
| ID | Entry point | Reachable from | Notes |
|---|---|---|---|
| EP1 | App frontend `GET /` (+ `/results`, `/about`) | localhost | No auth |
| EP2 | Websocket `/_stcore/stream` | localhost | All widget values; validated in `predictor.to_frame`; per-session rate limit |
| EP3 | `/_stcore/health`, `/_stcore/host-config` | localhost | Health → 200 |
| EP4 | `/media/<id>` | localhost | Unknown id → 404 |
| EP5 | `/_stcore/upload_file/...` (framework) | localhost | No uploader in app; unauthenticated PUT → **403 (XSRF)**, re-verified after remediation |
| EP6 | `/_stcore/agent/*` (framework, experimental) | localhost | Disabled (`enableAgentApi` default `false`); POST interact → 403 |
| EP7 | `models/*.joblib` | local filesystem | Verified against `manifest.json` before unpickling |
| EP8 | Dependency installation / CI | PyPI, GitHub | Constraints + `pip-audit` + Dependabot |
| EP9 | CLI scripts (`python -m cardiostage.*`) | local shell | No listeners |

## 6. Threats, impact, likelihood, severity, mitigations, status
| ID | Threat | Attack scenario | Impact | Likelihood (now) | Severity (now) | Existing mitigations | Missing / residual | Status |
|---|---|---|---|---|---|---|---|---|
| T1 / **SEC-01** | Disclosure & unauthorised use over the network | A device on the same Wi-Fi opens the app and sniffs plaintext traffic | Disclosure of A1/A2; unauthorised use | Very low (socket not reachable) | **Low** (was Medium) | `server.address = "localhost"` (verified 127.0.0.1 only; LAN request fails); XSRF/CORS explicit; agent API off | No TLS/auth if the operator overrides the address to share | ✅ Remediated |
| T2 / **SEC-02** | Denial of service | Scripted repeated stage-2/3 assessments (~5.5 s CPU each) | App/host slowed | Low (local only) | **Low** (was Medium) | Per-session limit 20 assessments / 60 s (`ratelimit.py`, `screener.run_stage`); localhost binding; `st.form` | Many parallel sessions aren't limited (would need a proxy) | 🟡 Partly remediated |
| T3 / **SEC-03** | Information disclosure via errors | Exception renders a traceback with local paths | Leaks paths/code | Very low | **Info** (was Low) | `client.showErrorDetails = "none"`; `run_stage` try/except with friendly messages; details only in server console (tested: `test_app_shows_friendly_errors_not_tracebacks`) | – | ✅ Remediated |
| T4 / **SEC-04** | Privacy: third-party IP lookup at startup | Streamlit contacted `checkip.amazonaws.com` (HTTP first) on each headless start | IP + start times disclosed | None (no longer happens) | **Info** (was Low) | Non-wildcard address: startup log now shows only `URL: http://localhost:8501` (no Network/External URL); `04-architecture.md` corrected | – | ✅ Remediated |
| T5 / **SEC-05** | Tampering → code execution via pickle | Replaced/corrupted `stage*.joblib` executes on load | Arbitrary code execution | Low | **Low** | `integrity.load` verifies SHA-256 vs `manifest.json` before every unpickle (app + all scripts); unlisted/mismatched/missing manifest → refused (tested incl. "refuse before unpickling"); bundles self-built, git-ignored | Attacker able to rewrite both bundle and manifest isn't stopped; pickle format remains | 🟡 Partly remediated |
| T6 / **SEC-06** | Crafted widget values | Websocket message with out-of-option selectbox values | Previously: traceback in own session | Very low | **Info** (was Low) | `to_frame` validates categories, coded values (`ALLOWED_CODES`), finiteness and `PLAUSIBLE_RANGES` → `InvalidInputError` → friendly message (measurements now use sliders; range enforcement is the engine's, not the widget's) | – | ✅ Remediated |
| T7 / **SEC-07** | Supply chain | Vulnerable/compromised (transitive) dependency | Code execution | Low | **Low** | `pip-audit`: no known vulnerabilities (requirements + full env, 2026-11-23); `constraints.txt` pins all 76 packages; CI audit on every push; Dependabot weekly | No hash pinning; GitHub Actions pinned by major tag, not commit SHA | 🟡 Partly remediated |
| T8 / **SEC-08** | Privacy: email in commit metadata | Viewers of the **public** repo harvest the personal Gmail from the earlier commits | Spam/phishing | Medium (repo confirmed public) | **Low** | Global Git email switched to the GitHub noreply address (2026-11-23): new commits no longer expose it | Earlier commits (up to `09225ff`) still contain the Gmail address; removal needs a destructive history rewrite (not recommended). GitHub "Block command line pushes that expose my email" enabled by the owner, preventing new exposure | 🟡 Partly remediated (history only) |
| T9 / **SEC-09** | No authentication | Anyone who can reach the server can use it | Unauthorised use | Very low (localhost) | **Info** (High if publicly deployed) | Localhost binding | Auth + TLS required before any shared deployment | ⚪ Accepted (local scope) |
| T10 / **SEC-10** | Repudiation / no monitoring | Abuse not recorded | No forensics | Low | **Info** | Assessment failures logged to the server console (`logging.getLogger("cardiostage.app")`), without patient inputs in the app's own messages | No access/audit logging | ⚪ Accepted (local scope) |
| T11 | Safety: output misused as diagnosis | User treats estimate as medical advice | Harm | Low–Medium | **Medium** (product safety) | Disclaimers on every page, non-diagnostic wording, limitations page, labelled limitation example | – | ⚪ Accepted (educational) |
| T12 / **SEC-12** | Exposure beyond LAN | Router/firewall forwarding to 8501 | Internet exposure | Very low (loopback-bound socket isn't reachable externally) | **Info** | Localhost binding | Optional owner check of firewall rules (see checklist) | ✅ Resolved by SEC-01 |

## 7. Attack scenario walk-throughs (after remediation)
1. **Coffee-shop Wi-Fi.** Another patron scans the network: port 8501 isn't open on any external interface (loopback only), so there's nothing to connect to, sniff or overload. *Residual:* only if the developer deliberately runs with `--server.address 0.0.0.0`.
2. **Poisoned model file.** A bundle downloaded from elsewhere is dropped into `models/`. Its hash isn't in the local manifest (or doesn't match), so `integrity.load` raises `IntegrityError`, the app shows "Model integrity check failed" and stops **without unpickling**. *Residual:* an attacker who can also rewrite `manifest.json`.
3. **Crafted input.** A local client sends `fbs="abc"` or `age=inf` over the websocket. `to_frame` raises `InvalidInputError`, the user sees "Some inputs aren't valid…", no model is called and no traceback is shown.
4. **Dependency compromise.** A malicious transitive release can't be pulled silently (pinned in `constraints.txt`). Known-vulnerable versions are flagged by `pip-audit` in CI and by Dependabot.

## 8. Existing security mechanisms (verified)
| Mechanism | Evidence |
|---|---|
| Localhost-only listening | `.streamlit/config.toml` `address = "localhost"`; `netstat`: `127.0.0.1:8501 LISTENING`; request to the LAN address → `URLError`; test `test_server_listens_on_localhost_only` |
| No startup third-party lookup | Startup log: only `URL: http://localhost:8501` (Streamlit calls `get_external_ip()` only for wildcard addresses, `streamlit/web/bootstrap.py:301-328`) |
| XSRF / CORS | Explicit `enableXsrfProtection = true`, `enableCORS = true`; unauthenticated upload PUT → 403 after remediation; test `test_framework_protections_explicitly_on` |
| Hidden error details | `client.showErrorDetails = "none"`; try/except in `screener.run_stage`; tests with an internal path in the error confirm it's never shown |
| Input validation | `predictor.to_frame` (`CHOICES`, `ALLOWED_CODES`, finiteness, `PLAUSIBLE_RANGES`); 11 attack values tested (the earlier Streamlit `number_input` clamping no longer applies: measurements use sliders since 2026-11-23) |
| Rate limiting | `ratelimit.check_and_record`, `config.RATE_LIMIT_*`; 3 tests |
| Pickle integrity | `integrity.py`; `manifest.json` written by `calibration.main` / `python -m cardiostage.integrity`; no direct `joblib.load` in `src/` or `app/` outside `integrity.py`; 4 tests |
| Agent API off, static serving off | Defaults; 403 probe |
| Developer options hidden remotely | `client.toolbarMode = "auto"` |
| Telemetry off | `gatherUsageStats = false` |
| Session isolation | Shared predictor holds only models + public training data |
| No input persistence/logging | No file/DB writes in `app/`; error messages don't include inputs |
| Secrets hygiene | None present; `secrets.toml` ignored; gitleaks job in CI |
| Supply chain | Pins + constraints; `pip-audit` clean; CI audit; Dependabot |
| Safety messaging | `ui.DISCLAIMER` on all pages |

## 9. Remaining work
- 🟡 **SEC-08:** done for future commits (noreply email set); historical commits still show the old address. GitHub's "Block command line pushes that expose my email" is now enabled (owner), so only old history remains.
- 🟡 **SEC-02:** a proxy-level limit if the app is ever shared.
- 🟡 **SEC-05:** move bundles to a non-executable format (e.g. skops) or a signed manifest stored outside `models/` if bundles are ever distributed.
- 🟡 **SEC-07:** optional hash pinning; pin GitHub Actions to commit SHAs.
- ⚪ **SEC-09/10:** TLS, authentication and access logging are prerequisites for any shared deployment.
- 🔍 Confirm the first CI run passes on GitHub after this change is pushed.
