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
PROCESSED_DIR = DATA_DIR / "processed"   # cleaned data we create in Phase 2
MODELS_DIR = PROJECT_ROOT / "models"     # trained models saved to disk
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
    "age",       # age in years
    "sex",       # Male / Female
    "cp",        # chest pain type (typical angina, atypical, non-anginal, none)
    "trestbps",  # resting blood pressure (mm Hg)
    "chol",      # serum cholesterol (mg/dl)
    "fbs",       # fasting blood sugar > 120 mg/dl (a diabetes indicator)
]

# Stage 2: needs an ECG and a supervised treadmill (exercise stress) test.
STAGE_2_TREADMILL = [
    "restecg",   # resting ECG result
    "thalch",    # maximum heart rate reached during exercise
    "exang",     # did exercise cause chest pain? (exercise-induced angina)
    "oldpeak",   # ST depression: how much the ECG signal dips under stress
    "slope",     # shape of the ST segment at peak exercise
]

# Stage 3: invasive / imaging tests done in a hospital.
STAGE_3_INVASIVE = [
    "ca",        # number of major vessels coloured by fluoroscopy (dye + X-ray)
    "thal",      # thallium stress scan result (nuclear imaging)
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
