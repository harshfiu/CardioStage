# CardioStage Project Documents

The authoritative reference for what CardioStage is, how its models work, how it looks, and how it's built.

| Document | Answers |
|---|---|
| [01 · Product requirements (PRD)](01-product-requirements.md) | What and why: goals, users, requirements, success metrics, safety rules, decision log, risks |
| [02 · Models](02-models.md) | Data, cleaning, features, candidate and final models, hyperparameters, calibration, thresholds, uncertainty, explanations, every performance number, artefacts, reproduction |
| [03 · Design system](03-design-system.md) | Colours, chart rules, figure inventory, app layout, components, content and voice, accessibility |
| [04 · Architecture](04-architecture.md) | System overview, modules and dependencies, data and runtime flows, caching, configuration, testing, ADRs, technical debt |

For a beginner-friendly, step-by-step account of how the project was built, see [`docs/learning/`](../learning/README.md).

## Maintenance rule
These are **living documents**. Every change to CardioStage (code, models, thresholds, data handling, UI, dependencies or decisions) must update the affected document(s) **in the same commit**, including the "Last updated" date and a changelog entry.

| If you change… | Update |
|---|---|
| Goals, scope, requirements, decisions | PRD |
| Data handling, features, models, tuning, calibration, thresholds, metrics | Models |
| Colours, charts, app screens, wording | Design system |
| Modules, files, data flow, tooling, dependencies, tests | Architecture |
