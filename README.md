# 🏆 VINUNI BUSINESS DATATHON 2026
## Revenue and COGS Forecasting Pipeline

> Time-series forecasting pipeline for Revenue and COGS prediction using `MLForecast` and `LightGBM`.

---

## 👥 Team

This project was built during the **VinUni Business Datathon 2026** by:

- Nguyễn Thị Kim Ngân (Julie) — *Team Lead / Exploratory Data Analysis (EDA), Quality Assurance & Storytelling Lead*
- Nguyễn Ngọc Nam — *Data Pipeline & Feature Engineering Lead*
- Trương Lê Trung Hiếu — *ML Modeling & Validation Lead*
- Nguyễn Trần Phương Thuý — *Problem Framing Lead, Exploratory Data Analysis (EDA) & Quality Assurance**

The repository started out... honestly pretty chaotic 😭.

During the competition, everyone pushed experiments, notebooks, temporary files, and random ideas into the repo as fast as possible just to keep the workflow moving. At one point, one of us even joked that we were simply “throwing trash onto GitHub”.

We did not end up winning a prize, but the experience itself became something much more memorable:
- learning how real forecasting pipelines break,
- debugging under pressure,
- arguing over validation leakage at 2AM,
- and somehow still having fun together through all of it.

This repository is kept both as:
- a reproducible forecasting project,
- and a small memory of that experience.

---

## 📌 Overview

This repository contains an end-to-end forecasting workflow for the DATATHON 2026 Revenue and COGS prediction task.

The final official workflow is implemented in:

```text
notebooks/forecast.ipynb
```

The solution focuses on:
- leakage-safe time-series forecasting,
- feature engineering for retail seasonality,
- LightGBM ensemble modeling,
- validation-calibrated blending,
- and SHAP-based explainability.

---

## ⚙️ Main Pipeline

```text
Raw Data
   ↓
Time-series preprocessing
   ↓
Feature Engineering
   ↓
Chronological Validation
   ↓
MLForecast + LightGBM
   ↓
Ensemble Blending
   ↓
Final Forecast Export
```

The pipeline performs the following stages:

| Step | Description |
|---|---|
| Configuration | Defines paths, forecast horizon, model parameters, and lag settings. |
| Data Loading | Reads historical sales data and submission templates. |
| Preprocessing | Converts raw tables into long-format time-series data. |
| Feature Engineering | Builds lag, rolling, calendar, seasonal, and event-based features. |
| Validation | Uses a leakage-safe chronological holdout strategy. |
| Modeling | Trains multiple LightGBM variants inside `MLForecast`. |
| Blending | Combines models using validation-calibrated ensemble weights. |
| Explainability | Generates SHAP summary plots for model interpretation. |
| Export | Produces the final Kaggle-compatible `submission.csv`. |

---

## 🧠 Feature Engineering

The forecasting notebook includes several feature groups:

- Lag features: 7, 14, 30, 90, 180, 354, and 365 days.
- Rolling statistics: rolling mean, minimum, and maximum over 7-day and 30-day windows.
- Calendar features: weekday, month, day of month, and day of year.
- Harmonic week-of-year encodings using sine/cosine transformations.
- Seasonal retail profile features.
- Fixed event windows for recurring business periods.
- COVID-regime indicators for structural disruptions between 2019-2022.

---

## 📊 Validation Metrics

The validation strategy uses a leakage-safe chronological holdout matching the official forecast horizon.

| Target | MAE |
|---|---:|
| Revenue | 595,943 |
| COGS | 498,150 |
| Average | 547,047 |

MAE was selected because it directly reflects absolute business forecasting error.

---

## 📂 Project Structure

```text
DATATHON-2026-GenApLucUWU/
├── README.md
├── requirements.txt
├── data/
│   ├── raw/
│   └── output/
│       ├── submission.csv
│       ├── forecast_visualization.png
│       ├── shap_summary.png
│       └── shap_summary_cogs.png
├── notebooks/
│   ├── forecast.ipynb
│   ├── answer.ipynb
│   └── Thuy.ipynb
├── reports/
│   └── figures/
├── knowledge/
└── im_about_to_del/
```

Yes, `im_about_to_del/` is exactly what it sounds like.

It contains old experiments, abandoned notebooks, broken ideas, temporary pipelines, and random remnants that somehow survived cleanup after the competition 😭.

---

## 🔍 Explainability (XAI)

To avoid treating the forecasting system as a pure black-box model, SHAP analysis was used to interpret prediction behavior.

Generated outputs:

```text
data/output/shap_summary.png
data/output/shap_summary_cogs.png
```

The explainability analysis highlights how predictions are influenced by:
- seasonality,
- short-term momentum,
- retail event windows,
- and structural market regime shifts.

---

## 🚀 Environment Setup

### 1. Create a virtual environment

```powershell
python -m venv .venv
```

### 2. Activate the environment

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

### 4. Register Jupyter kernel (optional)

```powershell
python -m ipykernel install --user --name datathon-2026 --display-name "Python (datathon-2026)"
```

---

## ▶️ Reproducing the Forecast

1. Open:

```text
notebooks/forecast.ipynb
```

2. Select the correct Python kernel.

3. Run all notebook cells from top to bottom.

Generated outputs:

```text
data/output/submission.csv
data/output/forecast_visualization.png
data/output/shap_summary.png
data/output/shap_summary_cogs.png
```

Final submission file:

```text
data/output/submission.csv
```

Expected columns:

```text
Date, Revenue, COGS
```

---

## ✨ Final Note

This project may not be the cleanest repository ever created.

But it represents months of experimentation, debugging, feature engineering, model tuning, failed ideas, rushed commits, and teamwork under pressure.

And honestly, that probably matters more than the leaderboard.
