# CardioStage: Secrets Assessment

| | |
|---|---|
| **Assessment date** | 2026-11-23 (initial at commit `8b6571f`; updated after remediation) |
| **Scope** | All tracked files, untracked project files (excluding `.venv/` contents), full Git history, `.git/config`, Streamlit configuration, CI configuration |
| **Companion docs** | [threat-model.md](threat-model.md) · [attack-surface.md](attack-surface.md) · [security-checklist.md](security-checklist.md) |

> No secret values are copied into this document. Where a value exists, only its type and location are described.

## Summary
**CardioStage has no secrets and currently needs none.** It uses no API keys, tokens, passwords, database credentials, private keys or third-party accounts at build or run time. Scans found **no secret material** in the working tree or Git history. Since remediation, **secret scanning runs automatically in CI** (gitleaks).

| Category | Result |
|---|---|
| Confirmed vulnerabilities | **None** |
| Security weaknesses | **SEC-08** (Low, 🔵 open, owner action): personal email address in commit metadata |
| Missing controls | ✅ *Resolved:* automated secret scanning added (gitleaks CI job). Optional: GitHub push protection (owner setting) |
| Potential risks requiring verification | GitHub repository visibility (sizes SEC-08 exposure) |

## 1. Where secrets are expected
| Location | Expected? | Evidence |
|---|---|---|
| Application code (`src/`, `app/`) | **No**: no external services are called | No `os.environ`, `getenv`, `st.secrets`, HTTP clients or sockets in project code |
| `.streamlit/secrets.toml` | **Not present**; git-ignored | `.gitignore` line 26 |
| `.env` files | **Not present** | – |
| CI secrets | **Only GitHub's automatic `GITHUB_TOKEN`** | `.github/workflows/ci.yml` passes `${{ secrets.GITHUB_TOKEN }}` to the gitleaks action. It's issued per run by GitHub, scoped by `permissions: contents: read`, never stored in the repo |
| Deployment platform secrets | **Not applicable** | No deployment config |
| Git remote credentials | Outside the repo | Remote URL has **no embedded credentials**; push auth via the OS/Git credential store (not inspected) |
| Data download (Kaggle) | Manual | No Kaggle API token used or stored |
| Streamlit `server.cookieSecret` | Framework-generated | Not set; Streamlit generates a random value in memory per process. No cookie-dependent features (no `st.login`) are used |
| Model integrity manifest (`models/manifest.json`) | **Not a secret** | Contains SHA-256 fingerprints of local bundles. Public-safe, git-ignored with the rest of `models/` |

## 2. Environment and configuration handling
- `src/cardiostage/config.py`: non-sensitive constants only (paths, seed, thresholds, rate limits). Nothing is read from the environment.
- `.streamlit/config.toml`: theme plus security settings (`address`, XSRF/CORS, `showErrorDetails`, telemetry). No credentials.
- `requirements.txt`, `constraints.txt`, `pyproject.toml`: package pins and tool settings. No private index URLs or tokens.
- **If a secret is ever needed:** store it in `.streamlit/secrets.toml` (already ignored) or environment variables. Never in `config.py`. The gitleaks CI job would flag accidental commits.

## 3. Hardcoded-secret risks
| Check | Method | Result |
|---|---|---|
| Credential patterns (AWS, GitHub, OpenAI-style, Slack, private-key headers, `password=`, `api_key=`, `secret=`) in current files | Case-insensitive search excluding `.venv/`, `.git/` | **0 matches** |
| Same patterns across all history | `git log -p --all` | **0 matches** |
| Sensitive filenames ever committed (`.env`, `secret`, `credential`, `.pem`, `.key`, `id_rsa`, `.joblib`, `.pkl`) | `git log --all --name-only` | **None** |
| Ongoing | gitleaks on every push/PR (`fetch-depth: 0`, full history) | Automated |

## 4. Client-side exposure risks
- No secrets exist to reach the browser. Data sent to the browser: patient inputs/outputs, public charts and result tables.
- ✅ *Resolved (SEC-03):* tracebacks with local paths are no longer shown (`client.showErrorDetails = "none"` plus friendly error handling in `app/views/screener.py`).

## 5. Git and history exposure risks
| Item | Evidence | Assessment |
|---|---|---|
| Secrets in history | 0 pattern matches | ✅ None |
| Model pickles | Never committed (`models/*` ignored) | ✅ |
| **Commit author email** (**SEC-08**) | All commits authored with a personal Gmail address | 🔵 Open: owner action |
| Author name | Commit metadata, `LICENSE` | Intentional |
| Local paths | `docs/learning/01-setup.md` shows the project folder path (no username) | Informational |

**SEC-08:** Severity **Low** → Evidence: `git log --format='%ae'` yields one personal Gmail address on every commit → Risk: spam, phishing, profiling → Affected: Git history on GitHub, global Git config → Why it matters: commit metadata is permanent and visible to anyone who can read the repo → Recommended fix (**owner action**):
1. On GitHub: **Settings → Emails** → tick **"Keep my email addresses private"** and **"Block command line pushes that expose my email"**. Copy the address shown there, of the form `ID+username@users.noreply.github.com`.
2. In a terminal: `git config --global user.email "ID+username@users.noreply.github.com"` (use the copied address).
3. Future commits use the private address. Rewriting the existing commits is **optional and destructive** (force-push), and not recommended unless the email must be removed from history.

## 6. Logging and error exposure risks
| Source | What it logs | Secret exposure |
|---|---|---|
| Analysis scripts (`print`) | Metrics, saved-file paths, aggregate tables; `final_evaluation.py` prints missed **public test-set** rows | None |
| App (`app/views/screener.py`) | On unexpected assessment errors only: `logger.exception("Assessment failed")` to the **server console** (traceback; the app adds no patient inputs to the message) | None |
| Streamlit server log | Startup URL (now only `http://localhost:8501`), warnings | None (LAN/public IP no longer printed) |
| Browser | Friendly messages only | None |

## 7. Secret rotation requirements
- **Currently none:** no secrets exist. `GITHUB_TOKEN` in CI is issued and expired automatically per run by GitHub.
- **Developer GitHub credentials** (outside the repo): rotate if the machine is compromised; prefer a fine-grained token or SSH key.
- **If secrets are added later:** define storage (`secrets.toml` / env vars), owner, rotation period (e.g. 90 days), immediate rotation on suspected exposure.

## 8. Recommendations
| ID | Type | Recommendation | Status |
|---|---|---|---|
| R-S1 | Recommendation | Switch to a GitHub noreply email (SEC-08) | 🔵 Owner action (steps above) |
| R-S2 | Potential risk requiring verification | Confirm repository visibility (GitHub repo page → public/private badge) | 🔵 Owner check |
| R-S3 | Missing control | Automated secret scanning | ✅ gitleaks CI job added. Optional extra: GitHub **Settings → Code security → Secret Protection / Push protection** (available for public repos) |
| R-S4 | Recommendation | If auth/hosting is added, set `server.cookieSecret` via `secrets.toml` | ⚪ Not needed yet |
