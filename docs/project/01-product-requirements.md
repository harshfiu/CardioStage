# CardioStage: Product Requirements Document (PRD)

| | |
|---|---|
| **Product** | CardioStage: staged, calibrated, explainable heart-disease risk screening |
| **Owner** | Harsh Gupta |
| **Status** | v1.0 complete (Phases 1–9 delivered) |
| **Repository** | https://github.com/harshfiu/CardioStage |
| **Last updated** | 2026-11-23 |
| **Related docs** | [Models](02-models.md) · [Design system](03-design-system.md) · [Architecture](04-architecture.md) |

---

## 1. Summary
CardioStage estimates a patient's probability of coronary heart disease in **three stages that mirror how clinicians order tests**: a basic check-up, then a treadmill stress test, then invasive imaging. At each stage it decides whether the patient can be **cleared**, should be **referred**, or needs the **next test**. Every estimate is **calibrated**, **explained** per patient, accompanied by a **plausible range**, and **flagged** when the patient is unlike the training data.

It is a **portfolio and learning project**, not a medical device.

## 2. Background and problem
- The common "heart disease prediction" tutorial trains one classifier on all 13 UCI features, reports accuracy on a random split, and wraps it in a form. It ignores the fact that some inputs require **invasive, expensive hospital tests**, and it tests only on patients from the training hospital.
- Real cardiology is **sequential**: cheap information first, escalating only when uncertain. A useful screening aid should say *whether the next test is worth doing*.
- Medical AI must be **honest**: numbers must mean what they say, explanations must be available, and limitations, including failure on subgroups and new hospitals, must be measured and disclosed.

## 3. Goals
| ID | Goal |
|---|---|
| G1 | Model heart-disease risk at three cost-ordered stages and quantify what each test adds |
| G2 | Reduce invasive testing while matching the sensitivity of testing every patient fully |
| G3 | Produce calibrated probabilities with a stated plausible range |
| G4 | Explain every prediction in plain English |
| G5 | Warn when a patient is outside the model's experience |
| G6 | Validate on hospitals never used in training, and analyse fairness by sex and age |
| G7 | Deliver an interactive app with clear safety messaging |
| G8 | Be reproducible, tested, and documented well enough to teach ML to a beginner |

## 4. Non-goals
- Clinical use, diagnosis, or treatment recommendations for real people.
- Regulatory approval, clinical validation, or integration with hospital systems.
- Predicting disease **severity** (0–4) or **causal** effects of changing risk factors (what-if sliders); both considered and rejected (see §12).
- Cloud deployment (v1 runs locally; see §14).

## 5. Users and personas
| Persona | Need | How CardioStage serves it |
|---|---|---|
| **Portfolio reviewer / recruiter** | Judge ML skill quickly and credibly | README headline results with CIs, a clear novelty, honest limitations, tests |
| **ML learner** (incl. the owner) | Understand every step | 9 learning guides with quizzes; heavily commented code; a from-scratch model |
| **Hypothetical clinician** (demo only) | Understand a risk estimate and its basis | Calibrated risk, range, explanation, next-step suggestion, unusual-patient warning |
| **Technical interviewer** | Probe depth of understanding | Nested CV, external validation, exact CIs, calibration analysis, fairness case study |

## 6. User stories
| ID | As a… | I want to… | So that… |
|---|---|---|---|
| US1 | demo user | enter basic check-up details and get a risk estimate | I know whether further testing is suggested |
| US2 | demo user | add treadmill, then imaging results step by step | the estimate updates as information arrives |
| US3 | demo user | see why the estimate is what it is | I can judge whether it's reasonable |
| US4 | demo user | be told when a patient is unusual | I don't over-trust an extrapolation |
| US5 | demo user | leave a measurement as "not measured" | real-world gaps don't block me |
| US6 | demo user | load example patients | I can explore without inventing values |
| US7 | reviewer | see evidence for every claim | I can trust the results |
| US8 | developer | rebuild all models with one command | the project is reproducible after cloning |
| US9 | learner | read a guide per phase | I understand what was done and why |

