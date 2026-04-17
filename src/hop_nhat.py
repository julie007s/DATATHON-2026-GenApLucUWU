"""
============================================================
MODULE: hop_nhat.py  (Data Merging Module)
============================================================
Mục đích: Hợp nhất nhiều DataFrame thành một bảng tổng hợp.

THUẬT NGỮ CHUYÊN NGÀNH:
  - Append (Nối chồng)     : Ghép các bảng cùng cấu trúc theo chiều dọc
                              (tăng số DÒNG, giữ nguyên số cột)
  - Join/Merge (Liên kết)  : Ghép các bảng khác cấu trúc theo chiều ngang
                              thông qua khóa chung (tăng số CỘT)
  - Left Join              : Giữ toàn bộ dòng của bảng bên trái, điền NaN
                              nếu không tìm thấy khớp bên phải
  - Primary Key (Khóa chính): Cột/tổ hợp cột định danh duy nhất mỗi bản ghi
  - Foreign Key (Khóa ngoại): Cột tham chiếu đến khóa chính của bảng khác
  - Star Schema            : Mô hình dữ liệu dạng "hình ngôi sao" với 1 bảng
                             Fact (sự kiện) trung tâm và nhiều bảng Dimension
============================================================
"""

import pandas as pd
import numpy as np
from pathlib import Path
from colorama import Fore, Style, init

init(autoreset=True)


# ────────────────────────────────────────────────────────────
# CẤU HÌNH LIÊN KẾT (Merge Strategy Config)
# ────────────────────────────────────────────────────────────
#
# Mô hình dữ liệu theo Star Schema:
#
#   [customers]─┐
#   [geography]─┤
#               ├──→ [orders] ──→ [order_items] ──→ [products]
#   [payments]──┤                      │
#   [shipments]─┘               [reviews, returns, inventory]
#
# Bảng FACT trung tâm   : orders (chứa order_id và customer_id)
# Bảng DIMENSION liên kết: theo khóa ngoại tương ứng
# ────────────────────────────────────────────────────────────

# Nhóm 1: Cùng schema → Append (nối chồng dọc)
# Ví dụ: Không có bảng cùng schema trong dataset này

# Nhóm 2: Schema khác nhau → Join theo khóa chung
# Thứ tự join: orders → order_items → products → customers
#              → payments → shipments → reviews → returns

# Định nghĩa khóa join cho từng bảng (key: tên file, value: khóa join)
KHOA_JOIN = {
    "orders.csv"     : ["order_id"],          # bảng fact trung tâm
    "order_items.csv": ["order_id"],           # FK → orders
    "products.csv"   : ["product_id"],         # FK → order_items
    "customers.csv"  : ["customer_id"],        # FK → orders
    "payments.csv"   : ["order_id"],           # FK → orders (có thể nhiều dòng)
    "shipments.csv"  : ["order_id"],           # FK → orders
    "reviews.csv"    : ["order_id", "product_id"],  # FK kép
    "returns.csv"    : ["order_id", "product_id"],  # FK kép
    "inventory.csv"  : ["product_id"],         # FK → products
    "geography.csv"  : ["zip"],               # FK → orders/customers
}


def _doc_file_csv(duong_dan: Path) -> pd.DataFrame:
    """Đọc CSV với xử lý lỗi đơn giản."""
    return pd.read_csv(duong_dan, low_memory=False)


def xac_dinh_chien_luoc(
    danh_sach_bang: dict[str, pd.DataFrame]
) -> tuple[list[str], list[str]]:
    """
    Phân loại các bảng theo chiến lược hợp nhất.

    Logic phân loại:
      - Nếu 2+ bảng có CÙNG tập hợp tên cột → Append (nối chồng)
      - Nếu các bảng có cột khóa chung → Merge (liên kết ngang)

    Trả về:
        (nhom_append, nhom_merge): Hai danh sách tên file
    """
    # Gom nhóm các file có cùng schema (cùng tập hợp cột)
    nhom_schema: dict[frozenset, list[str]] = {}
    for ten_file, bang in danh_sach_bang.items():
        schema_key = frozenset(bang.columns.tolist())
        nhom_schema.setdefault(schema_key, []).append(ten_file)

    nhom_append = []
    nhom_merge = []

    for schema_key, danh_sach in nhom_schema.items():
        if len(danh_sach) >= 2:
            nhom_append.extend(danh_sach)
        else:
            nhom_merge.extend(danh_sach)

    return nhom_append, nhom_merge


