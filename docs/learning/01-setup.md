# Phase 1: Project Setup

**Goal:** build a clean, professional skeleton *before* writing any ML code.
Recruiters open a repo and judge it in about 30 seconds. A clear structure signals that you know how real ML projects are organised.

---

## 1. The folder structure, and why each folder exists

```
├── app/                 the Streamlit web app (Phase 8)
├── data/raw/            the ORIGINAL dataset, never edited by hand
├── data/processed/      cleaned data our code creates
├── docs/learning/       these guides
├── models/              trained models saved to disk
├── reports/figures/     charts for the README and app
├── src/cardiostage/     all project logic, as an importable Python package
└── tests/               automated checks
```

**Key principles:**

- **Raw data is read-only.** We never open the CSV in Excel and "fix" things. Every cleaning step is written in code, so anyone can re-run it and get the same result. This is called *reproducibility*, and it's the most important habit in data science.
- **Logic lives in `src/`, not in notebooks or the app.** The app (Phase 8) only *calls* functions from `src/cardiostage/`. If the cleaning logic lived inside the app, we'd have to duplicate it for training, which is a common source of bugs.
- **Generated stuff is not committed.** `data/processed/` and `models/` are produced by running code. Committing them would bloat the repo and risk them going stale. The `.gitkeep` files are empty placeholders, because Git doesn't track empty folders.

## 2. The virtual environment (`.venv/`)

A virtual environment is a **private Python installation just for this project**.

Why bother? Imagine project A needs `pandas 2.0` and project B needs `pandas 3.1`. Installed globally, they'd fight. With a venv, each project has its own set of libraries.

```bash
python -m venv .venv          # create it (we did this once)
.venv\Scripts\activate        # "enter" it in a terminal (Windows)
deactivate                    # leave it
```

When activated, `python` and `pip` refer to the project's private copies. `.venv/` is in `.gitignore`, because it's large and specific to your machine. Others rebuild it from `requirements.txt`.

## 3. `requirements.txt`: the shopping list

Lists every library with an **exact version** (`pandas==3.1.1`).
Pinning matters in ML: a library update can subtly change model results, and "it worked on my machine" is never acceptable.

What each library is for:

| Library | Role |
|---|---|
| `pandas` | Tables of data (DataFrames): load, clean, filter |
| `numpy` | Fast maths on arrays; the foundation under pandas and scikit-learn |
| `scikit-learn` | The main ML toolkit: models, preprocessing, metrics, calibration |
| `xgboost` | A powerful tree-based model, often the best on spreadsheet-style data |
| `shap` | Explains *why* a model made a specific prediction |
| `joblib` | Saves trained models to files and loads them back |
| `matplotlib` / `seaborn` | Static charts |
| `plotly` | Interactive charts (for the app) |
| `streamlit` | Turns a Python script into a web app |
| `pytest` | Runs automated tests |

## 4. `pyproject.toml` and "editable install"

`pyproject.toml` declares `src/cardiostage/` as an installable package called `cardiostage`.
We installed it with `pip install -e .` (`-e` = *editable*). Two benefits:

1. **Clean imports from anywhere.** Tests, scripts and the app can all write `from cardiostage import config`, without fragile path hacks.
2. **Edits apply instantly.** Editable mode links to your source folder instead of copying it, so changes take effect without reinstalling.

The `src/` layout (code inside `src/` rather than at the root) is a recognised best practice. It guarantees you're always testing the installed package, not a stray file that happens to sit in the current folder.

## 5. `config.py`: one source of truth

Open `src/cardiostage/config.py`. It holds everything other files need to agree on:

- **Paths**, built with `pathlib.Path` relative to the file itself. This works on Windows and Mac, from any folder.
- **`RANDOM_SEED = 42`.** ML uses randomness (shuffling, random trees). A fixed seed makes every run identical, so when results change you know it's because *you* changed something, not luck. (42 is just a programmer in-joke; any number works.)
- **The target.** The raw `num` column is severity 0–4. We'll convert it to `has_disease` (1 if num > 0), because we're answering yes/no.
- **The stage feature groups: the core of the project.**

