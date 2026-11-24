# External datasets

## ✅ Z-Alizadeh Sani (used: external validation)
- **Source:** UCI Machine Learning Repository, dataset 412, https://archive.ics.uci.edu/dataset/412/z+alizadeh+sani (DOI 10.24432/C5Q31T), donated 2017.
- **Creators:** Z. Alizadeh Sani et al. (Rajaie Cardiovascular, Medical and Research Center, Tehran, Iran, per the original publication).
- **Licence:** CC BY 4.0. Credit the creators and the UCI repository when reusing.
- **Contents:** 303 patients, 56 columns (54 features + angiography result), no missing values. Outcome `Cath`: "CAD" if diameter narrowing ≥ 50%, otherwise "Normal" (same definition as the UCI Heart Disease data).
- **Files:**
  - `z+alizadeh+sani.zip`: as downloaded (sha256 `48210a6623fa6112423d9bc357f72fe3fca12ae77866e63e08632e15d95b724e`), containing `Z-Alizadeh sani dataset.xlsx`.
  - `z_alizadeh_sani.csv`: the same table converted once to CSV with Unix line endings (sha256 `bc90f8dec1388e38a4d608d6015941c0460d0924541fee1c43279498d3a60c67`); a round-trip check confirmed it identical to the spreadsheet. The project reads the CSV, so no Excel library is needed.
- **Mapping to CardioStage:** see `src/cardiostage/external_iran.py` (cholesterol estimated as LDL + HDL + TG/5; no exercise test or fluoroscopy, so only stage 1 is a fair test).

## ❌ Cardiovascular_Disease_Dataset, India (rejected)
- **Source:** Mendeley Data, DOI 10.17632/dzz48mvjht.1 (2021), 1,000 rows, CC BY 4.0. Not stored in this repository.
- **Why rejected** (checked on 2026-11-24; details in docs/learning/14-new-data-and-v2.md):
  1. Its own description contradicts the data: slope documented as 1–3 but 180 rows are 0 (all disease-free); cholesterol documented as 126–564 but 53 rows are 0 and the maximum is 602.
  2. Ages are uniformly spread (KS test p = 0.11), unlike any real clinical cohort (Cleveland p ≈ 1e-11).
  3. Classic predictors show no link to disease (age AUC 0.51, exercise angina 0.52), while slope codes determine the outcome almost completely (0 → 0%, 2 → 96%, 3 → 100%).
  4. The hospital and the diagnosis method aren't stated; the description text is copied from the UCI documentation.
  Together these make it unsafe to treat as real patient data (possibly synthetic or rule-labelled).
