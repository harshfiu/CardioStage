"""
Rebuild every trained model from scratch, in the right order.

Trained models are not stored in Git (they're generated files), so after
cloning the repo, run this once (~10 minutes) before starting the app:

    python -m cardiostage.train_all

Steps:
  1. Phase 4: per-stage model selection and decision zones  (staging.py)
  2. Phase 5: calibration, uncertainty copies, novelty detectors (calibration.py)
     -> models/stage1.joblib, stage2.joblib, stage3.joblib  (used by the app)
"""

import time

from cardiostage import calibration, staging


def main():
    start = time.time()
    print("== Phase 4: staged model selection ==")
    staging.main()
    print("\n== Phase 5: calibration, uncertainty and novelty detection ==")
    calibration.main()
    print(f"\nAll models built in {(time.time() - start) / 60:.1f} minutes.")


if __name__ == "__main__":
    main()
