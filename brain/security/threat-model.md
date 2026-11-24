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

**Result:** no confirmed vulnerabilities were found. Of the 14 findings (SEC-01–10, SEC-12–15), **8 are remediated and verified** (SEC-01, 03, 04, 05, 06, 07, 12, 15), **2 are partly remediated** with residual risk documented (SEC-02, 08), and **4 are accepted** (SEC-09, 10 for a public educational demo; SEC-13, 14 as hosting-platform limits, disclosed). See §6.

> **Update 2026-11-24: the app is now public** at https://cardiostage.streamlit.app (Streamlit Community Cloud, free tier), by the owner's decision. §1A below covers what changed; the findings table has been re-rated for public exposure.

---

## 1. System summary (as implemented)
- A **single-process Streamlit app** (`app/streamlit_app.py`, views in `app/views/`) serving an educational heart-disease risk screener, run locally from the developer's virtual environment.
- **Listens on `127.0.0.1:8501` only** (`.streamlit/config.toml` `server.address = "localhost"`). Verified with `netstat` (`TCP 127.0.0.1:8501 LISTENING`) and an HTTP request to the machine's LAN address, which failed (`URLError`). Before remediation it listened on `0.0.0.0:8501` and `[::]:8501`.
- **No backend API, database, authentication, user accounts, file uploads, webhooks, cloud deployment or containers** exist.
- **CI exists** (`.github/workflows/ci.yml`: lint, tests, `pip-audit`, gitleaks) with read-only permissions, plus Dependabot (`.github/dependabot.yml`).
- A **static landing site** (`site/`) is published on GitHub Pages by `.github/workflows/pages.yml`. It has no backend or input, loads nothing from other origins, and uses a strict CSP (see [attack-surface.md §1A](attack-surface.md)).
- **Public deployment** (since 2026-11-24): the same app runs on Streamlit Community Cloud. Locally it still listens on localhost only. See §1A.
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

## 1A. Public deployment (Streamlit Community Cloud)
| Aspect | How it works | Evidence |
|---|---|---|
| Hosting | Community Cloud builds from the public GitHub repo (`main`) and installs exactly from `uv.lock`; apps run in the US; sleep after 12 h idle | Streamlit docs; deployment verified live |
| Transport | HTTPS only: plain HTTP is redirected to HTTPS by the platform | `curl http://cardiostage.streamlit.app` → 303 to an `https://` URL |
| Consent | Nothing runs until the visitor ticks "I understand…" (educational only, emergency advice, data handling, host statistics) | `app/consent.py`; `test_public.py`; verified live |
| Public detection | `CARDIOSTAGE_DEPLOYMENT=public` (a Community Cloud secret) **or** a `*.streamlit.app` Host header (safety net if the secret is missing) | `consent.is_public_deployment`; tested |
| Models | Never pickles online: skops files from the `models-v2` release, archive + all 63 files pinned by SHA-256 in `deploy/models.json`, HTTPS only, size-capped, only manifest names extracted, everything verified before anything loads, reviewed trusted-types list | `model_store.py`; `test_model_store.py` (9); live download verified 63/63 |
| Error details | Community Cloud forces `client.showErrorDetails=false` (= "stacktrace" in Streamlit 1.67); the app resets it to `"none"` at startup | `streamlit_app.py`; `test_error_details_forced_to_none` |
| Abuse | Per-session limit (20/min) + shared limit across all visitors (40/min, thread-safe) | `ratelimit.SharedLimiter`; tests |
| Patient data | Processed in memory only; never stored or logged by CardioStage; failures log no inputs | Code review; no file/DB writes in `app/` |
| Not controllable on this host | XSRF protection forced off (no upload widget exists, so no upload route is used); platform usage statistics and an owner viewer count (anonymised); no custom HTTP security headers (HSTS, CSP, frame options) | Streamlit docs "Status and limitations"; header probe |

