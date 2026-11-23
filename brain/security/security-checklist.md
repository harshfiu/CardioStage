# CardioStage: Security Checklist

| | |
|---|---|
| **Assessment date** | 2026-11-23 (initial at commit `8b6571f`; **updated after remediation**) |
| **Context** | Local, single-user educational Streamlit app; no auth, DB, uploads or APIs; CI on GitHub |
| **Companion docs** | [threat-model.md](threat-model.md) · [secrets.md](secrets.md) · [attack-surface.md](attack-surface.md) |

**Checklist key:** ✅ In place (verified) · ⚠️ Weakness / residual risk · ❌ Missing control · 🔍 Requires verification · ➖ Not applicable · 💡 Recommendation · 🔵 Owner action
**Finding status:** ✅ Remediated · 🟡 Partly remediated · 🔵 Open: owner action · ⚪ Accepted for current scope

---

## Part A: Findings by classification

### Confirmed vulnerabilities
**None found.** Live probes confirmed that the framework protections tested work: XSRF on uploads, a disabled agent API, and localhost-only binding.

### Security weaknesses

#### SEC-01: Server listened on all network interfaces without authentication or TLS (✅ Remediated)
- **Severity:** Medium → now **Low** (residual only if deliberately overridden)
- **Evidence (before):** no `server.address`; `netstat` showed `0.0.0.0:8501` and `[::]:8501`; log printed Network and External URLs.
- **Evidence (after):** `.streamlit/config.toml` `[server] address = "localhost"`; `netstat`: `TCP 127.0.0.1:8501 LISTENING`; HTTP request to the LAN address → `URLError`; log shows only `URL: http://localhost:8501`; test `test_server_listens_on_localhost_only`.
- **Risk:** Network users could use the app and sniff plaintext health inputs.
- **Affected location:** `.streamlit/config.toml`.
- **Why it matters:** The app handles health-type inputs and was often run on shared networks.
- **Fix applied:** localhost binding. *Residual:* `--server.address 0.0.0.0` re-exposes the app without TLS/login (documented).

#### SEC-03: Full error details shown to viewers (✅ Remediated)
- **Severity:** Low → now **Info**
- **Evidence (before):** default `client.showErrorDetails = "full"`; no `try/except` around `predictor.assess()`.
- **Evidence (after):** `[client] showErrorDetails = "none"`; `app/views/screener.py` `run_stage` catches `InvalidInputError` (friendly "inputs aren't valid") and any other exception (logged to the server console; generic message). Tests `test_app_shows_friendly_errors_not_tracebacks` (2 cases, one with an internal path in the error) confirm no traceback and no internal details.
- **Risk:** Disclosure of local paths and code.
- **Affected location:** `.streamlit/config.toml`; `app/views/screener.py`.
- **Why it matters:** Reconnaissance aid.
- **Fix applied:** as above.

#### SEC-04: Outbound IP lookup to a third party at every start (✅ Remediated)
- **Severity:** Low → now **Info**
- **Evidence (before):** headless + wildcard address triggered `net_util.get_external_ip()` → `checkip.amazonaws.com` (HTTP, then HTTPS); "External URL" in the log; `04-architecture.md` didn't mention it.
- **Evidence (after):** specific address → Streamlit's single-URL branch (`streamlit/web/bootstrap.py:301-328`), so no lookup; log shows only the localhost URL. `docs/project/04-architecture.md` §1/§9 corrected.
- **Risk:** Public IP and start times disclosed; doc inaccuracy.
- **Fix applied:** localhost binding (same change as SEC-01); docs updated.

