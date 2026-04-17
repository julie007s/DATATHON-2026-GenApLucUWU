"""
============================================================
MODULE: kiem_dinh.py  (Data Validation Module)
============================================================
Mục đích: Kiểm định chất lượng dữ liệu cho từng file CSV.

THUẬT NGỮ CHUYÊN NGÀNH:
  - Missing Values  : Giá trị thiếu — ô dữ liệu bị để trống (NaN/NULL)
  - Duplicates      : Dòng trùng lặp — các dòng có nội dung hoàn toàn giống nhau
  - Data Integrity  : Tính toàn vẹn dữ liệu — dữ liệu phải đúng kiểu và nhất quán
  - Schema          : Cấu trúc bảng — tập hợp tên cột và kiểu dữ liệu của bảng
  - Primary Key     : Khóa chính — cột/tổ hợp cột dùng để định danh duy nhất mỗi dòng
  - DataFrame       : Cấu trúc dữ liệu dạng bảng 2 chiều của thư viện pandas
============================================================
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional
from colorama import Fore, Style, init

# Khởi tạo colorama để tô màu terminal trên Windows
init(autoreset=True)

# ────────────────────────────────────────────
# CẤU HÌNH KIỂM ĐỊNH (Validation Config)
# ────────────────────────────────────────────
# Định nghĩa các cột phải là số (numeric) cho từng file
CAU_HINH_KIEU_SO = {
    "products.csv"   : ["price", "cogs"],
    "orders.csv"     : [],
    "order_items.csv": ["quantity", "unit_price", "discount_amount"],
    "payments.csv"   : ["payment_value", "installments"],
    "shipments.csv"  : ["shipping_fee"],
    "reviews.csv"    : ["rating"],
    "returns.csv"    : ["return_quantity", "refund_amount"],
    "inventory.csv"  : ["stock_on_hand", "units_received", "units_sold",
                         "fill_rate", "sell_through_rate"],
    "sales.csv"      : ["Revenue", "COGS"],
    "web_traffic.csv": ["sessions", "unique_visitors", "bounce_rate"],
    "promotions.csv" : ["discount_value", "min_order_value"],
    "customers.csv"  : [],
    "geography.csv"  : [],
}


def _tao_tieu_de(ten_file: str) -> str:
    """Tạo tiêu đề phân cách đẹp cho output terminal."""
    duong_ke = "─" * 60
    return f"\n{Fore.CYAN}{duong_ke}\n  📄  {ten_file}\n{duong_ke}{Style.RESET_ALL}"


def kiem_tra_gia_tri_thieu(bang_du_lieu: pd.DataFrame) -> dict:
    """
    Kiểm tra Missing Values (Giá trị thiếu) trong DataFrame.

    Tham số:
        bang_du_lieu: DataFrame cần kiểm tra

    Trả về:
        dict: {tên_cột: số_ô_trống}  — chỉ các cột có giá trị thiếu
    """
    so_gia_tri_thieu = bang_du_lieu.isnull().sum()
    # Lọc chỉ các cột CÓ giá trị thiếu (> 0)
    cac_cot_bi_thieu = so_gia_tri_thieu[so_gia_tri_thieu > 0].to_dict()
    return cac_cot_bi_thieu


def kiem_tra_dong_trung_lap(bang_du_lieu: pd.DataFrame) -> int:
    """
    Đếm số dòng trùng lặp (Duplicates) hoàn toàn trong DataFrame.

    Tham số:
        bang_du_lieu: DataFrame cần kiểm tra

    Trả về:
        int: Số lượng dòng trùng lặp
    """
    so_dong_trung = bang_du_lieu.duplicated().sum()
    return int(so_dong_trung)


def kiem_tra_tinh_toan_ven(
    bang_du_lieu: pd.DataFrame,
    ten_file: str
) -> list[str]:
    """
    Kiểm tra Data Integrity (Tính toàn vẹn dữ liệu).
    Đảm bảo các cột số (numeric) không chứa giá trị phi số.

    Tham số:
        bang_du_lieu: DataFrame cần kiểm tra
        ten_file    : Tên file để tra cứu cấu hình

    Trả về:
        list[str]: Danh sách mô tả các lỗi toàn vẹn phát hiện được
    """
    danh_sach_loi = []
    cac_cot_phai_so = CAU_HINH_KIEU_SO.get(ten_file, [])

    for ten_cot in cac_cot_phai_so:
        if ten_cot not in bang_du_lieu.columns:
            continue

        # Cố gắng chuyển cột sang dạng số; lỗi → NaN
        chuan_hoa = pd.to_numeric(bang_du_lieu[ten_cot], errors="coerce")
        so_gia_tri_sai = chuan_hoa.isna().sum() - bang_du_lieu[ten_cot].isna().sum()

        if so_gia_tri_sai > 0:
            danh_sach_loi.append(
                f"Cột '{ten_cot}' phải là số nhưng có "
                f"{so_gia_tri_sai} giá trị phi số."
            )

    return danh_sach_loi


def kiem_dinh_mot_file(
    duong_dan: Path,
    in_ra_terminal: bool = True
) -> dict:
    """
    Kiểm định toàn diện MỘT file CSV.

    Tham số:
        duong_dan      : Đường dẫn tuyệt đối đến file CSV
        in_ra_terminal : Có in báo cáo ra màn hình không

    Trả về:
        dict: Báo cáo kiểm định với các khóa:
              'ten_file', 'so_dong', 'so_cot', 'gia_tri_thieu',
              'dong_trung_lap', 'loi_toan_ven', 'hop_le'
    """
    ten_file = duong_dan.name

    # ── Đọc file CSV ──────────────────────────────────────────
    try:
        bang_du_lieu = pd.read_csv(duong_dan, low_memory=False)
    except Exception as loi_doc:
        bao_cao = {
            "ten_file"       : ten_file,
            "so_dong"        : 0,
            "so_cot"         : 0,
            "gia_tri_thieu"  : {},
            "dong_trung_lap" : 0,
            "loi_toan_ven"   : [f"❌ Không đọc được file: {loi_doc}"],
            "hop_le"         : False,
        }
        if in_ra_terminal:
            print(_tao_tieu_de(ten_file))
            print(f"  {Fore.RED}❌ Lỗi đọc file: {loi_doc}{Style.RESET_ALL}")
        return bao_cao

    # ── Thực hiện 3 bước kiểm định ────────────────────────────
    gia_tri_thieu  = kiem_tra_gia_tri_thieu(bang_du_lieu)
    dong_trung_lap = kiem_tra_dong_trung_lap(bang_du_lieu)
    loi_toan_ven   = kiem_tra_tinh_toan_ven(bang_du_lieu, ten_file)

    # ── Tổng hợp kết quả ──────────────────────────────────────
    co_loi = bool(gia_tri_thieu) or dong_trung_lap > 0 or bool(loi_toan_ven)

    bao_cao = {
        "ten_file"       : ten_file,
        "so_dong"        : len(bang_du_lieu),
        "so_cot"         : len(bang_du_lieu.columns),
        "gia_tri_thieu"  : gia_tri_thieu,
        "dong_trung_lap" : dong_trung_lap,
        "loi_toan_ven"   : loi_toan_ven,
        "hop_le"         : not co_loi,
    }

    # ── In báo cáo ra terminal ────────────────────────────────
    if in_ra_terminal:
        print(_tao_tieu_de(ten_file))
        print(f"  📊 Kích thước: {bang_du_lieu.shape[0]:,} dòng × "
              f"{bang_du_lieu.shape[1]} cột")

        if gia_tri_thieu:
            print(f"  {Fore.YELLOW}⚠ Giá trị thiếu (Missing Values):{Style.RESET_ALL}")
            for cot, so_luong in gia_tri_thieu.items():
                pct = so_luong / len(bang_du_lieu) * 100
                print(f"      • {cot}: {so_luong:,} ô ({pct:.1f}%)")

        if dong_trung_lap > 0:
            print(f"  {Fore.YELLOW}⚠ Dòng trùng lặp (Duplicates): "
                  f"{dong_trung_lap:,} dòng{Style.RESET_ALL}")

        if loi_toan_ven:
            print(f"  {Fore.RED}✗ Lỗi toàn vẹn dữ liệu (Data Integrity):{Style.RESET_ALL}")
            for loi in loi_toan_ven:
                print(f"      • {loi}")

        if not co_loi:
            print(f"  {Fore.GREEN}✅ Dữ liệu hợp lệ — Không phát hiện lỗi!{Style.RESET_ALL}")

    return bao_cao


def kiem_dinh_nhieu_file(
    danh_sach_duong_dan: list[Path],
    in_ra_terminal: bool = True
) -> list[dict]:
    """
    Kiểm định nhiều file CSV và tổng hợp báo cáo.

    Tham số:
        danh_sach_duong_dan: Danh sách đường dẫn đến các file CSV
        in_ra_terminal     : Có in báo cáo từng file không

    Trả về:
        list[dict]: Danh sách báo cáo kiểm định từng file
    """
    danh_sach_bao_cao = []

    for duong_dan in danh_sach_duong_dan:
        bao_cao = kiem_dinh_mot_file(duong_dan, in_ra_terminal=in_ra_terminal)
        danh_sach_bao_cao.append(bao_cao)

    return danh_sach_bao_cao
