# Phase 8: The Streamlit App

**Goal:** turn seven phases of models, thresholds, calibration, uncertainty and explanations into something a person can actually use.

**Files in this phase**

| File | Job |
|---|---|
| `src/cardiostage/predictor.py` | **The decision engine**: risk, range, zone, warnings, explanation, recommendation. No UI code |
| `src/cardiostage/train_all.py` | Rebuilds every model from scratch in the right order |
| `app/streamlit_app.py` | Entry point: page navigation |
| `app/views/screener.py` | The staged screening flow |
| `app/views/results.py` | Evidence page: the project's key results and charts |
| `app/views/about.py` | Method, data, limitations |
| `app/ui.py` | Shared pieces: model loading, result card, explanation chart, disclaimer |
| `.streamlit/config.toml` | Colours and settings |
| `tests/test_predictor.py` | 7 checks, including a full automated run through the real app |

```bash
python -m cardiostage.train_all      # once, after cloning (~10 min): builds models/
streamlit run app/streamlit_app.py   # opens http://localhost:8501
```

---

## 1. Architecture: keep logic out of the UI

The most important design decision in this phase:

```
  Streamlit pages (app/)          <- only: collect inputs, show outputs
          │
          ▼
  CardioStagePredictor            <- all decisions: risk, zone, warnings, explanation
  (src/cardiostage/predictor.py)
          │
          ▼
  models/stage{1,2,3}.joblib      <- trained in Phases 4-5
```

**Why separate them?**
- **Testable:** the predictor is plain Python, so `pytest` checks it directly (zones follow thresholds, explanations add up, bad inputs are rejected), with no browser needed.
- **Reusable:** the same engine could power an API or a command-line tool without touching the logic.
- **Readable:** the Streamlit files read like a description of the screen, not a tangle of maths.

A common beginner mistake is putting model loading, preprocessing and decision rules inside the app script. It works until you need to test or change something.

## 2. What one assessment contains

`predictor.assess(patient, stage)` returns an `Assessment`:

| Field | Example | From phase |
|---|---|---|
| `risk` | 0.33 | 4–5 (calibrated stage model) |
| `range_low`, `range_high` | 0.28 – 0.39 | 5 (20 model copies) |
| `zone` | `"uncertain"` | 4 (decision zones) |
| `headline`, `recommendation` | "Uncertain … Suggested next step: a treadmill test" | 4 |
| `unusual` | ["chol = 590 is outside the training range (126 to 564)"] | 5 (novelty detector) |
| `not_measured` | ["fbs"] | 2 (imputation) |
| `explanation`, `summary` | "+14 pts: blocked vessels = 2 …" | 7 (SHAP) |

A `@dataclass` is a Python class that mainly holds data. You list the fields and Python writes the boilerplate (constructor, printing) for you.

## 3. Streamlit in 5 ideas

1. **The script reruns top to bottom on every interaction.** Click a button, and Streamlit runs the whole file again. That's what makes it simple, and why we need the next two ideas.
2. **`st.session_state` remembers things between reruns.** Each patient's inputs and stage results live there, so they survive every click.
3. **`@st.cache_resource` loads expensive things once.** The 3 model bundles take ~15 seconds to load (each holds 20 uncertainty copies). Cached, that happens once per server, not on every click.
4. **`st.form` batches inputs.** Without a form, every keystroke in a number box would rerun the app and re-predict. With one, nothing happens until "Assess risk" is pressed.
5. **Widgets with `key=` read and write session state.** That's how "Try an example" fills the form: a callback writes the example's values into `st.session_state`, and the widgets display them.

**One bug worth understanding:** the stage results are displayed in a loop, and a later stage's form is drawn *inside* that loop. Submitting it replaces `st.session_state.results` with a new dictionary, but the loop was still holding the old one, so the new result wouldn't show until the next click. The fix: read `st.session_state.results` fresh on each pass. Stale references are a classic source of "it updates one click late" bugs.

## 4. The screening flow

1. **Stage 1 form**: age, sex, chest pain type, blood pressure, cholesterol (or "not measured"), blood sugar.
2. **Result card**: risk, plausible range, coloured decision box, threshold caption, unusual-patient warning, plain-English explanation, contribution chart, full breakdown.
3. If the zone is **uncertain**, the next stage's form appears under "Recommended next step". Otherwise it's tucked into an optional "add results anyway" expander, so the app never hides information but makes the recommended path obvious.
4. Re-submitting an earlier stage clears later results, because they were based on old inputs.

## 5. Design choices for a medical tool
- **Disclaimer everywhere**: on the screener, the sidebar, and every page.
- **Plain English**: every input has a help tooltip ("Normal is about 120; 140 or above is high"), and chest-pain types are described, not just named.
- **"Not measured" is allowed**: real patients have gaps. The model fills them with typical values and the app says so.
- **Honest wording**: "Referral to a cardiologist is suggested", never "you have heart disease". The uncertainty range is labelled "for transparency only", as decided in Phase 5.
- **Explanations carry their caveat**: "these describe what drove the model, not what causes disease."

### The example patients
| Example | Stage 1 | Stage 2 | Stage 3 |
|---|---|---|---|
| Low risk (42-year-old woman) | 2% low | 9% low | 6% clear |
| **Uncertain, then cleared** (54-year-old man) | 33% uncertain | 15% uncertain | **8% clear** |
| High risk (63-year-old man) | 92% high | 91% high | 94% refer |
| **Known limitation** (57-year-old woman, atypical pain) | 8% **low (cleared)** | 17% uncertain | **25% refer** |

The "uncertain" example was **checked, not assumed**. My first candidate turned out to be cleared at stage 1, reproducing the Phase 6 limitation. Rather than hide that, it became a fourth, clearly labelled example, with a sidebar note explaining the weakness. Showing a tool's failure modes builds more trust than hiding them.

## 6. Testing the app itself
`streamlit.testing.v1.AppTest` runs the real app without a browser. Our test selects the "uncertain, then cleared" example and clicks through all three stages, checking each zone (uncertain → uncertain → clear) and that no errors occur.

My first version clicked `button[1]` expecting "Assess risk", but in the test harness the form's button comes first, so it clicked **Reset** and wiped the inputs. Fix: find buttons by their label. **Lesson:** avoid relying on positions (index 0, 1, …) in UI tests; select elements by something meaningful.

The model-dependent tests are **skipped, not failed**, when `models/` is missing (models aren't in Git), with a message saying to run `train_all`.

## 7. Check your understanding
1. Why does the app keep decision logic in `predictor.py` rather than in the Streamlit file?
2. What would happen without `@st.cache_resource` on model loading?
3. Why use `st.form` for the inputs?
4. Why was the "known limitation" example kept instead of replaced?
5. Why do the predictor tests skip, rather than fail, when models are missing?

## Answers

**1.** So the logic can be tested without a browser, reused by other interfaces, and read and changed without UI code in the way. The Streamlit files only collect inputs and display outputs.

**2.** Streamlit reruns the script on every interaction, so the ~15-second model load would happen on every click, making the app unusable.

**3.** Without a form, changing any input reruns the whole script and recomputes predictions and SHAP explanations for half-finished inputs. A form waits until the user presses the button, so there's one computation per deliberate submission.

**4.** It honestly demonstrates a real, documented weakness (Phase 6): atypical presentations in women can be cleared too early. Hiding it would make the demo look better than the tool is. Showing it with an explanation lets users understand when not to trust the result.

**5.** Trained models are generated files kept out of Git. On a fresh clone they don't exist yet, which isn't a code bug. Skipping with a clear hint ("run python -m cardiostage.train_all") distinguishes "not set up yet" from "broken".
