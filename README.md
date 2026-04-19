# 🚀 DATATHON — Data Pipeline: Validation, Cleaning & Merging CSV Data

> **Role:** Data Engineer | **Language:** Python 3.10+ | **Date:** 2026-04-19

---

## 📌 Project Overview

This pipeline automatically processes **13 e-commerce CSV files** through 3 main stages:

| Stage | Module | Description |
|-------|--------|-------------|
| **1. Validation** | `src/validator.py` | Detect Missing Values, Duplicates, and Data Integrity issues |
| **2. Cleaning** | `src/cleaner.py` | Handle missing values (Null handling) and save to `data/interim/` |
| **3. Merging** | `src/merger.py` | Join cleaned tables into a single Master table |

**Results:** Files in `data/output/`
- `master_table.csv` — Complete merged data (Star Schema)
- `validation_report.csv` — Detailed data quality report for each input file

---

## 🗂 Project Structure

```
DATATHON/
├── pipeline.py              ← RUN THIS FILE to start the full pipeline
├── requirements.txt         ← List of required libraries
├── .gitignore
│
├── configs/                 ← Configuration (no code changes needed for rules)
│   ├── datatypes.yaml       ← Column data type declarations
│   └── cleaning_rules.yaml  ← Cleaning rules (strip, digits_only, etc.)
│
├── src/                     ← Core Logic
│   ├── __init__.py
│   ├── validator.py         ← Missing Values, Duplicates, Data Integrity checks
│   ├── cleaner.py           ← Null-value cleaning
│   ├── merger.py            ← Table JOINs via Star Schema
│   └── reporter.py          ← Aggregate reports, terminal output & CSV export
│
├── data/
│   ├── raw/                 ← 📥 RAW CSV (Input data)
│   ├── interim/             ← 🔄 Cleaned data (Intermediate steps)
│   ├── processed/           ← ✅ Encoded/Normalized data
│   ├── quarantine/          ← 🚫 Erroneous data rows
│   ├── lookups/             ← 📚 Additional mapping tables
│   └── output/              ← 📊 FINAL RESULTS (Master table & Reports)
│
├── notebooks/               ← 📓 Jupyter Notebooks for EDA
│   └── answer.ipynb         ← Main analysis notebook
│
├── reports/                 ← 📊 Exported EDA reports (Figures, Profiles)
│
├── tests/                   ← ✅ Automated Tests
│   └── test_validator.py    ← Validator module correctness tests
└── .venv/                   ← Virtual Environment
```

---

## 🛠 Environment Setup (Run ONCE)

### Step 1 — Open Terminal in the project directory

```powershell
# On Windows: Open PowerShell and navigate to the folder
cd d:\DATATHON
```

---

### Step 2 — Create Virtual Environment

```powershell
python -m venv .venv
```

---

### Step 3 — Activate Virtual Environment

```powershell
# Windows (PowerShell)
.venv\Scripts\activate

# When successful, the terminal will show (.venv) at the start:
# (.venv) PS d:\DATATHON>
```

---

### Step 4 — Install Libraries

```powershell
pip install -r requirements.txt
```

---

## ▶ Running the Pipeline

### Method 1: Full Execution (Recommended)

```powershell
python pipeline.py
```

**Execution Flow:**
1. Discover CSV files in `data/raw/`
2. **Stage 1 (Validation):** Validate quality of each file → Print detailed report.
3. **Stage 2 (Cleaning):** Clean Null values → Save intermediate files to `data/interim/`.
4. **Stage 3 (Merging):** Merge all tables → Save `data/output/master_table.csv`.
5. **Report:** Save summary report to `data/output/validation_report.csv`.

---

### Method 2: Validation Only (Skip cleaning & merging)

```powershell
python pipeline.py --validate_only
```

---

### Method 3: Specify a different data directory

```powershell
python pipeline.py --data_dir path/to/your/csvs
```

---

## 🐍 Code Explanation (Main Modules)

### `src/validator.py` — Data Validation
Performs 3 checks:
- `check_missing_values()`: Counts empty cells (NaN/Null).
- `check_duplicates()`: Detects fully duplicate rows.
- `check_data_integrity()`: Ensures numeric columns (Price, Quantity...) contain no invalid characters.

### `src/cleaner.py` — Data Cleaning
Automatically fills or handles missing values based on configuration, preparing data for analysis and merging.

### `src/merger.py` — Data Merging
Uses the **Star Schema** model to connect tables:
- **Fact Table:** `orders`
- **Dimension Tables:** `customers`, `products`, `payments`, `shipments`, etc.

### `src/reporter.py` — Reporting
Aggregates validator results, formats tables using `tabulate`, and exports CSV files for quality management.

---

## 🧪 Running Unit Tests

Ensure code correctness by running the test suite:

```powershell
# Run all tests in the tests/ directory
pytest tests/ -v
```

---

## 📁 Output Files

| File | Location | Description |
|------|----------|-------------|
| `master_table.csv` | `data/output/` | Fully merged data, ready for BI/ML |
| `validation_report.csv` | `data/output/` | Detailed report on errors and quality of the 13 input files |

---

*Last updated: 2026-04-19*