## 4. Trust boundaries
| ID | Boundary | Crossed by | Current state |
|---|---|---|---|
| TB1 | **Browser ↔ Streamlit server** (HTTP + websocket `/_stcore/stream`, plaintext, no auth) | All app interaction | Loopback only, so traffic never leaves the machine |
| TB2 | **Host ↔ network** | – | Closed: socket bound to `127.0.0.1` |
| TB3 | **Server ↔ local filesystem** | `integrity.load`, `pd.read_csv`, `st.image` (fixed paths) | Pickles verified before load |
| TB4 | **Server ↔ third party** | – | Closed: no startup IP lookup |
| TB5 | **Developer/CI ↔ package index and GitHub Actions** | `uv sync --locked` from `uv.lock` (versions + file checksums); actions pinned to commit SHAs (`checkout`, `setup-uv`, `gitleaks-action`, Pages actions) | Locked with checksums; audited |
| TB6 | **Local repo ↔ GitHub** | `git push` (HTTPS, no credentials in remote URL) | Unchanged |
| TB7 | **Public visitor ↔ landing site** (GitHub Pages, HTTPS) | Page views only | Static; strict CSP; vendored scripts only; no data collected by the project |
| TB8 | **Public visitor ↔ online app** (Streamlit Community Cloud, HTTPS) | Consent, health inputs, results | Consent first; validation; per-session + shared rate limits; no storage/logging of inputs; host statistics disclosed |
| TB9 | **Online app ↔ GitHub release** (model download) | `cardiostage-models.zip` over HTTPS | Archive + every file verified against committed SHA-256s before use; skops trusted-types list |

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
| EP10 | `/app/static/fonts/*.woff2` (Streamlit static serving) | localhost | Fonts only (tested); traversal → 400; `nosniff` |
| EP11 | Landing site (GitHub Pages) | internet | Static files from `site/`; no input |
| EP12 | Online app `https://cardiostage.streamlit.app` (page + websocket) | internet | Consent gate; all EP1–EP6 behaviour now publicly reachable (agent API off, no uploader) |