## 7. Functional requirements
### 7.1 Screening logic
| ID | Requirement | Status |
|---|---|---|
| FR1 | Three stage models using the feature groups in [Models §3](02-models.md#3-features-and-stages) | ✅ |
| FR2 | Stages 1–2 return one of **low** (clear), **high** (refer), **uncertain** (next test) using rule-out / rule-in thresholds | ✅ |
| FR3 | Stage 3 returns **refer** / **clear** using a screening threshold targeting **97% recall** | ✅ |
| FR4 | Rule-out threshold keeps ≥ **99%** of sick training patients above it; rule-in requires ≥ **90%** precision | ✅ |
| FR5 | Probabilities are calibrated where calibration improves the Brier score | ✅ |
| FR6 | Each assessment includes a plausible range (10th–90th percentile of 20 subsample models) | ✅ |
| FR7 | The plausible range is **display-only**: it never changes decisions (`USE_UNCERTAINTY_GUARD = False`) | ✅ |
| FR8 | An unusual-patient check gives human-readable reasons (range violations, unusual combinations) | ✅ |
| FR9 | Every assessment includes a SHAP explanation in percentage points that sums exactly to the risk | ✅ |
| FR10 | Missing inputs are allowed, imputed with training medians/modes, and disclosed | ✅ |
| FR11 | Invalid categorical values are rejected with an error | ✅ |

### 7.2 App
| ID | Requirement | Status |
|---|---|---|
| FR12 | Screener page with stage forms, a result card per stage, and the next stage's form shown as "recommended" when uncertain, otherwise optional | ✅ |
| FR13 | Re-submitting a stage clears results of later stages | ✅ |
| FR14 | Four example patients: low, uncertain-then-cleared, high, and a labelled **known limitation** | ✅ |
| FR15 | Results page presenting evidence (sealed test, staged policy, calibration, external, fairness, explanations) | ✅ |
| FR16 | About page with method, data and limitations | ✅ |
| FR17 | Disclaimer on every page | ✅ |
| FR18 | Help tooltips explaining every medical input in plain English | ✅ |

### 7.3 Pipeline and evaluation
| ID | Requirement | Status |
|---|---|---|
| FR19 | One command rebuilds all deployable models (`python -m cardiostage.train_all`) | ✅ |
| FR20 | Sealed 20% Cleveland test set, fixed by seed, used once at the end | ✅ |
| FR21 | Nested cross-validation for model selection | ✅ |
| FR22 | External validation at Hungary, Switzerland, VA Long Beach (stages 1–2) | ✅ |
| FR23 | Fairness analysis by sex and age band with confidence intervals | ✅ |
| FR24 | All reported proportions and AUCs carry 95% confidence intervals | ✅ |

## 8. Non-functional requirements
| ID | Category | Requirement | Achieved |
|---|---|---|---|
| NFR1 | Performance | Assessment with explanation ≤ 5 s per stage on a laptop | ~0.3 s (stage 1), ~3–5 s (stages 2–3) |
| NFR2 | Performance | Model loading cached; once per server process | ~15 s first load, then instant |
| NFR3 | Privacy | No patient data leaves the machine; no network calls at inference | ✅ fully local |
| NFR4 | Reproducibility | Fixed seeds; pinned dependency versions; same split every run | ✅ `RANDOM_SEED = 42`, `requirements.txt` pinned |
| NFR5 | Quality | Automated tests for data, models, thresholds, uncertainty, explanations, predictor and app flow | ✅ 59 tests |
| NFR6 | Quality | Lint-clean code (`ruff check`) and consistent formatting (`ruff format`) | ✅ |
| NFR7 | Accessibility | Colour never the only signal; colour-blind-safe palette; text labels on all status boxes | ✅ see [Design system](03-design-system.md) |
| NFR8 | Portability | Python ≥ 3.10; Windows / macOS / Linux paths via `pathlib` | ✅ (built on Python 3.12, Windows) |
| NFR9 | Documentation | Code commented for beginners; a learning guide per phase; these four project docs kept current | ✅ |

## 9. Safety and ethics requirements
| ID | Requirement |
|---|---|
| S1 | Never state or imply a diagnosis; use "estimated risk" and "referral is suggested" |
| S2 | Disclaimer: educational, not a medical device, contact a doctor or emergency services for symptoms |
| S3 | Explanations must state they describe the model, not causes of disease |
| S4 | Known limitations shown in-app (About page; the limitation example with an explanatory note) |
| S5 | Prioritise sensitivity: missed sick patients are treated as the costliest error (97% recall target) |
| S6 | No subgroup "fix" may be fitted to a handful of patients; small-sample findings are documented, not patched |

## 10. Success metrics
| Metric | Target | Result |
|---|---|---|
| Staged-policy recall (CV) | ≈ all-tests recall, ≥ 95% | 0.964 vs 0.973 (diff −0.009 [−0.029, 0.000]) |
| Invasive tests saved (CV) | ≥ 25% | **40%** [33%, 46%] |
| Sealed-test sick patients missed | minimal | **0 of 28** (recall 1.000 [0.877, 1.000]) |
| Sealed-test invasive tests needed | < 100% | **49%** |
| Stage 3 ROC-AUC (CV / test) | ≥ 0.85 | 0.900 / 0.960 [0.902, 0.996] |
| Calibration error (pooled ECE) | ≤ 0.06 | 0.031–0.047 (chosen variants) |
| External AUC (Hungary, stage 2) | within CI of internal | 0.892 [0.848, 0.932] |
| Medical direction sanity checks | 100% | 12 / 12 |

## 11. Constraints and assumptions
- **Data:** UCI Heart Disease (920 patients, 4 hospitals, 1980s). Only Cleveland has near-complete stage-3 data, so **all models train on Cleveland** (243 training patients).
- **Target:** angiographic disease (`num > 0`, i.e. >50% narrowing of a major vessel) is assumed to be ground truth.
- **Population:** patients already referred for cardiac testing; conclusions don't transfer to the general public.
- **Compute:** a laptop CPU suffices; GPUs/epochs give no benefit at this data size.

## 12. Decision log (owner decisions)
| Date | Decision | Rationale |
|---|---|---|
| 2026-11-22 | Purpose: portfolio/resume; 1–2 weeks; local only | Owner's goals |
| 2026-11-22 | Novelty: staged screening (headline) + external validation + SHAP + calibration/"not sure" + fairness | Distinct from tutorial copies; clinically motivated |
| 2026-11-22 | Rejected: severity prediction, what-if sliders | Too few severe cases; sliders would imply causation |
| 2026-11-22 | Models: LR baseline vs RF vs XGBoost | Covers linear, bagging, boosting |
| 2026-11-22 | Comments + learning guide per phase; step-by-step build; venv + Git | Owner is new to ML |
| 2026-11-23 | Repo name **CardioStage**; local folder keeps its name | Owner's choice |
| 2026-11-23 | Train all stages on **Cleveland only** | Only hospital with stage-3 data; fair stage comparison |
| 2026-11-23 | Push to GitHub after every phase | Owner's choice |
| 2026-11-23 | Add from-scratch logistic regression | Learning value |
| 2026-11-23 | Screening target **97% recall** (rule-out 99%) | Minimise missed patients |
| 2026-11-23 | Uncertainty range **display-only** | Proved a weak error detector |
| 2026-11-23 | **MIT** licence | Portfolio-friendly |
| 2026-11-23 | Maintain these four project docs with every change | Owner's request |

## 13. Risks and mitigations
| Risk | Mitigation |
|---|---|
| Users mistake it for medical advice | Disclaimers everywhere; non-diagnostic wording; About page limitations |
| Over-optimistic metrics | Sealed test set; nested CV; CIs on everything; external validation |
| Silent subgroup failure | Fairness analysis; case study; labelled limitation example |
| Thresholds don't transfer | Documented (Hungary NPV 90% vs 96%); "re-validate locally" stated |
| Unusual inputs | Novelty detector with reasons |
| Model files missing after clone | `train_all`; app shows a clear error; tests skip with a hint |

## 14. Out of scope for v1 / future work
- Cloud deployment (Streamlit Community Cloud or Hugging Face Spaces); model files (~85 MB per stage) would need Git LFS or a release asset.
- Local recalibration UI (prior shift with a site's disease rate).
- Larger, modern datasets; stage-3 external validation.
- Monitoring of atypical presentations in women with more data.

## 15. Release status
| Phase | Deliverable | Status |
|---|---|---|
| 1 | Project setup | ✅ |
| 2 | Data exploration & cleaning | ✅ |
| 3 | Baseline models + from-scratch LR | ✅ |
| 4 | Staged screening | ✅ |
| 5 | Calibration, uncertainty, novelty | ✅ |
| 6 | External validation & fairness | ✅ |
| 7 | SHAP explanations | ✅ |
| 8 | Streamlit app | ✅ |
| 9 | Sealed test evaluation & polish | ✅ |

## Changelog
| Date | Change |
|---|---|
| 2026-11-23 | Document created at v1.0 completion (all 9 phases) |
