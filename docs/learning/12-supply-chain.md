# Phase 12: Locking the Supply Chain

**Goal:** make sure every computer that installs CardioStage (yours, GitHub's CI, and soon a Hugging Face server) gets **exactly** the code we tested, byte for byte, and that the CI's own tools can't be swapped out underneath us.

This closes security finding **SEC-07** from [Phase 10](10-security.md), which was "partly remediated" because two gaps remained: no checksums, and GitHub Actions referenced by movable tags.

**Files in this phase**

| File | Job |
|---|---|
| `pyproject.toml` | The human-edited list: direct dependencies pinned with `==`, dev tools in a `dev` group |
| `uv.lock` | Generated: **every** package (79) with its exact version and the SHA-256 checksum of every file, for every platform |
| `requirements.txt` | Generated from `uv.lock` with `--hash` lines, for people (and hosting platforms) that use plain `pip` |
| `.github/workflows/ci.yml`, `pages.yml` | Install with `uv sync --locked`; every action pinned to a commit SHA |
| `.github/dependabot.yml` | Weekly update PRs for uv packages and for the pinned actions |

```bash
uv sync                         # build .venv exactly from uv.lock
uv run pytest                   # run anything inside that environment
uv lock --check                 # is uv.lock up to date with pyproject.toml?
```

---

## 1. What "supply chain" means

You wrote maybe 5,000 lines of Python. When the app runs, it uses **79 packages** written by thousands of other people: pandas, scikit-learn, Streamlit, and everything *they* depend on. That chain of other people's code is the **software supply chain**. If any link is replaced by something malicious, it runs with the same power as your own code.

Two kinds of attack matter here:
- **A bad new version:** someone publishes `somepackage 2.0.1` containing malware. *Defence:* pin exact versions, so you never pick up a new release without choosing to.
- **A bad file with the same version number:** the download is swapped, mirrored badly or corrupted. The version still says `2.0.0`, but the bytes differ. *Defence:* **checksums**.

## 2. Versions vs checksums

A **version pin** (`pandas==3.1.1`) says *which release* to install. A **checksum** (a SHA-256 hash, the same tool as the model fingerprints in Phase 10) says *which exact bytes*:

```
pandas==3.1.1 \
    --hash=sha256:59bb0325…    ← the Windows wheel
    --hash=sha256:c66ae634…    ← the Linux wheel
```
When `pip --require-hashes` or `uv` downloads a file, it computes the SHA-256 and **refuses to install** if it doesn't match one recorded in the lock. Change one byte and the hash is completely different.

Phase 10 had version pins only (`constraints.txt`). Phase 12 adds checksums for every file.

## 3. Why `uv`, and what each file does

`uv` is a fast Python package manager that can **lock** a project: resolve every dependency once and write the result, with checksums for *all* platforms, into one file.

```
pyproject.toml   (you edit)     "pandas==3.1.1", "streamlit==1.67.0", …      ~13 lines
      │  uv lock
      ▼
uv.lock          (generated)    79 packages × exact version × file checksums, every OS
      │  uv export
      ▼
requirements.txt (generated)    same, in pip's format, with --hash lines
```
- **You only ever edit `pyproject.toml`.** The other two are generated: never hand-edit them.
- `uv sync` builds `.venv/` to match the lock **exactly**, adding missing packages and removing extra ones.
- `requirements.txt` exists for anyone without uv, and because Hugging Face Spaces (item 5) installs from it.

### Not changing anything by accident
A lock that silently upgraded scipy could change model results (it's used inside scikit-learn and for our exact confidence intervals). So the first lock was created **against the tested versions** from `constraints.txt`. A script then compared all 76: **zero differences**. Re-locking without the constraints kept the same versions, because `uv lock` prefers what's already locked. The full test suite, including the 13 tests that use the trained models, passed unchanged.

Two packages appeared that pip on Windows never installed: `nvidia-nccl-cu13`, which XGBoost needs **only on Linux**, and `pip` itself, which pip-audit uses. The lock covers every platform, so it records platform-specific packages too.

### A side effect worth noticing
The project used to say `requires-python = ">=3.10"`. But pandas 3.1 and numpy 2.5 need Python 3.11 or newer, so that claim was **false** and nobody noticed, because nothing ever tried 3.10. Locking forces the resolver to check every Python version you claim to support. It's now `">=3.12"`, the version actually tested. (Ruff then also knew `tomllib` is part of the standard library and re-sorted one import.)

## 4. Pinning GitHub Actions to commits

CI steps like `uses: actions/checkout@v7` run **someone else's code** with access to your repository. `v7` is a Git **tag**, and tags can be moved to point at different code later. If an action's repository were compromised, the attacker could re-point `v7` to malicious code, and every project using `@v7` would run it on the next push.

A **commit SHA** can't be moved: it's a fingerprint of the exact code. So every action is now pinned like this:

```yaml
- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
```
The comment keeps it readable, and Dependabot understands this format: it updates the SHA and the comment together.

**How the SHAs were found:** `git ls-remote --tags https://github.com/actions/checkout` lists every tag and its commit, straight from the official repository. Some tags are *annotated* (they point to a tag object, not a commit). For those, the line ending in `^{}` gives the actual commit, and that's the one to use.

## 5. CI now checks the chain

```yaml
- run: uv sync --locked          # fails if uv.lock is out of date with pyproject.toml
- run: diff requirements.txt <fresh export>   # fails if requirements.txt drifted from the lock
- run: uv run pip-audit --skip-editable       # known vulnerabilities in any installed package
```
The middle check matters because `requirements.txt` is generated: if someone updates the lock but forgets to regenerate it, pip users and Hugging Face would install something different from what CI tested. Now that mistake fails the build.

## 6. What's still not covered (honestly)

The website's JavaScript libraries (GSAP, Lenis, three.js, Vanta) are **vendored**: copied into `site/vendor/`. Neither Dependabot nor pip-audit looks at them. They were checksum-verified when downloaded, but updates are manual. This is documented as the remaining residual risk of SEC-07.

## 7. Check your understanding
1. What's the difference between pinning `pandas==3.1.1` and recording its SHA-256 checksum? Which attack does each one stop?
2. Which of `pyproject.toml`, `uv.lock` and `requirements.txt` should you edit by hand, and why only that one?
3. Why was the first lock created against the old `constraints.txt` versions instead of just "the latest"?
4. Why can a tag like `@v7` be dangerous in a CI workflow, when a commit SHA isn't?
5. The lock contains `nvidia-nccl-cu13`, which was never installed on your Windows machine. Is that a problem?
6. How did locking reveal that `requires-python = ">=3.10"` was wrong?

## Answers

**1.** The version pin chooses *which release* (it stops you picking up a new, possibly malicious version). The checksum fixes *which exact bytes* (it stops a swapped or corrupted file that still claims to be 3.1.1). You need both.

**2.** Only `pyproject.toml`. The other two are generated from it (`uv lock`, then `uv export`). Hand edits would be overwritten, and could make the files disagree, which CI now catches.

**3.** To avoid changing behaviour by accident. Indirect dependencies like scipy affect numeric results; the models, thresholds and every reported number were produced with specific versions. Locking those same versions, then checking all 76 matched, kept the project's results identical.

**4.** A tag is a movable label: whoever controls the action's repository can point `v7` at new code, and your CI would run it without any change on your side. A commit SHA is a fingerprint of specific code and can't be re-pointed.

**5.** No. The lock covers every platform, and XGBoost needs that package only on Linux. On Windows it's skipped; on Linux (CI, or a Linux server) it's installed, with its checksum checked like everything else.

**6.** To lock, the resolver must find versions that work on *every* Python the project claims to support. pandas 3.1 and numpy 2.5 don't support 3.10, so the claim couldn't be satisfied. It had never been noticed because nobody had tried installing on 3.10.
