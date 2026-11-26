# Data

## Source
**UCI Heart Disease dataset**, combined version of all four hospitals, via the Kaggle mirror
[`redwankarimsony/heart-disease-data`](https://www.kaggle.com/datasets/redwankarimsony/heart-disease-data).
The original is at the [UCI Machine Learning Repository](https://archive.ics.uci.edu/dataset/45/heart+disease),
created by Janosi, Steinbrunn, Pfisterer and Detrano (1988), licensed CC BY 4.0.

## Hospitals
| Hospital | Patients |
|---|---|
| Cleveland Clinic Foundation (USA) | 304 |
| Hungarian Institute of Cardiology, Budapest | 293 |
| VA Medical Center, Long Beach (USA) | 200 |
| University Hospitals, Zurich & Basel (Switzerland) | 123 |

Since version 2, the check-up model also learns from the **Z-Alizadeh Sani** cohort (Tehran, Iran, 303 patients, 2010s, CC BY 4.0); see [`raw/external/README.md`](raw/external/README.md).

## Folders
- `raw/`: the original file, **never edited**. All cleaning happens in code.
- `processed/`: cleaned output created by the pipeline (not committed to Git).
