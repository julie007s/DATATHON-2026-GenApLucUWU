# DATATHON 2026 - Pipeline Du Bao Revenue & COGS

> Vai tro: Data Engineer / ML Engineer  
> Ngon ngu: Python 3.10+  
> Cap nhat: 2026-05-01

---

## 1) Tong quan

Du an nay xay dung pipeline end-to-end cho bai toan du bao **Revenue** va **COGS** tu du lieu e-commerce.

Pipeline hien tai khong chi dung o muc validation/cleaning, ma da mo rong thanh chuoi xu ly day du:

1. Validation du lieu theo schema YAML
2. Cleaning va chuan hoa du lieu
3. Merge theo Star Schema tao bang tong
4. Target encoding theo time-series (giam leakage)
5. Feature engineering daily + lag/rolling
6. Train model XGBoost cho Revenue va COGS
7. Predict de tao file submission

---

## 2) Kien truc pipeline

| Giai doan | Module | Mo ta |
|---|---|---|
| Stage 1 | `src/validator_new.py` | Kiem tra missing, duplicate, sai kieu du lieu theo `configs/datatypes.yaml` |
| Stage 2 | `src/cleaner_new.py` | Fill null theo datatype + ap cleaning rules tu `configs/cleaning_rules.yaml` |
| Stage 2 | `src/merger.py` | Join cac bang theo Star Schema, tao `master_table.csv` |
| Stage 2.5 | `src/encoder.py` | Target encoding theo expanding window, han che look-ahead leakage |
| Stage 3 | `src/featurizer.py` | Tao feature daily, lag/roll, calendar feature, merge web traffic |
| Stage 4 | `src/trainer.py` | Train XGBoost cho Revenue va COGS, luu model + feature importance |
| Stage 5 | `src/predictor.py` | Du bao de quy (recursive) va xuat submission |

File dieu phoi chinh: `pipeline.py`.

---

## 3) Cau truc thu muc

```text
DATATHON-2026-GenApLucUWU/
|-- pipeline.py
|-- requirements.txt
|-- README.md
|-- drawchart.ipynb
|
|-- configs/
|   |-- datatypes.yaml
|   |-- cleaning_rules.yaml
|   |-- encoding.yaml
|   |-- features.yaml
|
|-- src/
|   |-- validator_new.py
|   |-- cleaner_new.py
|   |-- merger.py
|   |-- encoder.py
|   |-- featurizer.py
|   |-- trainer.py
|   |-- predictor.py
|   |-- reporter.py
|   |-- logger.py
|   |-- validator.py
|   |-- cleaner.py
|
|-- data/
|   |-- raw/         (du lieu dau vao)
|   |-- interim/     (du lieu sau cleaning)
|   |-- output/      (bang tong, feature, submission, bao cao)
|   |-- processed/
|   |-- quarantine/
|   |-- lookups/
|
|-- reports/
|   |-- feature_importance.png
|   |-- figures/
|
|-- notebooks/
|   |-- answer.ipynb
|   |-- forecast.ipynb
|
|-- tests/
|   |-- test_validator.py
```

---

## 4) Cai dat moi truong

### Buoc 1 - Mo terminal tai thu muc du an

```powershell
cd d:\DATATHON-2026-GenApLucUWU
```

### Buoc 2 - Tao virtual environment

```powershell
python -m venv venv
```

