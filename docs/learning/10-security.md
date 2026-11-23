# Phase 10: Security Hardening

**Goal:** find out how CardioStage could be misused or broken by someone else, fix what's worth fixing, and write down honestly what's left.

Machine-learning projects often skip this step: the model is the exciting part, and an app that "only runs on my laptop" doesn't feel like it needs security. This phase shows why it still does, and how to do a security review without inventing problems.

**Files in this phase**

| File | Job |
|---|---|
| `brain/security/threat-model.md` | What we protect, from whom, every finding (SEC-01 … SEC-12) and its status |
| `brain/security/attack-surface.md` | Every way in: endpoints, inputs, files, dependencies, third parties |
| `brain/security/secrets.md` | Where secrets could leak (none are used) |
| `brain/security/security-checklist.md` | Area-by-area checklist (input validation, CSRF, supply chain…) |
| `.streamlit/config.toml` | Server settings: localhost only, hidden error details, XSRF/CORS on |
| `src/cardiostage/integrity.py` | SHA-256 fingerprints checked **before** any model file is loaded |
| `src/cardiostage/ratelimit.py` | Per-session limit: 20 assessments per 60 seconds |
| `src/cardiostage/predictor.py` | Strict input validation (`to_frame`, `InvalidInputError`) |
| `.github/workflows/ci.yml`, `.github/dependabot.yml`, `constraints.txt` | Lint, tests, vulnerability audit, secret scan, dependency updates |
| `tests/test_security.py` | 25 tests that prove each control works |

```bash
pytest tests/test_security.py -v         # the security controls, tested
pip-audit -r requirements.txt            # known vulnerabilities in our dependencies
python -m cardiostage.integrity          # re-record model fingerprints (only for files YOU built)
```

---

## 1. How to think about security: a threat model

A **threat model** answers four questions before any fixing starts:

1. **What are we protecting?** (assets) The model files, the app's availability, the user's privacy (the inputs they type), and the developer's privacy (e.g. their email).
2. **Who might attack, and how?** (actors) Someone on the same Wi-Fi, someone who sends a crafted file, a compromised Python package, or a stranger reading the public GitHub repo.
3. **Where can they get in?** (entry points / attack surface) Every network endpoint, every input field, every file the code loads, every dependency.
4. **What happens if they succeed, and how likely is it?** (impact × likelihood = severity)

Each finding got a label. The labels keep the review **honest**:

| Label | Meaning |
|---|---|
| **Confirmed vulnerability** | An exploitable flaw we actually demonstrated |
| **Security weakness** | A confirmed setting or design that lowers security |
| **Missing control** | Something that should exist but doesn't |
| **Potential risk** | Plausible, but needs checking before you call it real |
| **Recommendation** | Good practice, not a flaw |

**Result:** no confirmed vulnerabilities. The 11 findings were weaknesses, missing controls and risks. Severity is always rated *for how the app is actually used* (one person, locally). The same finding, "no login", is *Info* for a local app and *High* for a public website.

> **Lesson:** "Do not invent security issues." A review that cries wolf about everything gets ignored. Every claim in `brain/security/` points to evidence: a config line, a probe result or a test.

## 2. The findings and their fixes

### SEC-01: the app was reachable from the whole network
Streamlit's default `server.address` is empty, which means **every network interface**. Anyone on the same café Wi-Fi could open `http://<your-laptop-ip>:8501` and use the app, unencrypted.

**Fix** (`.streamlit/config.toml`):
```toml
[server]
address = "localhost"
```
**Verified:** `netstat` shows only `127.0.0.1:8501`, and a request to the laptop's LAN address fails. Test: `test_server_listens_on_localhost_only`.

### SEC-04: a surprise network call at every start
While reading Streamlit's source to confirm SEC-01, we found that in headless mode with a wildcard address, Streamlit contacts `checkip.amazonaws.com` at startup to print an "External URL". That sends your IP address to a third party every time the app starts. Binding to `localhost` skips that code path, so **one setting fixed two findings**.

> **Lesson:** read the framework's source for the behaviour you depend on. Defaults can do things the docs don't make obvious.

### SEC-03: tracebacks showed internal details
When something crashed, Streamlit displayed the full Python traceback, including local file paths and code. **Fix:** `client.showErrorDetails = "none"`, plus `try/except` around each assessment that shows a friendly message ("Something went wrong while assessing this patient…") and logs details only to the server console. Tests deliberately trigger an error containing a fake internal path and check it never appears on the page.

### SEC-05: model files are pickles, and pickles can run code
`joblib` saves models with Python's **pickle** format. Loading a pickle can execute arbitrary code, so a swapped or tampered `stage2.joblib` is dangerous, not merely wrong.

**Fix** (`integrity.py`): when models are built, record each file's **SHA-256 fingerprint** in `models/manifest.json`. Before loading, recompute it and refuse if it doesn't match:

```
build:  stage2.joblib ──sha256──► "9f2c…"  ──written to──► manifest.json
load:   stage2.joblib ──sha256──► "9f2c…"  == manifest?  yes → unpickle
                                            no  → IntegrityError (never unpickled)
```

