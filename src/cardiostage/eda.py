"""
Exploratory Data Analysis (EDA): charts that help us understand the data
BEFORE modelling. Each chart answers one question; findings are explained in
docs/learning/02-data.md.

Run:  python -m cardiostage.eda
Charts are saved to reports/figures/.
"""

import matplotlib

matplotlib.use("Agg")  # draw to files, not a pop-up window (works anywhere)

import matplotlib.pyplot as plt
import seaborn as sns

from cardiostage import config
from cardiostage.data import clean_data, load_raw

# One consistent, colour-blind-safe colour per meaning, used in every chart.
HEALTHY_COLOR = "#2a78d6"  # blue
DISEASE_COLOR = "#eb6834"  # orange
TEXT_COLOR = "#52514e"
HOSPITAL_ORDER = ["Cleveland", "Hungary", "VA Long Beach", "Switzerland"]

# Readable names for charts (raw column names are cryptic).
PRETTY_NAMES = {
    "age": "Age",
    "sex": "Sex (male)",
    "cp": "Chest pain type",
    "trestbps": "Resting blood pressure",
    "chol": "Cholesterol",
    "fbs": "High fasting blood sugar",
    "restecg": "Resting ECG",
    "thalch": "Max heart rate",
    "exang": "Exercise chest pain",
    "oldpeak": "ST depression",
    "slope": "ST slope",
    "ca": "Blocked vessels (fluoroscopy)",
    "thal": "Thallium scan",
}


def _style():
    sns.set_theme(style="whitegrid", context="notebook")
    plt.rcParams.update(
        {
            "axes.edgecolor": "#d0cfca",
            "grid.color": "#ebeae6",
            "axes.labelcolor": TEXT_COLOR,
            "xtick.color": TEXT_COLOR,
            "ytick.color": TEXT_COLOR,
            "axes.titleweight": "bold",
            "figure.dpi": 110,
            "savefig.bbox": "tight",
        }
    )


def _save(fig, name):
    config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = config.FIGURES_DIR / name
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"saved {path.relative_to(config.PROJECT_ROOT)}")


def plot_disease_rate_by_hospital(df):
    """Q: Do the four hospitals have similar patients?"""
    rates = (
        df.groupby(config.HOSPITAL_COLUMN)[config.TARGET_COLUMN]
        .agg(["mean", "size"])
        .reindex(HOSPITAL_ORDER)
    )

    fig, ax = plt.subplots(figsize=(7, 3.6))
    bars = ax.barh(rates.index, rates["mean"] * 100, color=DISEASE_COLOR, height=0.55)
    for bar, (rate, n) in zip(bars, rates.itertuples(index=False)):
        ax.text(
            bar.get_width() + 1.5,
            bar.get_y() + bar.get_height() / 2,
            f"{rate:.0%}  (n={n})",
            va="center",
            color=TEXT_COLOR,
        )
    ax.set_xlim(0, 115)
    ax.set_xlabel("Patients with heart disease (%)")
    ax.invert_yaxis()
    ax.set_title("Disease rate varies hugely between hospitals")
    _save(fig, "01_disease_rate_by_hospital.png")


