# Project Structure Report — DATATHON-2026-GenApLucUWU

> Generated: 2026-04-23  
> Workspace root: `d:\DATATHON-2026-GenApLucUWU`

---

## 1. Tổng quan dự án

Dự án tham gia cuộc thi **DATATHON 2026: THE GRIDBREAKER** do VinTelligence & VinUniversity Data Science and AI Club tổ chức. Mục tiêu chính là xây dựng pipeline xử lý dữ liệu e-commerce (thời trang Việt Nam, 2012–2022) và dự báo doanh thu (`Revenue`) + giá vốn hàng bán (`COGS`) cho giai đoạn 2023-01-01 đến 2024-07-01.

**Ngôn ngữ:** Python 3.10+  
**Framework ML:** XGBoost  
**Orchestration:** `pipeline.py` (single-entry, multi-stage)

---

## 2. Cây thư mục đầy đủ (tới lá)

```
DATATHON-2026-GenApLucUWU/
│
├── pipeline.py                            ← Entry point chính của toàn bộ pipeline
├── README.md                              ← Hướng dẫn cài đặt & chạy dự án
├── requirements.txt                       ← Danh sách thư viện Python
├── report.md                              ← File báo cáo này
│
├── configs/
│   ├── cleaning_rules.yaml                ← Quy tắc làm sạch dữ liệu theo cột/kiểu
│   ├── datatypes.yaml                     ← Khai báo kiểu dữ liệu cho từng bảng
│   ├── encoding.yaml                      ← Cấu hình target encoding
│   └── features.yaml                      ← Quy tắc feature engineering
│
├── data/
│   ├── raw/                               ← Dữ liệu gốc (không chỉnh sửa)
│   │   ├── baseline.ipynb                 ← Notebook baseline cuộc thi
│   │   ├── customers.csv                  ← 121,930 khách hàng
│   │   ├── geography.csv                  ← 39,948 mã bưu chính
│   │   ├── inventory.csv                  ← 60,247 bản ghi tồn kho (theo tháng)
│   │   ├── orders.csv                     ← 646,945 đơn hàng
│   │   ├── order_items.csv                ← 714,669 dòng chi tiết đơn
│   │   ├── payments.csv                   ← 646,945 thanh toán (1:1 với orders)
│   │   ├── products.csv                   ← 2,412 sản phẩm
│   │   ├── promotions.csv                 ← 50 chiến dịch khuyến mãi
│   │   ├── returns.csv                    ← 39,939 bản ghi trả hàng
│   │   ├── reviews.csv                    ← 113,551 đánh giá
│   │   ├── sales.csv                      ← 3,833 ngày doanh thu (train set)
│   │   ├── sample_submission.csv          ← 548 ngày cần dự báo (test set)
│   │   ├── shipments.csv                  ← 566,067 bản ghi vận chuyển
│   │   └── web_traffic.csv                ← 3,652 bản ghi lưu lượng web
│   │
│   ├── interim/                           ← Dữ liệu sau bước validate + clean
│   │   ├── customers.csv
│   │   ├── geography.csv
│   │   ├── inventory.csv
│   │   ├── orders.csv
│   │   ├── order_items.csv
│   │   ├── payments.csv
│   │   ├── products.csv
│   │   ├── promotions.csv
│   │   ├── returns.csv
│   │   ├── reviews.csv
│   │   ├── sales.csv
│   │   ├── shipments.csv
│   │   └── web_traffic.csv
│   │
│   ├── output/                            ← Kết quả cuối cùng
│   │   ├── encoded_master.parquet         ← Master table sau target encoding
│   │   ├── featured_table.parquet         ← Master table sau feature engineering
│   │   ├── master_table.csv               ← Bảng tổng hợp sau merge (Star Schema)
│   │   └── validation_report.csv          ← Báo cáo chất lượng dữ liệu
│   │
│   ├── lookups/                           ← (dự phòng, hiện rỗng)
│   ├── processed/                         ← (dự phòng, hiện rỗng)
│   └── quarantine/                        ← (dự phòng, dành cho dữ liệu lỗi)
│
├── knowledge/
│   ├── agent.md                           ← Hướng dẫn cho visualization agent
│   ├── DeThi.md                           ← Đề thi gốc (tiếng Việt)
│   ├── reason.md                          ← Phân tích nguyên nhân các lỗi pipeline
│   ├── schema.md                          ← Schema đầy đủ và quan hệ bảng
│   └── warning.md                         ← Cảnh báo chất lượng dữ liệu
│
├── logs/
│   └── pipeline.log                       ← Log thực thi pipeline (DEBUG level)
│
├── models/
│   ├── advanced_encoders.joblib           ← Encoder đã train (category, city)
│   ├── xgboost_cogs_model.joblib          ← Mô hình XGBoost dự báo COGS
│   └── xgboost_revenue_model.joblib       ← Mô hình XGBoost dự báo Revenue
│
├── notebooks/
│   ├── answer.ipynb                       ← Notebook phân tích chính
│   └── Hiulaptop.ipynb                    ← Notebook phân tích phụ
│
├── reports/
│   ├── feature_importance.png             ← Biểu đồ feature importance
│   ├── data_profiles/                     ← (dự phòng cho profiling report)
│   └── figures/                           ← (dự phòng cho biểu đồ)
│
├── scratch/
│   ├── analyze_nulls.py                   ← Script khám phá giá trị null
│   └── audit_dates.py                     ← Script kiểm tra phạm vi ngày
│
├── scripts/                               ← (dự phòng, hiện rỗng)
│
├── src/
│   ├── __init__.py                        ← Package marker
│   ├── cleaner.py                         ← Module làm sạch null (phiên bản gốc)
│   ├── cleaner_new.py                     ← Module làm sạch nâng cao (dùng YAML)
│   ├── encoder.py                         ← Target encoding chống data leakage
│   ├── featurizer.py                      ← Feature engineering từ YAML rules
│   ├── logger.py                          ← Thiết lập logger (file + console)
│   ├── merger.py                          ← Merge Star Schema → master_table
│   ├── predictor.py                       ← Sinh file submission (recursive forecast)
│   ├── reporter.py                        ← Tổng hợp validation report
│   ├── trainer.py                         ← Huấn luyện XGBoost (TimeSeriesSplit)
│   ├── validator.py                       ← Kiểm tra chất lượng dữ liệu (gốc)
│   └── validator_new.py                   ← Kiểm tra chất lượng dùng YAML
│
└── tests/
    └── test_validator.py                  ← Unit test cho src/validator.py
```

