# Data Pipeline — Kiểm định & Hợp nhất Dữ liệu CSV

> **Datathon** | Vai trò: Data Engineer | Ngôn ngữ: Python 3.10+

---

## 📌 Tổng quan

Pipeline này thực hiện hai giai đoạn chính:

| Giai đoạn | Mô tả |
|-----------|-------|
| **1. Kiểm định** | Phát hiện Missing Values, Duplicates, lỗi Data Integrity |
| **2. Hợp nhất** | Ghép nhiều bảng CSV theo mô hình Star Schema |

---

## 🗂 Cấu trúc Dự án

```
DATATHON/
├── pipeline.py              # Điểm vào chính — chạy file này
├── requirements.txt         # Danh sách thư viện Python cần thiết
├── .gitignore               # Các file/thư mục git sẽ bỏ qua
│
├── src/                     # Mã nguồn pipeline
│   ├── __init__.py
│   ├── kiem_dinh.py         # Module kiểm định dữ liệu
│   ├── hop_nhat.py          # Module hợp nhất dữ liệu
│   └── bao_cao.py           # Module tạo báo cáo
│
├── data/
│   ├── raw/                 # ← Đặt file CSV gốc vào đây
│   │   ├── orders.csv
│   │   ├── customers.csv
│   │   └── ...
│   └── output/              # Kết quả tự động tạo ra (git ignore)
│       ├── du_lieu_tong_hop.csv
│       └── bao_cao_kiem_dinh.csv
│
└── tests/                   # Unit tests
    └── test_kiem_dinh.py
```

---

## 🚀 Cài đặt & Chạy

### 1. Tạo môi trường ảo (Virtual Environment)

```bash
# Tạo venv
python -m venv .venv

# Kích hoạt (Windows)
.venv\Scripts\activate

# Kích hoạt (macOS/Linux)
source .venv/bin/activate
```

### 2. Cài đặt thư viện

```bash
pip install -r requirements.txt
```

### 3. Chạy pipeline

```bash
# Chạy đầy đủ (kiểm định + hợp nhất)
python pipeline.py

# Chỉ kiểm định, không hợp nhất
python pipeline.py --chi_kiem_dinh

# Chỉ định thư mục khác
python pipeline.py --thu_muc path/to/data
```

---

## 📊 Mô hình Dữ liệu (Star Schema)

```
                      [customers]
                      [geography]
                           │
[products] ──→ [order_items] ──→ [ORDERS] ←── [payments]
[inventory] ─────────────────────────────────── [shipments]
                                  ↑
                           [reviews]
                           [returns]
```

**Bảng Fact trung tâm:** `orders`  
**Bảng Dimension:** customers, products, geography, payments, shipments, reviews, returns, inventory

---

## 📋 Giải thích Thuật ngữ Chuyên ngành

| Thuật ngữ | Tiếng Việt | Giải thích |
|-----------|------------|------------|
| **Missing Values** | Giá trị thiếu | Ô dữ liệu bị để trống (NaN/NULL) |
| **Duplicates** | Dòng trùng lặp | Dòng có nội dung hoàn toàn giống nhau |
| **Data Integrity** | Toàn vẹn dữ liệu | Dữ liệu đúng kiểu và nhất quán |
| **Schema** | Cấu trúc bảng | Tập hợp tên cột và kiểu dữ liệu |
| **Primary Key** | Khóa chính | Cột định danh duy nhất mỗi bản ghi |
| **Foreign Key** | Khóa ngoại | Cột tham chiếu khóa chính bảng khác |
| **Append** | Nối chồng | Ghép bảng cùng schema theo chiều dọc |
| **Join/Merge** | Liên kết ngang | Ghép bảng qua khóa chung |
| **Left Join** | Nối trái | Giữ toàn bộ dòng bảng trái |
| **Star Schema** | Lược đồ hình sao | 1 bảng Fact + nhiều bảng Dimension |
| **Aggregation** | Tổng hợp | Gộp nhiều dòng thành 1 dòng |
| **DataFrame** | Bảng dữ liệu | Cấu trúc bảng 2D của pandas |

---

## 👥 Hướng dẫn Cộng tác (Team Collaboration)

### Git Workflow

```bash
# Clone dự án
git clone <repo-url>
cd DATATHON

# Tạo nhánh tính năng mới
git checkout -b feature/ten-tinh-nang

# Sau khi hoàn thành
git add .
git commit -m "feat: mô tả thay đổi"
git push origin feature/ten-tinh-nang
```

### Quy ước Commit Message

```
feat:  Thêm tính năng mới
fix:   Sửa lỗi
docs:  Cập nhật tài liệu
test:  Thêm/sửa unit test
refactor: Tái cấu trúc mã (không thêm tính năng/sửa lỗi)
```

> **Lưu ý:** Thư mục `data/output/` được git ignore. Mỗi thành viên chạy pipeline cục bộ để tạo kết quả.

---

## 🧪 Chạy Tests

```bash
pytest tests/ -v
pytest tests/ --cov=src --cov-report=term-missing
```

---

## 📁 Đầu ra

| File | Vị trí | Mô tả |
|------|--------|-------|
| `du_lieu_tong_hop.csv` | `data/output/` | Bảng dữ liệu đã hợp nhất hoàn chỉnh |
| `bao_cao_kiem_dinh.csv` | `data/output/` | Báo cáo tóm tắt kiểm định từng file |