## 6. Threats, impact, likelihood, severity, mitigations, status
| ID | Threat | Attack scenario | Impact | Likelihood (now) | Severity (now) | Existing mitigations | Missing / residual | Status |
|---|---|---|---|---|---|---|---|---|
| T1 / **SEC-01** | Disclosure & unauthorised use over the network | A device on the same Wi-Fi opens the app and sniffs plaintext traffic | Disclosure of A1/A2; unauthorised use | Very low (socket not reachable) | **Low** (was Medium) | `server.address = "localhost"` (verified 127.0.0.1 only; LAN request fails); XSRF/CORS explicit; agent API off | No TLS/auth if the operator overrides the address to share | ✅ Remediated |
| T2 / **SEC-02** | Denial of service | Scripted repeated stage-2/3 assessments (~6 s CPU each on 2 shared cores) from many tabs | App slowed for everyone | Medium (public) | **Low** | Per-session limit 20/60 s; **shared limit 40/60 s across all sessions** (`SharedLimiter`, thread-safe, tested); `st.form`; host may throttle | No IP-level limiting (no proxy on the free host) | 🟡 Partly remediated |
| T3 / **SEC-03** | Information disclosure via errors | Exception renders a traceback with local paths | Leaks paths/code | Very low | **Info** (was Low) | `client.showErrorDetails = "none"`; `run_stage` try/except with friendly messages; details only in server console (tested: `test_app_shows_friendly_errors_not_tracebacks`) | – | ✅ Remediated |
| T4 / **SEC-04** | Privacy: third-party IP lookup at startup | Streamlit contacted `checkip.amazonaws.com` (HTTP first) on each headless start | IP + start times disclosed | None (no longer happens) | **Info** (was Low) | Non-wildcard address: startup log now shows only `URL: http://localhost:8501` (no Network/External URL); `04-architecture.md` corrected | – | ✅ Remediated |
| T5 / **SEC-05** | Tampering → code execution via pickle | Replaced/corrupted model file executes on load | Arbitrary code execution | Low | **Low** | Locally: `integrity.load` verifies SHA-256 before every unpickle. **Online: no pickles at all**: skops with a reviewed trusted-types list; archive and every file pinned by SHA-256 in the committed `deploy/models.json`; verified before anything loads (tested: tampered archive/member, traversal names) | Someone able to change both the release asset and the committed manifest (i.e. the repo owner's account) | ✅ Remediated |
| T6 / **SEC-06** | Crafted widget values | Websocket message with out-of-option selectbox values | Previously: traceback in own session | Very low | **Info** (was Low) | `to_frame` validates categories, coded values (`ALLOWED_CODES`), finiteness and `PLAUSIBLE_RANGES` → `InvalidInputError` → friendly message (measurements now use sliders; range enforcement is the engine's, not the widget's) | – | ✅ Remediated |
| T7 / **SEC-07** | Supply chain | Vulnerable/compromised (transitive) dependency | Code execution | Low | **Low** | `pip-audit`: no known vulnerabilities (full env, 2026-11-23); `uv.lock` pins all 79 packages **with SHA-256 checksums for every platform** (`requirements.txt` exported from it with `--hash` lines); CI installs with `uv sync --locked`; GitHub Actions pinned to **commit SHAs**; Dependabot weekly (uv + actions) | Vendored front-end libraries (site only) not scanned automatically | ✅ Remediated |
| T8 / **SEC-08** | Privacy: email in commit metadata | Viewers of the **public** repo harvest the personal Gmail from the earlier commits | Spam/phishing | Medium (repo confirmed public) | **Low** | Global Git email switched to the GitHub noreply address (2026-11-23): new commits no longer expose it | Earlier commits (up to `09225ff`) still contain the Gmail address; removal needs a destructive history rewrite (not recommended). GitHub "Block command line pushes that expose my email" enabled by the owner, preventing new exposure | 🟡 Partly remediated (history only) |
| T9 / **SEC-09** | No authentication | Anyone can use the online app | Unauthorised use | Expected (public demo) | **Info** | By design (owner decision): public educational demo with consent gate, no stored data, rate limits | Login would be needed for any non-demo use | ⚪ Accepted (public demo) |
| T10 / **SEC-10** | Repudiation / no monitoring | Abuse not recorded | No forensics | Low | **Info** | Platform logs (owner-visible); app logs failures without inputs | No audit logging by design (privacy: no inputs recorded) | ⚪ Accepted |
| T11 | Safety: output misused as diagnosis | A visitor treats an estimate as medical advice | Harm | Medium (public) | **Medium** (product safety) | Consent screen (not a diagnosis; call emergency services for chest pain); disclaimers on every page; non-diagnostic wording; limitations page; labelled limitation example | – | ⚪ Accepted (educational) |
| T13 / **SEC-13** | Host overrides security settings | Community Cloud forces `showErrorDetails=false` (tracebacks), `enableXsrfProtection=false`, `gatherUsageStats=true`; no custom security headers | Error-detail leak; weaker CSRF; telemetry | Certain (platform) | **Low** | `showErrorDetails` reset to `"none"` in code (tested); no upload widget, so XSRF's main protected route is unused; telemetry disclosed on the consent screen | XSRF/telemetry/headers can't be changed on this host | ⚪ Accepted (disclosed) |
| T14 / **SEC-14** | Privacy: hosting platform | Visitor inputs are processed on a US server; the platform collects usage statistics and shows the owner an anonymous viewer count | Disclosure to the host | Certain (platform) | **Low** | Consent screen + About page state this plainly with a link to Streamlit's privacy notice; CardioStage stores/logs nothing; no identifying fields | Owner accepted (2026-11-24) instead of paying for a self-controlled host | ⚪ Accepted (disclosed) |
| T15 / **SEC-15** | Model supply for the online app | A tampered or corrupted release download | Wrong predictions / code execution | Low | **Low** | HTTPS; size cap; SHA-256 of archive and each member vs committed manifest; extract only listed names; skops trusted types; nothing loads unless all files verify (tested) | – | ✅ Remediated |
| T12 / **SEC-12** | Exposure beyond LAN | Router/firewall forwarding to 8501 | Internet exposure | Very low (loopback-bound socket isn't reachable externally) | **Info** | Localhost binding | Optional owner check of firewall rules (see checklist) | ✅ Resolved by SEC-01 |

## 7. Attack scenario walk-throughs (after remediation)
1. **Coffee-shop Wi-Fi.** Another patron scans the network: port 8501 isn't open on any external interface (loopback only), so there's nothing to connect to, sniff or overload. *Residual:* only if the developer deliberately runs with `--server.address 0.0.0.0`.
2. **Poisoned model file.** A bundle downloaded from elsewhere is dropped into `models/`. Its hash isn't in the local manifest (or doesn't match), so `integrity.load` raises `IntegrityError`, the app shows "Model integrity check failed" and stops **without unpickling**. *Residual:* an attacker who can also rewrite `manifest.json`.
3. **Crafted input.** A local client sends `fbs="abc"` or `age=inf` over the websocket. `to_frame` raises `InvalidInputError`, the user sees "Some inputs aren't valid…", no model is called and no traceback is shown.
4. **Dependency compromise.** A malicious transitive release can't be pulled silently: every package is pinned in `uv.lock` with checksums, so even a re-uploaded file with the same version number would be rejected. Known-vulnerable versions are flagged by `pip-audit` in CI and by Dependabot.

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
| Agent API off | Default; 403 probe |
| Static serving limited to fonts | `enableStaticServing = true` with `app/static/` holding only `.woff2` (test-enforced); traversal probes → 400 |
| Landing-site hardening | Strict CSP, no inline code, no external loads (3 tests in `test_site.py`); vendored libs sha512-verified |
| Developer options hidden remotely | `client.toolbarMode = "auto"` |
| Telemetry off | `gatherUsageStats = false` |
| Session isolation | Shared predictor holds only models + public training data |
| No input persistence/logging | No file/DB writes in `app/`; error messages don't include inputs |
| Secrets hygiene | None present; `secrets.toml` ignored; gitleaks job in CI |
| Supply chain | Pins + constraints; `pip-audit` clean; CI audit; Dependabot |
| Safety messaging | `ui.DISCLAIMER` on all pages |

## 9. Remaining work
- 🟡 **SEC-08:** done for future commits (noreply email set); historical commits still show the old address. GitHub's "Block command line pushes that expose my email" is now enabled (owner), so only old history remains.
- 🟡 **SEC-02:** shared limit added for the public app; IP-level limiting would need a host with a configurable proxy.
- ✅ **SEC-05:** done (2026-11-24): online models are skops only (reviewed trusted types, SHA-256-pinned).
- ✅ **SEC-07:** done (2026-11-23): `uv.lock` with checksums, CI installs `--locked`, GitHub Actions pinned to commit SHAs. Remaining: review vendored site libraries manually.
- ⚪ **SEC-09/10:** accepted for the public educational demo (TLS by the host; no login; no input logging by design). Required for any non-demo use.
- ⚪ **SEC-13/14:** hosting-platform limits (forced settings, telemetry, no custom headers), disclosed to visitors; moving to a self-controlled host (e.g. paid Hugging Face) would lift them.
- 🔍 Confirm the first CI run passes on GitHub after this change is pushed.
- 🟡 **Landing site:** vendored front-end libraries aren't covered by Dependabot/pip-audit; check for updates manually (e.g. each release). ⚪ `frame-ancestors` can't be set on GitHub Pages (static page with no actions).
