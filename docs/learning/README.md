# CardioStage Learning Guides

A step-by-step record of how CardioStage was built, written for someone starting out in machine learning. Each guide explains **what** was done, **why**, the mistakes caught along the way, and ends with questions and answers.

| # | Guide | You'll learn |
|---|---|---|
| 1 | [Project setup](01-setup.md) | Repo structure, virtual environments, packaging, config, tests, Git |
| 2 | [Data exploration & cleaning](02-data.md) | The medical columns in plain English, fixing bad data, **data leakage** |
| 3 | [Baseline models](03-models.md) | Sealed test sets, cross-validation, **nested CV**, 3 model types, metrics, logistic regression **from scratch** |
| 4 | [Staged screening](04-staging.md) | Out-of-fold predictions, ROC curves, decision thresholds, bootstrapping, why epochs/GPUs don't help small data |
| 5 | [Honest probabilities](05-calibration.md) | Calibration, Brier score, uncertainty ranges, unusual-patient detection, **noisy metrics** |
| 6 | [New hospitals & fairness](06-external-and-fairness.md) | External validation, dataset shift, prior shift, subgroup analysis, when *not* to "fix" |
| 7 | [Explanations](07-explanations.md) | SHAP and Shapley values, global vs local explanations, sanity-checking a model |
| 8 | [The app](08-app.md) | Separating logic from UI, Streamlit's rerun model, caching, testing an app |
| 9 | [Final evaluation & polish](09-final.md) | Opening the sealed test set, exact confidence intervals, linting, presenting ML work |
| 10 | [Security hardening](10-security.md) | Threat models, honest severity ratings, localhost binding, pickle safety (SHA-256), input validation, rate limiting, supply chain |
| 11 | [The website & the redesign](11-website-and-design.md) | Static sites, Lenis/GSAP/Vanta, never hand-typing a statistic, measured contrast, Content-Security-Policy, Plotly charts, a failing test that revealed a real subtlety |
| 12 | [Locking the supply chain](12-supply-chain.md) | Version pins vs checksums, `uv` lockfiles, generated vs hand-edited files, pinning CI actions to commits |
| 13 | [Going online](13-going-online.md) | Choosing a host from current facts, consent screens, failing safe, skops vs pickle, measuring a slowdown, verified downloads, shared rate limits, CI-only failures |

**Suggested reading order:** in sequence. Each guide builds on the previous ones. Every guide lists the files it covers and the commands to reproduce its results.