A SHA-256 fingerprint changes completely if even one byte changes, so tampering or corruption is caught **before** the dangerous step. The docstring is honest about the limit: someone who can rewrite *both* the model and the manifest defeats it. That's why it's 🟡 *partly* remediated, with "signed manifest or a safer format (skops)" listed for any future distribution.

### SEC-06: crafted inputs could bypass the form
The browser talks to Streamlit over a websocket. A user can't type "banana" into a dropdown, but someone sending messages directly *can*. **Fix:** `predictor.to_frame` validates everything itself (allowed categories, 0/1 codes, finite numbers, plausible ranges such as age 18–100) and raises `InvalidInputError`. This is **defence in depth**: never rely on the UI alone to enforce rules. Eleven attack values are tested (NaN, infinity, negative ages, unknown categories…).

### SEC-02: one person could hog the computer
Stages 2–3 take ~5.5 s of CPU each. A script clicking in a loop could make the machine crawl. **Fix:** a sliding-window limit in `ratelimit.py`, small enough to read in full:

```python
recent = [t for t in timestamps if now - t < window_seconds]   # last 60 s only
if len(recent) >= max_events:                                     # 20 already?
    wait = window_seconds - (now - min(recent))                   # when the oldest expires
    return False, recent, max(wait, 0.0)
return True, recent + [now], 0.0
```
It's a **pure function** (no Streamlit inside), so tests can pass in fake timestamps instead of waiting a minute.

### SEC-07: the supply chain
Your code is a small fraction of what runs: the app installs **76 packages**. Controls:
- `requirements.txt` pins direct dependencies; `constraints.txt` pins **all 76** to tested versions.
- `pip-audit` checks them against the public vulnerability database, locally and in CI.
- **Dependabot** opens weekly update PRs (you merged the first batch: ruff, `actions/checkout`, `setup-python`, `gitleaks-action`).
- **gitleaks** scans the full Git history for accidentally committed secrets.

### SEC-08: your email in public commits
Every Git commit records an author email. On a public repo, anyone can read it, and spam harvesters do. **Fix:** commits now use GitHub's private `noreply` address, and you enabled "Block command line pushes that expose my email". Old commits still show the earlier address (rewriting public history causes more problems than it solves), so this is documented as 🟡.

### Accepted for local use: SEC-09, SEC-10
No login and no access logs. Both are fine for a local, single-user app, and both are **prerequisites before any public deployment**. Writing that down ("accepted for current scope") is better than silently ignoring it.

## 3. Proving it: security tests

A control that isn't tested can quietly break in a later refactor. `tests/test_security.py` checks:

| What | How |
|---|---|
| Config hardening | Reads `config.toml`: localhost bind, `showErrorDetails = "none"`, XSRF/CORS on |
| Integrity | Tampered file, unlisted file, missing manifest → `IntegrityError`, and **the file is never unpickled** |
| Validation | 11 hostile values each raise `InvalidInputError` |
| Rate limit | 20 allowed, 21st refused, allowed again after the window |
| Friendly errors | The real app (via `AppTest`) shows a friendly message, never a traceback or path |

## 4. Later additions (Phase 11)

The redesign added a **public** surface for the first time: the website. It got its own review (`attack-surface.md §1A`): a strict Content-Security-Policy, no inline scripts, no third-party requests, and vendored libraries verified by checksum. The app's new static file route (for self-hosted fonts) was probed: fonts → 200, directory listing → 404, `../` path traversal → **400**. See [Phase 11](11-website-and-design.md).

## 5. Check your understanding
1. Why is "no login" rated *Info* for CardioStage but would be *High* for a public website?
2. Binding to `localhost` fixed two findings. Which two, and why did one setting fix both?
3. Why check the SHA-256 fingerprint *before* calling `joblib.load`, rather than loading and then checking?
4. The dropdowns only offer valid options. Why validate inputs again in `predictor.py`?
5. Why is the rate limiter written as a pure function instead of directly using `st.session_state` and `time.time()`?
6. What does the integrity check *not* protect against, and why is it still worth having?

## Answers

**1.** Severity is impact × likelihood **for the actual deployment**. Locally, only you can reach the app (it listens on localhost), so the likelihood of misuse is near zero. On a public site, anyone on the internet could use it, so the same missing control becomes serious.

**2.** SEC-01 (reachable from the network) and SEC-04 (startup call to `checkip.amazonaws.com`). Streamlit only looks up your external IP when bound to all interfaces, to print an "External URL". A specific address both closes the network exposure and skips that lookup.

**3.** Because loading a pickle is the dangerous step: it can run code. Checking afterwards would be like checking a parcel for a bomb after opening it. The fingerprint is computed from the raw bytes without unpickling, so a bad file is rejected safely.

**4.** The UI isn't a security boundary. Someone can send websocket messages directly, skipping the widgets. Validating in the engine ("defence in depth") also protects any future interface that reuses `predictor.py`.

**5.** A pure function (inputs in, outputs out, no hidden state) can be tested instantly with fake times like `now=1000.0`, and it can't be broken by Streamlit internals. The page just stores the timestamp list in session state and calls it.

**6.** Someone with write access to `models/` can replace both the bundle and `manifest.json`. It's still worth having because it catches the realistic cases (a bundle copied from elsewhere, a corrupted or partial file, a swapped file) at almost no cost, and it documents a clear upgrade path (a signed manifest or skops) for distribution.