#### SEC-08: Personal email address in public commit metadata (🟡 Partly remediated)
- **Severity:** Low
- **Evidence:** one personal Gmail address on every commit up to `09225ff` (`git log --format='%ae'`); the repository is **public** (confirmed via the unauthenticated GitHub API).
- **Risk:** Spam, phishing, profiling.
- **Affected location:** Git history; global Git config.
- **Why it matters:** Commit metadata is permanent and public.
- **Fix applied:** global Git email set to the GitHub noreply address (verified; no repo-level override), so new commits no longer expose the Gmail address.
- **Also done:** GitHub "Block command line pushes that expose my email" enabled by the owner on 2026-11-23 (account/repo settings; not verifiable via the public API).
- **Remaining:** historical commits keep the old address (rewrite is destructive and not recommended). See [secrets.md §5](secrets.md#5-git-and-history-exposure-risks).

### Missing controls

#### SEC-02: No rate limiting or resource limits (🟡 Partly remediated)
- **Severity:** Medium → now **Low**
- **Evidence (after):** `src/cardiostage/ratelimit.py` sliding window; `config.RATE_LIMIT_MAX_ASSESSMENTS = 20`, `RATE_LIMIT_WINDOW_SECONDS = 60`; enforced in `screener.run_stage` with a "please wait" warning; 3 tests. Localhost binding removes network abusers.
- **Risk:** CPU exhaustion via repeated assessments (~5.5 s CPU each at stages 2–3).
- **Residual:** limit is per browser session; many parallel sessions aren't capped (needs a reverse proxy if shared).

#### SEC-07: No dependency scanning; transitive dependencies unpinned (🟡 Partly remediated)
- **Severity:** Low
- **Evidence (after):** `pip-audit -r requirements.txt` and full-environment audit → **"No known vulnerabilities found"** (2026-11-23); `constraints.txt` pins all 76 installed packages; CI runs `pip-audit` on every push/PR; `.github/dependabot.yml` weekly PRs (pip + GitHub Actions); `pip-audit==2.10.1` pinned in `requirements.txt`.
- **Residual:** no hash pinning; actions referenced by major tag, not commit SHA.

#### SEC-09: No authentication or authorization (⚪ Accepted for local use)
- **Severity:** Info (localhost-only); **High** if deployed publicly
- **Evidence:** no auth code. The app is reachable only from the local machine.
- **Required before sharing:** reverse-proxy authentication or `st.login` (with `cookieSecret` in `secrets.toml`) plus TLS.

#### SEC-10: No security logging or monitoring (⚪ Accepted for local use)
- **Severity:** Info
- **Evidence (after):** unexpected assessment failures are now logged to the server console (`logging.getLogger("cardiostage.app").exception`); no access/audit log.
- **Required before sharing:** proxy access logs. Never log patient inputs.

### Potential risks requiring verification

#### SEC-05: Pickle deserialisation of model bundles (🟡 Partly remediated)
- **Severity:** Low (High if bundles were ever obtained from untrusted sources)
- **Evidence (after):** `src/cardiostage/integrity.py` writes `models/manifest.json` (SHA-256 of `stage{1,2,3}.joblib`, `phase4_oof.joblib`, `phase5_oof.joblib`) from `calibration.main` or `python -m cardiostage.integrity`. **All** pickle loads in `src/` and `app/` go through `integrity.load`, which refuses unlisted/mismatched files or a missing manifest **before unpickling**. The app shows "Model integrity check failed" and stops. 4 tests, including refuse-before-unpickle and verification of the real bundles.
- **Residual / verify:** an attacker with write access to `models/` could rewrite both bundle and manifest. Keep `models/` writable only by you; never load third-party bundles; use skops or an externally stored signed manifest if bundles are ever distributed.

#### SEC-06: Crafted widget values outside UI options (✅ Remediated)
- **Severity:** Low → now **Info**
- **Evidence:** Streamlit's `selectbox.deserialize` passes unknown strings through (`selectbox.py:171-172`). Now `predictor.to_frame` enforces `CHOICES`, `ALLOWED_CODES` (sex/fbs/exang/ca), finiteness and `PLAUSIBLE_RANGES`, raising `InvalidInputError`, which the UI shows as a friendly message. 11 attack values tested (e.g. `fbs="abc"`, `ca=7`, `age=inf`, `chol="1e309"`, `oldpeak=50`).
- **Fix applied:** engine-side validation + UI error handling.

#### SEC-12: Exposure beyond the local network (✅ Resolved by SEC-01)
- **Severity:** Info
- **Evidence:** a socket bound to 127.0.0.1 isn't reachable from other hosts regardless of router settings.
- **Optional owner check:** Windows Security → Firewall & network protection → Allow an app through firewall → review entries for `python.exe` (remove "Public" if present).

### Recommendations
| ID | Recommendation | Status |
|---|---|---|
| R-1 | Localhost binding + hidden error details (SEC-01/03/04) | ✅ Done |
| R-2 | Correct `docs/project/04-architecture.md` (network statements) | ✅ Done |
| R-3 | Dependency audit + secret scanning in CI | ✅ Done (`pip-audit`, gitleaks) |
| R-4 | Before any deployment: TLS, authentication, proxy rate limits, explicit `cookieSecret`, safer artefact format, hash-locked deps | ⚪ Not needed for local use |
| R-5 | Keep XSRF/CORS on and the agent API off | ✅ Set explicitly; guarded by `test_framework_protections_explicitly_on` |
| R-6 | Switch commit email to GitHub noreply (SEC-08) | ✅ Done for new commits; optional GitHub email-privacy setting (owner) |
| R-7 | Enable GitHub secret scanning / push protection and Dependabot alerts in repo settings | ✅ Done (enabled by the owner on 2026-11-23 (account/repo settings; not verifiable via the public API)) |
| R-8 | Pin GitHub Actions to commit SHAs | 💡 Optional |

---

## Part B: Checklist by area

### Authentication
- ❌ User authentication: none (SEC-09, ⚪ accepted: app is localhost-only)
- ➖ Password storage / MFA / account recovery: no accounts
- 💡 Add auth + TLS before any shared deployment

### Authorization / RBAC
- ➖ No roles, admin functions or protected data
- ✅ Privileged actions (retraining, manifest regeneration) require shell access
- ✅ Developer toolbar hidden from non-localhost viewers

### Session / token security
- ✅ Per-session isolation (`st.session_state`); shared predictor holds no user data
- ✅ `cookieSecret` auto-generated per process, never committed; no cookie-based features
- ✅ CI `GITHUB_TOKEN` limited to `contents: read`
- 💡 Explicit `cookieSecret` via secrets if auth is added

### Input validation
- ✅ UI bounds (sliders limited to the plausible ranges); server-side bounds are enforced by the engine (`PLAUSIBLE_RANGES`), not by the widget
- ✅ Engine validation of every input: categories, coded values, finiteness, plausible ranges (`predictor.to_frame`)
- ✅ Missing values handled explicitly and disclosed
- ✅ Out-of-training-range inputs flagged by the novelty detector
- ✅ Invalid input → friendly message, no model call (tested)

### Injection
- ➖ SQL/NoSQL: no database
- ✅ No `subprocess`/`os.system`/`eval`/`exec` in project code
- ✅ No user-controlled file paths
- ⚠️ Pickle deserialisation remains, but hash-verified before load (SEC-05, 🟡)

### XSS / CSRF
- ✅ No raw HTML rendering
- ✅ User-influenced text rendered only after validation/numeric formatting
- ✅ XSRF protection explicitly on (verified 403)
- ✅ Landing site: strict CSP without `unsafe-inline`; no inline scripts/styles; DOM built without `innerHTML` (tested)
- ⚪ Landing site can't send `frame-ancestors` (GitHub Pages, meta CSP); no actions to clickjack

### API security
- ➖ No project API
- ✅ Streamlit agent API disabled (403)
- ✅ Static serving on for self-hosted fonts only (test-enforced; traversal → 400; `nosniff`)

### Rate limiting / abuse
- ✅ Per-session limit: 20 assessments / 60 s (tested)
- ✅ Work only on explicit form submission; models loaded once
- ⚠️ No cross-session/proxy limits (SEC-02, 🟡; acceptable on localhost)

### File uploads
- ➖ No upload feature
- ✅ Framework upload route rejects requests without an XSRF token (403)

### Database security
- ➖ No database

### Secrets
- ✅ No secrets in code, config or history
- ✅ `.streamlit/secrets.toml` git-ignored
- ✅ Remote URL contains no credentials
- ✅ gitleaks secret scan on every push/PR (full history)
- ⚠️ Personal email in earlier commit metadata (SEC-08, 🟡); new commits use the noreply address
- ✅ GitHub push protection and Dependabot alerts enabled by the owner (R-7)

### Encryption
- ➖ TLS: not needed while traffic stays on loopback; ❌ required if ever shared
- ➖ Encryption at rest: no user data stored
- ✅ GitHub transport uses HTTPS

### CORS
- ✅ `enableCORS = true` set explicitly; `corsAllowedOrigins = []` (default)

### Dependency security
- ✅ Direct dependencies pinned; all 76 installed packages constrained (`constraints.txt`)
- ✅ `pip-audit`: no known vulnerabilities (2026-11-23); runs in CI
- ✅ Dependabot weekly update PRs
- ⚠️ No hash pinning; actions pinned by major tag (SEC-07, 🟡)
- ✅ Landing-site libraries vendored at exact versions, sha512-verified; licences included
- ⚠️ Vendored front-end libraries not scanned automatically: update/review manually

### Logging / monitoring
- ✅ Patient inputs never written to logs or disk by the app
- ✅ Unexpected errors logged to the server console for the developer
- ⚠️ No access/audit logging (SEC-10, ⚪)

### Admin security
- ➖ No admin pages or API
- ✅ Developer options localhost-only; retraining needs shell access

### Deployment / infrastructure
- ✅ Localhost-only binding (verified)
- ✅ No startup third-party lookup (verified)
- ✅ Telemetry disabled
- ✅ CI with least-privilege permissions
- ✅ Generated artefacts excluded from Git
- ➖ No containers or cloud deployment of the app
- ✅ Landing site: static GitHub Pages deployment, least-privilege workflow (`pages: write`, `id-token: write`, `contents: read`)
- 🔵 Owner: Settings → Pages → Source: GitHub Actions

### Data privacy
- ✅ Inputs held only in session memory; never persisted or logged by the app
- ✅ Traffic stays on the local machine
- ✅ Training data public and de-identified
- ✅ Disclaimer against real-patient use on every page
- ⚠️ Developer email in earlier public commits (SEC-08, 🟡); new commits private
- ✅ No third-party requests from the site or app (fonts and libraries self-hosted; no analytics or cookies)

### Error handling
- ✅ `showErrorDetails = "none"`
- ✅ Assessment errors caught with friendly messages (tested)
- ✅ Missing or tampered models → friendly error and stop (no unpickling of tampered files)

### Backup / recovery
- ✅ Source, reports, figures and docs on GitHub
- ✅ Models reproducible (`train_all`, ~10 min, fixed seeds); manifest regenerated automatically
- ➖ No user data to back up
- 💡 Tag releases (e.g. `v1.0`)
