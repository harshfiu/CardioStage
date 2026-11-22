"""
Central configuration for CardioStage.

Every other file imports its paths, constants, and feature groups from here,
so there is exactly ONE place to change them. This avoids "magic strings"
(like "data/raw/heart_disease_uci.csv") being copy-pasted across many files,
where they could drift out of sync.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# __file__ is the path of THIS file: .../src/cardiostage/config.py
# .resolve() turns it into an absolute path, and .parents[2] walks up
# three levels: config.py -> cardiostage/ -> src/ -> project root.
# Building paths this way means the code works no matter which folder
# you run it from, and on any operating system (Windows or Mac/Linux).
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_PATH = DATA_DIR / "raw" / "heart_disease_uci.csv"
PROCESSED_DIR = DATA_DIR / "processed"  # cleaned data we create in Phase 2
MODELS_DIR = PROJECT_ROOT / "models"  # trained models saved to disk
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"  # charts for README/app

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
# Many ML steps involve randomness (shuffling data, building random trees).
# Fixing the "seed" makes that randomness repeatable: run the code twice and
# you get identical results. Essential for trustworthy, comparable experiments.
RANDOM_SEED = 42

# ---------------------------------------------------------------------------
# Target column
# ---------------------------------------------------------------------------
# In the raw data, "num" is disease severity from 0 (healthy) to 4 (severe).
# We predict a yes/no question: "does this patient have heart disease?"
# So in Phase 2 we will convert num > 0 into 1 (disease) and num == 0 into 0.
RAW_TARGET_COLUMN = "num"
TARGET_COLUMN = "has_disease"

# Column saying which of the 4 hospitals a patient came from.
# Used for the cross-hospital experiment (feature B), NOT as a model input:
# a real patient's hospital name shouldn't decide their diagnosis.
HOSPITAL_COLUMN = "dataset"

# ---------------------------------------------------------------------------
# Feature stages  (the heart of CardioStage's novelty, feature A)
# ---------------------------------------------------------------------------
# We group the patient measurements by HOW HARD they are to obtain, mirroring
# how a doctor escalates from cheap checks to expensive tests.

# Stage 1: available at a normal clinic visit plus a routine blood test.
STAGE_1_BASIC = [
    "age",  # age in years
    "sex",  # Male / Female
    "cp",  # chest pain type (typical angina, atypical, non-anginal, none)
    "trestbps",  # resting blood pressure (mm Hg)
    "chol",  # serum cholesterol (mg/dl)
    "fbs",  # fasting blood sugar > 120 mg/dl (a diabetes indicator)
]

# Stage 2: needs an ECG and a supervised treadmill (exercise stress) test.
STAGE_2_TREADMILL = [
    "restecg",  # resting ECG result
    "thalch",  # maximum heart rate reached during exercise
    "exang",  # did exercise cause chest pain? (exercise-induced angina)
    "oldpeak",  # ST depression: how much the ECG signal dips under stress
    "slope",  # shape of the ST segment at peak exercise
]

# Stage 3: invasive / imaging tests done in a hospital.
STAGE_3_INVASIVE = [
    "ca",  # number of major vessels coloured by fluoroscopy (dye + X-ray)
    "thal",  # thallium stress scan result (nuclear imaging)
]

# Each stage INCLUDES everything from the stages before it, because a patient
# who reached the treadmill test still has their basic information.
STAGES = {
    1: STAGE_1_BASIC,
    2: STAGE_1_BASIC + STAGE_2_TREADMILL,
    3: STAGE_1_BASIC + STAGE_2_TREADMILL + STAGE_3_INVASIVE,
}

STAGE_NAMES = {
    1: "Basic check-up",
    2: "+ Treadmill stress test",
    3: "+ Invasive imaging",
}

# ---------------------------------------------------------------------------
# Feature types  (decide HOW each column is prepared for the models)
# ---------------------------------------------------------------------------
# Models only understand numbers, and different kinds of columns need
# different preparation (see preprocessing.py):

# Numeric: real measurements where "bigger" means something.
NUMERIC_FEATURES = ["age", "trestbps", "chol", "thalch", "oldpeak", "ca"]

# Binary: yes/no columns, stored as 1/0.
BINARY_FEATURES = ["sex", "fbs", "exang"]

# Categorical: a few named options with no natural order
# (e.g. chest pain type). These get "one-hot encoded" into yes/no columns.
CATEGORICAL_FEATURES = ["cp", "restecg", "slope", "thal"]

CLEAN_DATA_PATH = PROCESSED_DIR / "heart_clean.csv"

# ---------------------------------------------------------------------------
# Training setup  (decided after Phase 2, see docs/learning/02-data.md)
# ---------------------------------------------------------------------------
# All stage models are trained on Cleveland only: it is the one hospital with
# near-complete data for every stage, so the stages can be compared fairly on
# the SAME patients. The other hospitals become unseen external test sets.
TRAIN_HOSPITAL = "Cleveland"
EXTERNAL_HOSPITALS = ["Hungary", "Switzerland", "VA Long Beach"]

# 20% of Cleveland is sealed away as the final test set ("the exam").
TEST_SIZE = 0.2

# Cross-validation: split training data into 5 parts ("folds"), and repeat
# the whole process with different shuffles for more stable estimates.
CV_FOLDS = 5
CV_REPEATS = 3

REPORTS_DIR = PROJECT_ROOT / "reports"

# ---------------------------------------------------------------------------
# Screening decision rules  (Phase 4)
# ---------------------------------------------------------------------------
# In screening, missing a sick patient is far worse than a false alarm, so the
# thresholds are chosen around RECALL (fraction of sick patients caught).

# Final yes/no threshold: catch at least 97% of sick patients.
# Chosen deliberately (Phase 4): in screening a false alarm costs an extra
# test, while a missed patient can cost a life. Compared options (90/95/97%)
# are documented in docs/learning/04-staging.md.
SCREENING_RECALL = 0.97

# Stage-by-stage "is the next test worth it?" zones:
#   LOW risk   -> below a threshold that still keeps >= 99% of sick patients
#                 above it (so at most ~1% of sick patients are sent home
#                 at that stage).
#   HIGH risk  -> above a threshold where >= 90% of flagged patients are
#                 truly sick: confident enough to refer straight to a
#                 cardiologist.
#   UNCERTAIN  -> in between: recommend the next, more informative test.
RULE_OUT_RECALL = 0.99
RULE_IN_PRECISION = 0.90

# ---------------------------------------------------------------------------
# Honest probabilities and "not sure" answers  (Phase 5)
# ---------------------------------------------------------------------------
# Calibration methods compared (see calibration.py):
#   "sigmoid"  (Platt scaling): fits a smooth S-curve, needs little data
#   "isotonic": fits any increasing step function, flexible but data-hungry
CALIBRATION_METHODS = ["sigmoid", "isotonic"]

# Model uncertainty: train N_REPLICAS versions of each stage model, each on a
# random 80% of the training patients. If those versions disagree about a
# patient enough that their middle-80% range crosses a decision threshold,
# the answer is flagged "not confident".
N_REPLICAS = 20
REPLICA_FRACTION = 0.8
UNCERTAINTY_PERCENTILES = (10, 90)

# Decision (Phase 5): on this data the disagreement check proved a weak error
# detector, so the app SHOWS each patient's plausible risk range for
# transparency but does NOT let it change decisions. (As a guard it caught
# 1 more sick patient of 111 but raised invasive tests from 60% to 72%.)
USE_UNCERTAINTY_GUARD = False

# Unusual-patient detection: flag inputs less typical than the most unusual
# 1% of training patients.
NOVELTY_QUANTILE = 0.01