---

## 3. Luồng thực thi Pipeline

```
data/raw/*.csv
     │
     ▼ Stage 1 — Validation (src/validator_new.py)
     │  • Kiểm tra missing values, duplicates, data integrity (config-driven)
     │  • Xuất: data/output/validation_report.csv
     │
     ▼ Stage 2 — Cleaning (src/cleaner_new.py)
     │  • Impute null theo datatypes.yaml + cleaning_rules.yaml
     │  • Strip whitespace, chuẩn hoá text
     │  • Xuất: data/interim/*.csv
     │
     ▼ Stage 2.5 — Encoding (src/encoder.py)
     │  • Target encoding cho category, city
     │  • Expanding window: chỉ dùng dữ liệu ngày trước (chống leakage)
     │  • Xuất: models/advanced_encoders.joblib
     │
     ▼ Stage 3 — Merging (src/merger.py)
     │  • Star Schema: fact = order_items, dims = tất cả bảng còn lại
     │  • LEFT JOIN để giữ toàn bộ fact rows
     │  • Xuất: data/output/master_table.csv
     │
     ▼ Stage 4 — Feature Engineering (src/featurizer.py)
     │  • Row-level: is_promotion, delivery_days, is_low_stock, ...
     │  • Daily-level: day_of_week, month, year, lag features, rolling means
     │  • Xoá features có nguy cơ leakage (daily_order_count, sessions, ...)
     │  • Xuất: data/output/featured_table.parquet
     │
     ▼ Stage 5 — Training (src/trainer.py)
     │  • TimeSeriesSplit (5 folds) → báo cáo MAE, RMSE, R² mỗi fold
     │  • XGBoost: n_estimators=1000, lr=0.05, max_depth=5, seed=42
     │  • Xuất: models/xgboost_revenue_model.joblib
     │          models/xgboost_cogs_model.joblib
     │
     ▼ Stage 6 — Prediction (src/predictor.py)
     │  • Recursive forecasting cho các lag target
     │  • Forward-fill cho exogenous lags
     │  • Xuất: data/output/submission.csv
     │
     ▼ Báo cáo (src/reporter.py)
        • In summary table ra terminal + lưu CSV
```

**Chạy pipeline:**
```bash
python pipeline.py                            # Toàn bộ pipeline
python pipeline.py --validate_only            # Chỉ validate
python pipeline.py --train                    # Bao gồm training
python pipeline.py --predict                  # Sinh submission
python pipeline.py --train_until 2022-01-01   # Custom train/test split
```