def plot_missing_by_hospital(df):
    """Q: Which measurements does each hospital actually have?"""
    features = config.STAGES[3]
    missing = df[features].isna().groupby(df[config.HOSPITAL_COLUMN]).mean() * 100
    missing = missing.reindex(HOSPITAL_ORDER)
    missing.columns = [PRETTY_NAMES[c] for c in features]

    fig, ax = plt.subplots(figsize=(11, 3.8))
    sns.heatmap(
        missing,
        annot=True,
        fmt=".0f",
        cmap="Blues",
        vmin=0,
        vmax=100,
        cbar_kws={"label": "% missing"},
        linewidths=2,
        linecolor="white",
        ax=ax,
    )
    # Vertical lines separating the three stages.
    n1, n2 = len(config.STAGES[1]), len(config.STAGES[2])
    for x in (n1, n2):
        ax.axvline(x, color="#1a1a19", linewidth=2.5)
    for label, start, end in [
        ("Stage 1: basic", 0, n1),
        ("Stage 2: treadmill", n1, n2),
        ("Stage 3: invasive", n2, len(features)),
    ]:
        ax.text((start + end) / 2, -0.35, label, ha="center", fontweight="bold", color=TEXT_COLOR)
    ax.set_xlabel("")
    ax.set_ylabel("")
    plt.setp(ax.get_xticklabels(), rotation=35, ha="right")
    ax.set_title(
        "Missing data (%) by hospital: invasive tests exist almost only in Cleveland", pad=48
    )
    _save(fig, "02_missing_by_hospital.png")


def plot_numeric_by_disease(df):
    """Q: How do measurements differ between healthy and sick patients?"""
    columns = ["age", "trestbps", "chol", "thalch", "oldpeak"]
    fig, axes = plt.subplots(1, len(columns), figsize=(16, 3.4))
    for ax, column in zip(axes, columns):
        for value, color, label in [
            (0, HEALTHY_COLOR, "No disease"),
            (1, DISEASE_COLOR, "Heart disease"),
        ]:
            data = df.loc[df[config.TARGET_COLUMN] == value, column].dropna()
            sns.kdeplot(
                data,
                ax=ax,
                color=color,
                fill=True,
                alpha=0.25,
                linewidth=2,
                label=label,
                common_norm=False,
            )
        ax.set_title(PRETTY_NAMES[column])
        ax.set_xlabel("")
        ax.set_ylabel("")
        ax.set_yticks([])
    # One shared legend above the panels, so it never covers a curve.
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles, labels, loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(0.5, 1.04)
    )
    fig.suptitle("Measurement distributions: healthy vs heart disease", fontweight="bold", y=1.12)
    _save(fig, "03_numeric_by_disease.png")


def plot_categorical_disease_rate(df):
    """Q: Which categories are associated with heart disease?"""
    readable = df.assign(
        sex=df["sex"].map({1.0: "Male", 0.0: "Female"}),
        exang=df["exang"].map({1.0: "Yes", 0.0: "No"}),
        fbs=df["fbs"].map({1.0: "Yes", 0.0: "No"}),
    )
    columns = ["cp", "sex", "exang", "fbs", "slope", "thal"]
    fig, axes = plt.subplots(2, 3, figsize=(14, 6.5))
    overall = df[config.TARGET_COLUMN].mean() * 100
    for ax, column in zip(axes.flat, columns):
        stats = (
            readable.dropna(subset=[column])
            .groupby(column)[config.TARGET_COLUMN]
            .agg(["mean", "size"])
            .sort_values("mean")
        )
        ax.barh(stats.index.astype(str), stats["mean"] * 100, color=DISEASE_COLOR, height=0.55)
        for i, (rate, n) in enumerate(stats.itertuples(index=False)):
            ax.text(
                rate * 100 + 2, i, f"{rate:.0%} (n={n})", va="center", color=TEXT_COLOR, fontsize=9
            )
        ax.axvline(overall, color=TEXT_COLOR, linestyle="--", linewidth=1)
        ax.set_xlim(0, 118)
        ax.set_title(PRETTY_NAMES[column])
    fig.supxlabel(
        f"Patients with heart disease (%)   - - -  overall rate {overall:.0f}%", color=TEXT_COLOR
    )
    fig.suptitle("Heart-disease rate by category", fontweight="bold")
    fig.tight_layout()
    _save(fig, "04_categorical_disease_rate.png")


def main():
    _style()
    df = clean_data(load_raw())
    plot_disease_rate_by_hospital(df)
    plot_missing_by_hospital(df)
    plot_numeric_by_disease(df)
    plot_categorical_disease_rate(df)


if __name__ == "__main__":
    main()
