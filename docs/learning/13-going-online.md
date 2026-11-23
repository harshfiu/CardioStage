# Phase 13: Going Online

**Goal:** put the full screener on the internet, so anyone can try it at **https://cardiostage.streamlit.app**, without giving up privacy, safety or security. Until now the app only ran on your own computer, so almost every decision in this phase is about what changes once *strangers* can use it.

**Files in this phase**

| File | Job |
|---|---|
| `app/consent.py` | The "Before you start" screen; local vs public privacy wording |
| `app/streamlit_app.py` | Forces hidden error details, then requires consent before any page runs |
| `src/cardiostage/model_store.py` | Safe (skops) model files: export, release archive, verified download, loading with a trusted-types list |
| `deploy/models.json` | Committed SHA-256 fingerprints of the released model archive and all 63 files inside it |
| `src/cardiostage/ratelimit.py` | Adds `SharedLimiter`: one limit across all visitors |
| `src/cardiostage/predictor.py` | `load_bundles()`: which model files to use where |
| `tests/test_public.py`, `tests/test_model_store.py` | 16 tests for the above |

```bash
python -m cardiostage.model_store export <release URL>   # make the safe model files + manifest
python -m cardiostage.model_store download               # fetch and verify the released files
```

---

## 1. Choosing a host: plans change, so check the facts

The plan was Hugging Face Spaces. Reading its **current** documentation showed that free accounts can no longer run Streamlit apps: they now run as "Docker Spaces", which need the paid PRO plan. Many tutorials online still say it's free, but they were written before the change.

The free alternative, **Streamlit Community Cloud**, fits well (it deploys straight from the GitHub repo and installs exactly from `uv.lock`), with trade-offs we found by reading its "Status and limitations" page:

| What Streamlit Cloud does | What we did about it |
|---|---|
| Forces `showErrorDetails = false`, which in this Streamlit version means *show tracebacks* | The app sets it back to `"none"` in code at startup (a test proves it wins) |
| Forces its own usage statistics on, and shows the owner an anonymous viewer count | Can't be switched off, so the owner decided to **accept it and disclose it** on the consent screen |
| Turns off XSRF protection | The app has no file-upload widget, which is the main thing XSRF protects here; recorded as an accepted platform limit |
| Hosts in the US; sleeps after 12 hours without visitors | Stated in the privacy notice; anyone can wake the app with one click |

> **Lesson:** platform defaults can quietly undo your security settings. Read the host's "limitations" page *before* deploying, and re-apply anything important in code, where the host can't override it.

## 2. Consent before anything else

A local app is used by its owner. A public one is used by people who might type in their *own* health information and act on the result. So before any page runs, `require_consent()` shows:
- **an educational estimate, not a diagnosis**, and *call your local emergency number* for chest pain;
- **what happens to what you type**: processed on a US server only to compute the estimate; CardioStage stores, logs and shares nothing; it never asks for identifying details;
- **what the host collects** (its usage statistics), with a link to Streamlit's privacy notice.

The **Continue** button stays disabled until the box is ticked, and `st.stop()` prevents the rest of the app from running. The same privacy text is on the About page.