### Buoc 3 - Kich hoat virtual environment (Windows PowerShell)

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\venv\Scripts\Activate.ps1
```

### Buoc 4 - Cai thu vien

```powershell
pip install -r requirements.txt
```

---

## 5) Cach chay pipeline

### 5.1 Chay day du validate-clean-merge-encode-feature

```powershell
python pipeline.py
```

### 5.2 Chi validation

```powershell
python pipeline.py --validate_only
```

### 5.3 Train model

```powershell
python pipeline.py --train
```

### 5.4 Train voi moc thoi gian holdout

```powershell
python pipeline.py --train --train_until 2022-01-01
```

### 5.5 Du bao va tao submission (can model da train)

```powershell
python pipeline.py --predict
```

### 5.6 Train + Predict trong mot lenh

```powershell
python pipeline.py --train --predict --train_until 2022-01-01
```

### 5.7 Doi thu muc du lieu raw

```powershell
python pipeline.py --data_dir data/raw
```

---

## 6) Dau ra quan trong

Sau khi chay, cac file ket qua thuong nam o `data/output/`:

- `validation_report.csv`: Tong hop loi/missing/duplicate/integrity
- `master_table.csv`: Bang merged sau stage Star Schema
- `encoded_master.parquet`: Bang sau target encoding
- `featured_table.parquet`: Bang feature daily dung cho train/predict
- `submission.csv`: File nop bai gom 3 cot `Date, Revenue, COGS`
- `analysis_report.csv`: Bao cao chi tiet (co them Profit)

Ngoai ra:

- Model duoc luu trong thu muc `models/` (neu chay `--train`)
  - `xgboost_revenue_model.joblib`
  - `xgboost_cogs_model.joblib`
  - `advanced_encoders.joblib`
- Hinh importance/visual duoc luu trong `reports/`.

---

## 7) He thong config

Pipeline duoc thiet ke theo huong config-driven:

- `configs/datatypes.yaml`
  - Khai bao schema mong doi cho tung file CSV
  - Validator/Cleaner doc file nay de check va xu ly null

- `configs/cleaning_rules.yaml`
  - Quy tac lam sach theo cot va theo nhom datatype
  - Vi du: strip, upper_case, digits_only, drop_negatives

- `configs/encoding.yaml`
  - Cau hinh cot target encoding, target_col va smoothing_weight

- `configs/features.yaml`
  - Danh sach rule tao/xoa feature theo 2 scope:
    - row-level
    - daily-level

---

## 8) Kiem thu

Chay unit test:

```powershell
pytest tests/ -v
```

Co the chay kem do bao phu:

```powershell
pytest tests/ --cov=src --cov-report=term-missing
```

---

## 9) Ghi chu su dung

- Pipeline mac dinh tim du lieu trong `data/raw/`.
- Buoc predict hien mac dinh doc sample submission tu `data/raw/sample_submission.csv`.
- Neu ban dang su dung ten file khac (vi du `submission.csv` hoac `sales_submission.csv`), hay doi ten file tuong ung hoac cap nhat duong dan trong `src/predictor.py`.
- Du an co dong thoi ban cu (`validator.py`, `cleaner.py`) va ban moi (`validator_new.py`, `cleaner_new.py`); `pipeline.py` dang dung ban moi.

---

## 10) Thu vien chinh

Mot so thu vien noi bat trong `requirements.txt`:

- Xu ly du lieu: pandas, numpy, pyarrow, PyYAML
- ML/Forecasting: xgboost, scikit-learn, optuna, statsmodels
- Truc quan: matplotlib, seaborn
- Utility: colorama, tabulate, joblib
- Test/quality: pytest, pytest-cov, black, flake8, isort

---

## 11) Tai lieu va notebook

- `notebooks/answer.ipynb`: Phan tich tong hop
- `notebooks/forecast.ipynb`: Thu nghiem du bao
- `knowledge/`: Luu mo ta de bai, schema, canh bao va ghi chu phan tich

---

## 12) Ket qua minh hoa (hinh san co)

Ban co the xem nhanh mot so hinh ket qua trong thu muc reports:

- `reports/optimized_forecast_comparison.png`
- `reports/feature_importance.png`
- `reports/figures/forecast_visualization.png`
- `reports/figures/feature_importance_revenue.png`

---

Neu can, co the bo sung tiep README theo huong "Quickstart cho nguoi cham" (1 lenh train + 1 lenh predict + checklist file nop).