---

## 4. Mô tả chi tiết từng module

### 4.1 `configs/`

| File | Mục đích |
|------|----------|
| `cleaning_rules.yaml` | Quy tắc per-column: `strip`, `title_case`, `upper_case`, `lower_case`, `digits_only`, `drop_negatives`. Default fills: string→"Unknown", int→0, float→0.0, promo_code→"NO_PROMO" |
| `datatypes.yaml` | Khai báo kiểu (`string`, `integer`, `float`, `datetime`) cho 16 bảng. Dùng bởi `validator_new.py` và `cleaner_new.py` |
| `encoding.yaml` | `columns: [category, city]`, `target_col: line_revenue`, `smoothing_weight: 10` |
| `features.yaml` | Danh sách features row-level và daily-level; liệt kê features bị xoá để tránh leakage |

### 4.2 `src/`

| Module | Vai trò | Đầu vào | Đầu ra |
|--------|---------|---------|--------|
| `logger.py` | Setup logger file + console | — | `logs/pipeline.log` |
| `validator.py` | Validate (hardcoded column list) | `data/raw/*.csv` | list of dicts |
| `validator_new.py` | Validate dùng `datatypes.yaml` | `data/raw/*.csv` + YAML | list of dicts |
| `cleaner.py` | Impute null (hardcoded rules) | DataFrame | DataFrame cleaned |
| `cleaner_new.py` | Impute + normalize dùng YAML | DataFrame + YAML | DataFrame cleaned |
| `reporter.py` | Tổng hợp & xuất validation report | list of dicts | `validation_report.csv` |
| `merger.py` | LEFT JOIN Star Schema | `data/interim/*.csv` | `master_table.csv` |
| `encoder.py` | Target encoding leak-free | `master_table.csv` + YAML | `encoded_master.parquet`, `.joblib` |
| `featurizer.py` | Feature engineering từ YAML | `encoded_master.parquet` + YAML | `featured_table.parquet` |
| `trainer.py` | Train XGBoost TimeSeriesSplit | `featured_table.parquet` | `*_model.joblib` |
| `predictor.py` | Recursive forecast + submission | `.joblib` + `featured_table.parquet` | `submission.csv` |

### 4.3 `data/`

| Thư mục | Nội dung |
|---------|----------|
| `raw/` | 14 file CSV gốc (bất biến) + `baseline.ipynb` |
| `interim/` | 13 file CSV sau validate + clean |
| `output/` | `master_table.csv`, `encoded_master.parquet`, `featured_table.parquet`, `validation_report.csv`, `submission.csv` |
| `lookups/`, `processed/`, `quarantine/` | Placeholder (hiện chỉ có `.gitkeep`) |

### 4.4 `knowledge/`

| File | Nội dung |
|------|----------|
| `DeThi.md` | Đề thi gốc: mô tả dữ liệu, câu hỏi trắc nghiệm, yêu cầu EDA & forecasting |
| `schema.md` | Schema thực tế từ dữ liệu: số dòng, kiểu dữ liệu, nullable, giá trị categorical, quan hệ FK |
| `reason.md` | 7 lỗi pipeline được phân tích nguyên nhân: BOM header, join bị skip, web_traffic không được merge, duplicate columns, logic `primary_product_id` sai, data leakage từ inventory |
| `warning.md` | 6 cảnh báo chất lượng dữ liệu: 564 shipment thiếu, 80 returned không có return record, leakage từ inventory snapshot, đơn đa sản phẩm bị mất chi tiết, thiếu region/promotions/web_traffic trong master table |
| `agent.md` | Hướng dẫn cho visualization agent: cách đọc dữ liệu, quy tắc code, quan hệ bảng, phạm vi thời gian |

### 4.5 `models/`

| File | Nội dung |
|------|----------|
| `advanced_encoders.joblib` | Target encoder đã fit cho `category` và `city` |
| `xgboost_revenue_model.joblib` | XGBoost trained, dự báo Revenue |
| `xgboost_cogs_model.joblib` | XGBoost trained, dự báo COGS |

### 4.6 `notebooks/`

| File | Nội dung |
|------|----------|
| `answer.ipynb` | Notebook phân tích chính (trả lời câu hỏi cuộc thi) |
| `Hiulaptop.ipynb` | Notebook phân tích phụ |

### 4.7 `tests/`

| File | Nội dung |
|------|----------|
| `test_validator.py` | Unit tests cho `src/validator.py`: `TestCheckMissingValues` (3 test cases) kiểm tra detect null, skip clean columns |