def _tinh_gop_payments(bang_payments: pd.DataFrame) -> pd.DataFrame:
    """
    Tổng hợp bảng payments: 1 order_id → 1 dòng duy nhất.
    Tránh nhân bội dòng khi join với bảng orders.
    """
    ket_qua = (
        bang_payments
        .groupby("order_id", as_index=False)
        .agg(
            tong_thanh_toan=("payment_value", "sum"),
            so_phuong_thuc=("payment_method", "nunique"),
            so_ky_tra_gop=("installments", "max"),
        )
    )
    return ket_qua


def _tinh_gop_reviews(bang_reviews: pd.DataFrame) -> pd.DataFrame:
    """Tổng hợp bảng reviews: 1 order_id → điểm đánh giá trung bình."""
    ket_qua = (
        bang_reviews
        .groupby("order_id", as_index=False)
        .agg(
            diem_danh_gia_tb=("rating", "mean"),
            so_luong_danh_gia=("rating", "count"),
        )
    )
    return ket_qua


def _tinh_gop_returns(bang_returns: pd.DataFrame) -> pd.DataFrame:
    """Tổng hợp bảng returns: 1 order_id → tổng hoàn tiền."""
    ket_qua = (
        bang_returns
        .groupby("order_id", as_index=False)
        .agg(
            tong_hoan_tien=("refund_amount", "sum"),
            so_mat_hang_tra=("return_quantity", "sum"),
            co_tra_hang=("return_id", "count"),
        )
    )
    ket_qua["co_tra_hang"] = (ket_qua["co_tra_hang"] > 0).astype(int)
    return ket_qua


def _tinh_gop_inventory(bang_inventory: pd.DataFrame) -> pd.DataFrame:
    """Tổng hợp bảng inventory: 1 product_id → chỉ số tồn kho mới nhất."""
    # Lấy snapshot mới nhất theo product_id
    ket_qua = (
        bang_inventory
        .sort_values("snapshot_date")
        .groupby("product_id", as_index=False)
        .last()
        [["product_id", "stock_on_hand", "fill_rate",
          "stockout_flag", "overstock_flag", "reorder_flag",
          "sell_through_rate"]]
    )
    # Đổi tên để tránh xung đột cột
    ket_qua = ket_qua.rename(columns={
        "stock_on_hand"    : "ton_kho_hien_tai",
        "fill_rate"        : "ti_le_dap_ung",
        "stockout_flag"    : "het_hang",
        "overstock_flag"   : "ton_du",
        "reorder_flag"     : "can_dat_lai",
        "sell_through_rate": "ti_le_ban_het",
    })
    return ket_qua