| Stage | Features | Real-world cost |
|---|---|---|
| 1. Basic | age, sex, chest-pain type, blood pressure, cholesterol, blood sugar | Clinic visit + blood test |
| 2. + Treadmill | resting ECG, max heart rate, exercise chest pain, ST depression, ST slope | ECG + supervised stress test |
| 3. + Invasive | blocked vessels on fluoroscopy, thallium scan | Hospital, dye/radiation, expensive |

Each stage *includes* the earlier ones. This one dictionary drives the whole project: when we train "the Stage 2 model", the code just looks up `STAGES[2]`.

**Why the hospital column is not a model input:** the model should judge the *patient*, not the building they walked into. We keep the column only to split data for the cross-hospital experiment.

## 6. Tests (`tests/test_setup.py`)

Run `pytest` and it executes every `test_...` function. Ours check:

- the dataset exists and has 920 rows × 16 columns (catching the wrong 303-row version),
- all 4 hospitals are present,
- every stage feature really exists in the data,
- the stages are properly nested, with 13 unique features.

Tests are a safety net: as the project grows, one command tells you nothing broke.

## 7. Git

Git records snapshots ("commits") of the project so you can see history and undo mistakes. `.gitignore` lists what Git should never track (the venv, caches, generated files).
We make **one clean commit per phase** with a clear message. A readable history is part of what recruiters see.

---

## Try it yourself

```bash
cd "D:\Unpushed Projects\Heartbeat ML"
.venv\Scripts\activate
pytest -v
python -c "from cardiostage import config; print(config.STAGES[2])"
```

## Check your understanding
1. Why do we never edit `data/raw/heart_disease_uci.csv` by hand?
2. What would go wrong if two projects shared one global Python installation?
3. Why is `thal` in Stage 3 and not Stage 1?
4. Why shouldn't the hospital name be fed into the model?

## Answers

**1. Why do we never edit `data/raw/heart_disease_uci.csv` by hand?**

Because of **reproducibility**. If you open the file in Excel and fix a few values, nobody (including future you) can tell what changed or why, and nobody can repeat it. Your results would depend on invisible manual edits.
Instead, the raw file stays exactly as downloaded, and *every* cleaning step is written as code in `src/cardiostage/`. That gives three benefits:
- **Anyone can re-run it** from the original file and get identical cleaned data.
- **Every decision is documented**, e.g. "cholesterol of 0 means missing". The code *is* the record.
- **Mistakes are fixable.** If a cleaning step turns out to be wrong, you change one line and re-run. With hand edits, the original values would be gone forever.

**2. What would go wrong if two projects shared one global Python installation?**

**Version conflicts.** There's only one copy of each library globally. Suppose an old project needs `pandas 2.0` and CardioStage needs `pandas 3.1`. Upgrading for CardioStage could silently break the old project, and downgrading would break CardioStage.
It also hurts reproducibility. A global install collects many libraries over time, so you lose track of what *this* project actually needs, and `requirements.txt` might miss something that only worked because it happened to be installed.
A virtual environment (`.venv/`) gives each project its own isolated set of libraries, and `requirements.txt` records exactly what's in it.

**3. Why is `thal` in Stage 3 and not Stage 1?**

Because of **how hard and costly the test is to get**, which is the whole idea behind CardioStage's stages.
`thal` is the result of a **thallium stress scan**: a radioactive tracer is injected and a nuclear-imaging camera shows how well blood reaches the heart muscle. It needs a hospital, specialist staff, radiation exposure and significant cost.
Stage 1 holds only what a normal clinic visit and blood test give you (age, sex, chest-pain type, blood pressure, cholesterol, blood sugar). A doctor would never order a nuclear scan first. They escalate only if the cheaper information leaves them unsure. Our stages copy that order, so we can measure whether the expensive test actually adds value.

**4. Why shouldn't the hospital name be fed into the model?**

Two reasons:
- **It isn't medical information.** A diagnosis should depend on the patient's body, not which building they walked into. In this data, the hospitals have very different disease rates (some mostly sick patients, some mostly healthy). A model given the hospital name could learn shortcuts like *"from Switzerland → probably sick"*. That's useless for a new patient at a new hospital, and it looks accurate for the wrong reason.
- **It would break the cross-hospital experiment (feature B).** We train on Cleveland and test on the other hospitals to see if the model generalises. If the hospital name were an input, the model would meet a hospital value it had never seen during training, and the test would no longer measure what we want.

So the `dataset` column is used only to **split** the data by hospital, never as a feature.
