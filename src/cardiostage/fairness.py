"""
Phase 6b: does CardioStage work equally well for everyone?

A model can look good on average while failing a subgroup, especially one
that's under-represented in training. Here women are ~1/3 of Cleveland's
patients, and heart disease in women is known to be under-diagnosed,
partly because their symptoms are more often "atypical".

We compare groups by SEX and AGE on:
  - ranking quality (ROC-AUC) at stages 1 and 3
  - the full staged policy: recall (sick caught), specificity, missed patients
  - honesty: average predicted risk vs actual disease rate
  - cost: how many patients in each group needed invasive tests

Data: Cleveland out-of-fold predictions (honest, unseen) plus, for stages
1-2, all external-hospital patients.

Every number comes with a 95% bootstrap CI: subgroups are small (e.g. ~20
sick women), so differences that look large can easily be chance.

Run:  python -m cardiostage.fairness
"""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from cardiostage import config, integrity
from cardiostage.data import get_features_and_target, load_clean, split_cleveland
from cardiostage.staging import simulate_policy
from cardiostage.stats import bootstrap_ci, fmt_ci

TEXT = "#52514e"


def age_band(age):
    return pd.cut(age, bins=[0, 49, 59, 200], labels=["under 50", "50-59", "60+"])


def recall(y, d):
    sick = y == 1
    return d[sick].mean() if sick.any() else np.nan


def specificity(y, d):
    healthy = y == 0
    return (1 - d[healthy]).mean() if healthy.any() else np.nan


def group_metrics(y, p1, p3, decision, reached) -> dict:
    auc1 = bootstrap_ci(roc_auc_score, y, p1, need_both_classes=True)
    auc3 = bootstrap_ci(roc_auc_score, y, p3, need_both_classes=True)
    rec = bootstrap_ci(recall, y, decision)
    spec = bootstrap_ci(specificity, y, decision)
    return {
        "n": len(y),
        "n_sick": int(y.sum()),
        "disease_rate": y.mean(),
        "auc_stage1": fmt_ci(*auc1),
        "auc_stage3": fmt_ci(*auc3),
        "policy_recall": fmt_ci(*rec),
        "policy_specificity": fmt_ci(*spec),
        "missed_sick": int(((decision == 0) & (y == 1)).sum()),
        "mean_predicted_stage3": p3.mean(),
        "needed_invasive": (reached == 3).mean(),
        "_recall": rec,
        "_spec": spec,
    }


def plot_fairness(table: pd.DataFrame):
    fig, axes = plt.subplots(1, 2, figsize=(12, 3.6), sharey=True)
    fig.subplots_adjust(wspace=0.08)
    labels = list(table.index)
    for ax, col, title in [
        (axes[0], "_recall", "Recall: sick patients caught"),
        (axes[1], "_spec", "Specificity: healthy patients cleared"),
    ]:
        for i, label in enumerate(labels):
            est, lo, hi = table.loc[label, col]
            color = "#2a78d6" if label.startswith("Sex") else "#eb6834"
            if label == "All patients":
                color = "#52514e"
            ax.errorbar(
                est,
                i,
                xerr=[[est - lo], [hi - est]],
                fmt="o",
                color=color,
                markersize=9,
                capsize=4,
                linewidth=2,
            )
            ax.text(hi + 0.015, i, f"{est:.2f}", va="center", color=TEXT, fontsize=9)
        ax.set_title(title, fontweight="bold")
        ax.set_xlim(0, 1.1)
        ax.grid(axis="x", color="#ebeae6")
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    n_text = [
        f"{label}  (n={table.loc[label, 'n']}, sick={table.loc[label, 'n_sick']})"
        for label in labels
    ]
    axes[0].set_yticks(range(len(labels)), n_text)
    axes[0].set_ylim(len(labels) - 0.5, -0.5)
    fig.suptitle(
        "Fairness: staged policy performance by group (Cleveland out-of-fold, 95% CI)",
        fontweight="bold",
        y=1.03,
    )
    path = config.FIGURES_DIR / "14_fairness.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {path.relative_to(config.PROJECT_ROOT)}")


def main():
    df = load_clean()
    train, _sealed_test = split_cleveland(df)
    saved = integrity.load(config.MODELS_DIR / "phase5_oof.joblib")
    y = saved["y"]
    p = {s: saved["oof"][s][saved["method"][s]].mean(axis=0) for s in config.STAGES}
    with open(config.REPORTS_DIR / "phase5_zones.json") as f:
        zones = {int(s): z for s, z in json.load(f)["zones"].items()}
    decision, reached = simulate_policy(p, zones)

    # The out-of-fold arrays follow the row order of the training DataFrame.
    groups = {"All patients": np.ones(len(y), dtype=bool)}
    sex = train["sex"].to_numpy()
    groups["Sex: female"] = sex == 0
    groups["Sex: male"] = sex == 1
    ages = age_band(train["age"]).astype(str).to_numpy()
    for band in ["under 50", "50-59", "60+"]:
        groups[f"Age: {band}"] = ages == band

    rows = {
        name: group_metrics(y[m], p[1][m], p[3][m], decision[m], reached[m])
        for name, m in groups.items()
    }
    table = pd.DataFrame(rows).T
    public = [c for c in table.columns if not c.startswith("_")]
    table[public].to_csv(config.REPORTS_DIR / "phase6_fairness.csv")
    pd.set_option("display.width", 250, "display.max_columns", 30)
    print("Cleveland, out-of-fold, full staged policy:\n")
    print(table[public].to_string())

    # External hospitals pooled, stages 1-2, by sex.
    ext = df[df[config.HOSPITAL_COLUMN].isin(config.EXTERNAL_HOSPITALS)]
    ext_rows = []
    for stage in (1, 2):
        bundle = integrity.load(config.MODELS_DIR / f"stage{stage}.joblib")
        X, y_ext = get_features_and_target(ext, stage)
        p_ext = bundle["model"].predict_proba(X)[:, 1]
        for label, value in [("female", 0.0), ("male", 1.0)]:
            m = (ext["sex"] == value).to_numpy()
            auc = bootstrap_ci(roc_auc_score, y_ext.to_numpy()[m], p_ext[m], need_both_classes=True)
            ext_rows.append(
                {
                    "stage": stage,
                    "sex": label,
                    "n": int(m.sum()),
                    "n_sick": int(y_ext.to_numpy()[m].sum()),
                    "roc_auc": fmt_ci(*auc),
                }
            )
    ext_table = pd.DataFrame(ext_rows)
    ext_table.to_csv(config.REPORTS_DIR / "phase6_fairness_external.csv", index=False)
    print("\nExternal hospitals pooled, by sex:\n", ext_table.to_string(index=False))

    plot_fairness(table)


if __name__ == "__main__":
    main()