def hop_nhat_du_lieu(
    thu_muc_raw: Path,
    ten_file_dau_ra: str = "du_lieu_tong_hop.csv",
    in_ra_terminal: bool = True,
) -> pd.DataFrame:
    """
    Pipeline hợp nhất chính — Kết hợp tất cả bảng CSV thành 1 bảng tổng hợp.

    Chiến lược:
        Bước 1: Đọc tất cả các file CSV
        Bước 2: Xử lý & tổng hợp các bảng nhiều-nhiều
        Bước 3: Xây dựng bảng Fact trung tâm (orders + order_items)
        Bước 4: Left Join từng bảng Dimension vào bảng Fact
        Bước 5: Lưu kết quả ra file CSV

    Tham số:
        thu_muc_raw    : Thư mục chứa các file CSV gốc
        ten_file_dau_ra: Tên file CSV kết quả
        in_ra_terminal : Có in tiến trình không

    Trả về:
        pd.DataFrame: Bảng dữ liệu tổng hợp
    """
    if in_ra_terminal:
        print(f"\n{Fore.BLUE}{'═'*60}")
        print("  🔗  PIPELINE HỢP NHẤT DỮ LIỆU")
        print(f"{'═'*60}{Style.RESET_ALL}")

    # ── Bước 1: Đọc các bảng cần thiết ───────────────────────
    ten_cac_bang = [
        "orders.csv", "order_items.csv", "products.csv",
        "customers.csv", "payments.csv", "shipments.csv",
        "reviews.csv", "returns.csv", "inventory.csv", "geography.csv"
    ]

    cac_bang = {}
    for ten_file in ten_cac_bang:
        duong_dan = thu_muc_raw / ten_file
        if duong_dan.exists():
            cac_bang[ten_file] = _doc_file_csv(duong_dan)
            if in_ra_terminal:
                so_dong = len(cac_bang[ten_file])
                print(f"  ✔ Đọc '{ten_file}': {so_dong:,} dòng")
        else:
            if in_ra_terminal:
                print(f"  {Fore.YELLOW}⚠ Bỏ qua (không tìm thấy): {ten_file}{Style.RESET_ALL}")

    # ── Bước 2: Tổng hợp bảng nhiều-nhiều ────────────────────
    if in_ra_terminal:
        print(f"\n{Fore.CYAN}  📐 Tổng hợp bảng (Aggregation)...{Style.RESET_ALL}")

    bang_payments_gop  = _tinh_gop_payments(cac_bang["payments.csv"])
    bang_reviews_gop   = _tinh_gop_reviews(cac_bang["reviews.csv"])
    bang_returns_gop   = _tinh_gop_returns(cac_bang["returns.csv"])
    bang_inventory_gop = _tinh_gop_inventory(cac_bang["inventory.csv"])

    # ── Bước 3: Bảng Fact trung tâm (orders × order_items) ───
    if in_ra_terminal:
        print(f"\n{Fore.CYAN}  🔗 Ghép bảng Fact (Join)...{Style.RESET_ALL}")

    # Bước 3a: Join orders với order_items (1:nhiều → nhiều dòng)
    bang_fact = pd.merge(
        cac_bang["orders.csv"],
        cac_bang["order_items.csv"],
        on="order_id",
        how="left",
        suffixes=("_order", "_item"),
    )
    if in_ra_terminal:
        print(f"    orders × order_items → {len(bang_fact):,} dòng")

    # Bước 3b: Join với products (tra thông tin sản phẩm)
    bang_fact = pd.merge(
        bang_fact,
        cac_bang["products.csv"].add_prefix("sp_"),
        left_on="product_id",
        right_on="sp_product_id",
        how="left",
    ).drop(columns=["sp_product_id"], errors="ignore")
    if in_ra_terminal:
        print(f"    + products → {len(bang_fact):,} dòng")

    # ── Bước 4: Left Join từng bảng Dimension ─────────────────

    # 4a: Thông tin khách hàng
    bang_fact = pd.merge(
        bang_fact,
        cac_bang["customers.csv"].add_prefix("kh_"),
        left_on="customer_id",
        right_on="kh_customer_id",
        how="left",
    ).drop(columns=["kh_customer_id"], errors="ignore")

    # 4b: Địa lý (geography)
    kh_zip = "kh_zip" if "kh_zip" in bang_fact.columns else "zip_order"
    bang_fact = pd.merge(
        bang_fact,
        cac_bang["geography.csv"].add_prefix("dc_"),
        left_on=kh_zip,
        right_on="dc_zip",
        how="left",
    ).drop(columns=["dc_zip"], errors="ignore")

    # 4c: Thanh toán (đã tổng hợp 1:1 với order_id)
    bang_fact = pd.merge(
        bang_fact,
        bang_payments_gop,
        on="order_id",
        how="left",
    )

    # 4d: Vận chuyển
    bang_fact = pd.merge(
        bang_fact,
        cac_bang["shipments.csv"],
        on="order_id",
        how="left",
    )

    # 4e: Đánh giá
    bang_fact = pd.merge(
        bang_fact,
        bang_reviews_gop,
        on="order_id",
        how="left",
    )

    # 4f: Hoàn hàng
    bang_fact = pd.merge(
        bang_fact,
        bang_returns_gop,
        on="order_id",
        how="left",
    )
    # Điền 0 cho đơn hàng không có hoàn hàng
    bang_fact["co_tra_hang"] = bang_fact["co_tra_hang"].fillna(0).astype(int)

    # 4g: Tồn kho (theo product_id)
    bang_fact = pd.merge(
        bang_fact,
        bang_inventory_gop,
        on="product_id",
        how="left",
    )

    if in_ra_terminal:
        print(f"\n  {Fore.GREEN}✅ Bảng tổng hợp: {len(bang_fact):,} dòng × "
              f"{len(bang_fact.columns)} cột{Style.RESET_ALL}")

    # ── Bước 5: Lưu kết quả ───────────────────────────────────
    thu_muc_output = thu_muc_raw.parent / "output"
    thu_muc_output.mkdir(parents=True, exist_ok=True)

    duong_dan_luu = thu_muc_output / ten_file_dau_ra
    bang_fact.to_csv(duong_dan_luu, index=False, encoding="utf-8-sig")

    if in_ra_terminal:
        print(f"\n  {Fore.GREEN}💾 Đã lưu: {duong_dan_luu}{Style.RESET_ALL}")

    return bang_fact
