"""
v2.0 final exam: the sealed test set, opened once.

Written and committed BEFORE the sealed test was opened, so the results
can't influence what is measured. Nothing here is tuned: every model, zone
and threshold is frozen from training.

Sealed test (pooled.split_v2): 245 patients. Cleveland's 61 are v1's test
patients (v2 reuses v1's stage-2/3 models, trained on the other 243); every
other hospital contributes a fresh 20%.

What is compared (v1 vs v2, same patients):
  A. Stage 1 at each hospital and overall: ranking quality (AUC, bootstrap
     95% CI), calibration (ECE, mean predicted vs actual), and the clear
     zone's safety: share cleared, sick patients wrongly cleared, and
     "sick not cleared" (stage-1 safety) with an exact 95% CI.
  B. Typical angina: actual disease rate vs each model's mean prediction.
  C. The full 3-stage policy on Cleveland's 61 (the only hospital with all
     three stages): sick missed, recall (exact CI), specificity, share
     needing invasive tests. v2 = v2 stage 1 + v1 stages 2-3.

Run (needs the trained models, incl. models/v1_stage1.joblib):
    python -m cardiostage.v2_final
"""

import json

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from cardiostage import config, integrity
from cardiostage.calibration import expected_calibration_error
from cardiostage.pooled import STAGE_HOSPITALS, load_pooled, split_v2
from cardiostage.staging import simulate_policy
from cardiostage.stats import bootstrap_ci, exact_proportion_ci, fmt_ci
from cardiostage.thresholds import decision_metrics

VERSIONS = ("v1", "v2")


def load_stage1() -> dict:
    return {
        "v1": integrity.load(config.MODELS_DIR / "v1_stage1.joblib"),
        "v2": integrity.load(config.MODELS_DIR / "stage1.joblib"),
    }


def stage1_rows(test: pd.DataFrame, bundles: dict) -> pd.DataFrame:
    rows = []
    groups = [(h, test[config.HOSPITAL_COLUMN] == h) for h in STAGE_HOSPITALS[1]]
    groups.append(("All hospitals", pd.Series(True, index=test.index)))
    for name, mask in groups:
        part = test[mask]
        y = part[config.TARGET_COLUMN].to_numpy()
        X = part[config.STAGES[1]]
        for v in VERSIONS:
            b = bundles[v]
            p = b["model"].predict_proba(X)[:, 1]
            cleared = p < b["zones"]["rule_out_below"]
            sick = int(y.sum())
            sick_not_cleared = int((~cleared & (y == 1)).sum())
            auc = (
                bootstrap_ci(roc_auc_score, y, p, need_both_classes=True)
                if 0 < sick < len(y)
                else (np.nan,) * 3
            )
            rows.append(
                {
                    "hospital": name,
                    "version": v,
                    "n": len(y),
                    "n_sick": sick,
                    "disease_rate": y.mean(),
                    "mean_predicted": p.mean(),
                    "roc_auc": fmt_ci(*auc) if not np.isnan(auc[0]) else "n/a",
                    "auc_value": auc[0],
                    "ece": expected_calibration_error(y, p, n_bins=5),
                    "share_cleared": cleared.mean(),
                    "cleared_but_sick": int((cleared & (y == 1)).sum()),
                    "stage1_safety": fmt_ci(*exact_proportion_ci(sick_not_cleared, sick))
                    if sick
                    else "n/a",
                }
            )
    return pd.DataFrame(rows)


def typical_angina_rows(test: pd.DataFrame, bundles: dict) -> pd.DataFrame:
    rows = []
    for name, mask in [("All hospitals", test["cp"] == "typical angina")] + [
        (h, (test["cp"] == "typical angina") & (test[config.HOSPITAL_COLUMN] == h))
        for h in STAGE_HOSPITALS[1]
    ]:
        part = test[mask]
        if not len(part):
            continue
        row = {"group": name, "n": len(part), "actual": part[config.TARGET_COLUMN].mean()}
        for v in VERSIONS:
            row[f"predicted_{v}"] = (
                bundles[v]["model"].predict_proba(part[config.STAGES[1]])[:, 1].mean()
            )
        rows.append(row)
    return pd.DataFrame(rows)


def cleveland_policy(test: pd.DataFrame, bundles1: dict) -> pd.DataFrame:
    cle = test[test[config.HOSPITAL_COLUMN] == config.TRAIN_HOSPITAL]
    y = cle[config.TARGET_COLUMN].to_numpy()
    later = {s: integrity.load(config.MODELS_DIR / f"stage{s}.joblib") for s in (2, 3)}
    p_later = {s: later[s]["model"].predict_proba(cle[config.STAGES[s]])[:, 1] for s in (2, 3)}
    rows = {}
    for v in VERSIONS:
        b1 = bundles1[v]
        p = {1: b1["model"].predict_proba(cle[config.STAGES[1]])[:, 1], **p_later}
        zones = {1: b1["zones"], 2: later[2]["zones"], 3: later[3]["zones"]}
        decision, reached = simulate_policy(p, zones)
        m = decision_metrics(y, decision)
        rows[f"{v} staged policy"] = {
            "recall": fmt_ci(*exact_proportion_ci(m["tp"], m["tp"] + m["fn"])),
            "specificity": fmt_ci(*exact_proportion_ci(m["tn"], m["tn"] + m["fp"])),
            "sick_missed": m["fn"],
            "healthy_flagged": m["fp"],
            "cleared_at_stage1": int(((reached == 1) & (decision == 0)).sum()),
            "needed_treadmill": (reached >= 2).mean(),
            "needed_invasive": (reached == 3).mean(),
        }
    return pd.DataFrame(rows).T


def main():
    _, test = split_v2(load_pooled())
    bundles = load_stage1()
    assert bundles["v2"].get("version") == "v2", "models/stage1.joblib must be the v2 bundle"
    print(
        f"v2 sealed test: {len(test)} patients\n"
        + test.groupby(config.HOSPITAL_COLUMN).size().to_string()
    )

    s1 = stage1_rows(test, bundles)
    ta = typical_angina_rows(test, bundles)
    pol = cleveland_policy(test, bundles)
    s1.to_csv(config.REPORTS_DIR / "v2_final_stage1.csv", index=False)
    ta.to_csv(config.REPORTS_DIR / "v2_final_typical_angina.csv", index=False)
    pol.to_csv(config.REPORTS_DIR / "v2_final_policy_cleveland.csv")
    (config.REPORTS_DIR / "v2_final_meta.json").write_text(
        json.dumps(
            {
                "n_test": len(test),
                "hospitals": test.groupby(config.HOSPITAL_COLUMN).size().to_dict(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    pd.set_option("display.width", 250, "display.max_columns", 30)
    cols = [
        "hospital",
        "version",
        "n",
        "n_sick",
        "disease_rate",
        "mean_predicted",
        "roc_auc",
        "ece",
        "share_cleared",
        "cleared_but_sick",
        "stage1_safety",
    ]
    print("\nA. Stage 1 on the sealed test:\n" + s1[cols].round(3).to_string(index=False))
    print("\nB. Typical angina (actual vs mean predicted):\n" + ta.round(3).to_string(index=False))
    print("\nC. Full 3-stage policy, Cleveland's 61 sealed patients:\n" + pol.to_string())


if __name__ == "__main__":
    main()