### 4.8 `scratch/`

| File | Nội dung |
|------|----------|
| `analyze_nulls.py` | Script khám phá nhanh null values trong raw data |
| `audit_dates.py` | Script kiểm tra phạm vi ngày và tính nhất quán thời gian |

---

## 5. Dữ liệu đầu vào (Raw)

| File | Lớp | Số dòng | Mô tả ngắn |
|------|-----|--------:|------------|
| `products.csv` | Master | 2,412 | Danh mục sản phẩm (4 category, 8 segment) |
| `customers.csv` | Master | 121,930 | Khách hàng (gender, age_group, acquisition_channel) |
| `promotions.csv` | Master | 50 | Chiến dịch khuyến mãi |
| `geography.csv` | Master | 39,948 | Mã bưu chính — region (East/Central/West) |
| `orders.csv` | Transaction | 646,945 | Đơn hàng (order_status, payment_method, device_type) |
| `order_items.csv` | Transaction | 714,669 | Chi tiết sản phẩm trong đơn (38.7% có promo_id) |
| `payments.csv` | Transaction | 646,945 | Thanh toán (1:1 với orders) |
| `shipments.csv` | Transaction | 566,067 | Vận chuyển (chỉ cho delivered/returned/shipped) |
| `returns.csv` | Transaction | 39,939 | Trả hàng (5 lý do) |
| `reviews.csv` | Transaction | 113,551 | Đánh giá (~17% orders) |
| `sales.csv` | Analytical | 3,833 | Train set: Revenue + COGS theo ngày |
| `sample_submission.csv` | Analytical | 548 | Test set: 2023-01-01 → 2024-07-01 |
| `inventory.csv` | Operational | 60,247 | Tồn kho cuối tháng |
| `web_traffic.csv` | Operational | 3,652 | Traffic web theo nguồn (bắt đầu 2013-01-01) |

---

## 6. Dependencies (`requirements.txt`)

| Nhóm | Thư viện |
|------|----------|
| Data | `pandas>=2.0`, `numpy>=1.24`, `pyarrow>=12.0` |
| Config | `PyYAML>=6.0` |
| ML | `xgboost>=1.7`, `scikit-learn>=1.2`, `joblib>=1.2` |
| Viz | `matplotlib>=3.7`, `seaborn>=0.12` |
| CLI/Format | `colorama>=0.4.6`, `tabulate>=0.9`, `openpyxl>=3.1` |
| Dev/Test | `pytest>=7.4`, `pytest-cov>=4.1`, `black>=23`, `flake8>=6.1`, `isort>=5.12` |

---

## 7. Các vấn đề đã biết (Known Issues)

| # | Vấn đề | Mức độ | Trạng thái |
|---|--------|--------|-----------|
| 1 | BOM header (`\ufefforder_id`) do `encoding="utf-8-sig"` | Cao | Đã ghi nhận trong `reason.md` |
| 2 | Geography join bị skip (tìm cột `province` không tồn tại) | Cao | Đã ghi nhận |
| 3 | Promotions join bị skip (tìm cột `promo_code` không tồn tại) | Cao | Đã ghi nhận |
| 4 | Web traffic không được merge vào master table | Trung bình | Đã ghi nhận |
| 5 | Duplicate columns (`zip` vs `zip_dim`, `payment_method` vs `payment_method_dim`) | Thấp | Đã ghi nhận |
| 6 | `primary_product_id` logic sai (dùng `mode()` thay vì max revenue) | Trung bình | Đã ghi nhận |
| 7 | Data leakage từ inventory snapshot (tất cả orders dùng snapshot mới nhất) | Cao | Đã ghi nhận |
| 8 | 564 shipment records thiếu ship_date | Thấp | Đã ghi nhận |
| 9 | `total_item_revenue == total_payment` (100% giống nhau) | Trung bình | Đang theo dõi |

---

## 8. Mối quan hệ bảng (Star Schema)

```
                    geography (zip PK)
                         ▲
                    FK: zip
customers ──────────── orders (order_id PK)
(customer_id PK)           │
                   ┌───────┼────────────────┐
                   │       │                │
              order_items  payments (1:1)  shipments
              (fact table) (order_id FK)  (order_id FK)
                   │
           ┌───────┼───────────┐
           │                   │
        products            promotions
     (product_id PK)       (promo_id PK)
           │
       inventory
    (product_id FK)

reviews ──► orders, products, customers (FK)
returns ──► orders, products (FK)
```

---

*Báo cáo được tạo tự động từ việc phân tích toàn bộ workspace.*