### A safety net learned the hard way
The app decides which wording to show from a deployment setting (`CARDIOSTAGE_DEPLOYMENT=public`). During the first deploy that setting was accidentally skipped, so for a few minutes the **public** app showed the **local** wording ("never sent anywhere"), which was untrue. The fix is a second, independent check: if the visitor reached the app through a `*.streamlit.app` address (read from the request's `Host` header), it's public, whatever the setting says.

> **Lesson:** a missing setting should fail *safe*. Don't let the most privacy-sensitive text depend on one thing someone has to remember.

## 3. Safe model files: skops instead of pickle

Phase 10 explained the risk: model files saved with joblib are **pickles**, and loading a pickle can run code. Locally that's acceptable, because the files are ones you built. Online, the files are downloaded, so they get stronger protection.

**skops** stores models as data and loads only the types you explicitly trust. When we first converted the models, skops listed every type it found that wasn't automatically safe. Each one was reviewed and written down with a reason (`model_store.TRUSTED_TYPES`): our own two classes, numpy's data type, scikit-learn's tree, calibration and cross-validation pieces, and XGBoost's model and wrapper. If a future model contains anything else, the export **stops** rather than quietly trusting it.

### A performance surprise, solved by measuring
Converting the stage-2 bundle in one go ran for over 40 minutes without finishing. Rather than keep waiting, we measured:

| What was converted | Time |
|---|---|
| One of the 20 plausible-range copies | 5.7 s |
| Two copies in one file | more than 10 minutes (stopped) |

Converting two copies should take about 11 seconds if time grew in proportion; it didn't. So each copy now gets **its own file** (`stage2-range-07.skops` and so on), and loading puts them back together. The whole export takes **5 minutes**. All 63 files are packed into one archive, so the GitHub release needs a single upload.

> **Lesson:** when something is "just slow", measure the smallest piece. Time that grows faster than the input usually means the approach needs to change, not that you should wait longer.

### Proving nothing changed
A model in a new format is only acceptable if it gives the **same answers**. For 8 patients × 3 stages, risk, range, decision, unusual-patient flags and every explanation bar were compared: **maximum difference 0**. A permanent test (`test_skops_models_give_identical_results`) checks this whenever both formats are present.

## 4. Downloading safely

At its first start, the online app downloads `cardiostage-models.zip` (267 MB) from the `models-v1` GitHub release. `model_store.download()` is careful at every step:

```
HTTPS only ─► stop if larger than the recorded size ─► SHA-256 of the archive must match deploy/models.json
          ─► extract ONLY the file names listed in the manifest (a crafted "../x" entry can't escape)
          ─► SHA-256 of every extracted file must match ─► only then can anything be loaded
```
`deploy/models.json` is **committed to Git**, so changing what the app accepts means changing the repository. Tests cover a tampered archive, a tampered file inside a valid archive, an oversized download, plain HTTP and a path-traversal name. In every case nothing is loaded and no partial files are left behind.

## 5. One limit for everyone

The per-session rate limit (Phase 10) stops one browser tab from hammering the app, but anyone can open many tabs. The free server has about 2 CPU cores, roughly 20 heavy assessments a minute. `SharedLimiter` caps **all visitors together** at 40 a minute. Visitors run in parallel threads, so it uses a **lock**, and a test fires 200 attempts from 10 threads at once to check that exactly 50 get through when the cap is 50.

## 6. Tests that pass locally but fail in CI

After pushing, CI failed on a new test: "after consent, the Stage 1 form appears". Locally it passed. In CI there are **no trained models** (they're never in Git), so after consent the screener correctly stopped with "models not found". The test was assuming something about the environment, not testing consent. It now checks what consent actually controls (the consent screen goes away). To prove the fix, the whole suite was run locally with the model folders pointed at an empty directory: 107 passed, 14 skipped, exactly as in CI.

## 7. Check your understanding
1. Why does the app set `showErrorDetails` in Python when `.streamlit/config.toml` already says `"none"`?
2. Why is the public/local decision made from *two* signals instead of one?
3. What does skops do differently from pickle, and why does `TRUSTED_TYPES` need to be reviewed by a person?
4. Why are the 20 range copies stored as separate files?
5. The release archive is checked against a SHA-256 in `deploy/models.json`. Why must that manifest be committed to Git rather than downloaded alongside the archive?
6. Why does `SharedLimiter` need a lock when `check_and_record` didn't?
7. A test passed locally but failed in CI. What was the real cause, and why wasn't "skip it in CI" the right fix?

## Answers

**1.** Streamlit Community Cloud overrides `config.toml` with `showErrorDetails = false`, which in Streamlit 1.67 means "stacktrace": visitors would see code and file paths after a crash. The option can also be set from inside the app, which the host doesn't override, so the code wins everywhere.

**2.** So the privacy wording fails safe. If the deployment setting is forgotten (which actually happened), the `*.streamlit.app` address still marks the app as public, and visitors never see the incorrect "never sent anywhere" text.

**3.** Pickle can run arbitrary code while loading. skops stores plain data and refuses any type you haven't explicitly trusted. A person must review the list because trusting a type is a security decision: the export can only report what it found, not judge whether it's safe.

**4.** skops became extremely slow when one file held many large model copies (more than 10 minutes for two copies, versus 6 seconds for one). One file per copy keeps the conversion to about 6 seconds each, and loading reassembles them.

**5.** If the fingerprint came from the same place as the file, anyone able to replace the file could replace the fingerprint too, and the check would prove nothing. A committed manifest means the accepted fingerprints only change through the repository's history.

**6.** `check_and_record` works on one session's own list, so nothing else touches it at the same time. `SharedLimiter` holds one list used by every visitor's thread at once; without a lock, two threads could both see "39 used" and both get through, breaking the cap.

**7.** The test assumed trained models exist, which is true on your computer but never in CI. Skipping it in CI would hide a test that should run everywhere. Instead, the test was rewritten to check what consent controls, and the CI conditions were reproduced locally to confirm.
