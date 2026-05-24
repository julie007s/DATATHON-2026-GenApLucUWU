# 🏆 VINUNI BUSINESS DATATHON 2026
## Revenue and COGS Forecasting Pipeline

> **Role:** Team Lead / Data & Problem Framing Lead  
> **Language:** Python 3.10+  
> **Frameworks:** `MLForecast`, `LightGBM`  
> **Project Status:** Completed (Academic & Competition Experience)

---

## 👥 Our Team
A journey of sleepless nights, model tuning, and invaluable teamwork among 4 members:
* **Nguyễn Thị Kim Ngân (Julie)** — *Team Lead / Problem Framing & QA*
* **Nguyễn Ngọc Nam** — *Data Pipeline & Feature Engineering Lead*
* **Trương Lê Trung Hiếu** — *ML Modeling & Validation Lead*
* **Nguyễn Trần Phương Thúy** — *Exploratory Data Analysis (EDA) & Storytelling Lead*

---

## 1) Overview & Business Problem
Developed for the **VinUni Business Datathon 2026**, this project implements a comprehensive time-series forecasting pipeline for two critical financial metrics: **Revenue** and **Cost of Goods Sold (COGS)** to optimize budget planning.

### Key Data Challenges:
- **Strong Non-linear Volatility:** Heavily influenced by seasonality (Calendar, Seasonal profiles) and event windows.
- **Structural Market Shifts:** The COVID-19 period (2019-2022) significantly altered standard consumer behavior.

---

## 2) Core Architecture & Methodology
The supervised daily time-series forecasting solution is implemented in `notebooks/forecast.ipynb`:

**Workflow:**
`[Raw Data (Wide format)]` $\rightarrow$ `[Long format (unique_id, ds, y)]` $\rightarrow$ `[Pipeline]`

### Pipeline Components:
- **Feature Engineering:**
    - Lags (7d - 365d)
    - Rolling Stats (Mean, Min, Max)
    - Harmonic Fourier (Sine/Cosine)
    - COVID-regime features
- **Validation Strategy:**
    - 548-day Chronological Holdout
    - Leakage-safe design
    - Aligned with actual forecasting horizons
- **Modeling & Blending:**
    - MLForecast + LightGBM Ensembles
    - Calibrated Blending via Validation MAE
    - Non-negative clipping to avoid negative price/cost predictions

---

## 3) Project Structure
```text
DATATHON-2026-GenApLucUWU/
├── README.md
├── requirements.txt
├── data/
│   ├── output/          # Submission files (submission.csv) and result charts
│   └── raw/             # Original dataset from organizers
├── notebooks/
│   ├── forecast.ipynb   # Main forecasting pipeline (Run All Cells)
│   ├── answer.ipynb     # Supplementary analysis
│   └── Thuy.ipynb       # Exploratory Data Analysis (EDA) by Thúy
├── reports/figures/     # Charts and SHAP summary plots for reporting
└── knowledge/           # Competition rules, data schema, and risk analysis
```

---

## 4) Explainability & Insights (XAI)
To avoid a "black-box" model, **SHAP (SHapley Additive exPlanations)** was used to decompose forecasting drivers.
- **Insight:** The plot at `data/output/shap_summary.png` demonstrates that forecasts are primarily driven by **Seasonality**, recent **Momentum**, and specific **Retail Events**.

---

## 5) Internal Validation Metrics
The model is evaluated using **MAE (Mean Absolute Error)** to accurately reflect absolute errors in financial risk management.

| Target | Validation MAE |
| :--- | :--- |
| 💰 Revenue | 595,943 |
| 📦 COGS | 498,150 |
| 📈 **Average** | **547,047** |

---

## 6) Environment Setup & Replication

### Step 1: Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Step 2: Install Dependencies
```powershell
pip install -r requirements.txt
```

### Step 3: Reproduce Results
1. Open `notebooks/forecast.ipynb`.
2. Select the `.venv` kernel.
3. Click **Run All Cells**.
4. The Kaggle-formatted submission file will be exported to `data/output/submission.csv` with columns: `Date`, `Revenue`, `COGS`.

---
*This project serves as a significant milestone in our Data Science learning journey at UIT!* 🎓
