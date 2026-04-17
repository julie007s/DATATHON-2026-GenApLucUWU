"""
============================================================
MODULE: bao_cao.py  (Reporting Module)
============================================================
Mục đích: Tổng hợp và xuất báo cáo kiểm định dưới dạng bảng.

THUẬT NGỮ:
  - Summary Report  : Báo cáo tóm tắt — cái nhìn tổng quát về trạng thái
                      chất lượng dữ liệu của toàn bộ dataset
  - Data Quality    : Chất lượng dữ liệu — mức độ hoàn chỉnh, chính xác,
                      nhất quán của dữ liệu
  - KPI             : Key Performance Indicator — chỉ số đo lường hiệu suất
============================================================
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
from colorama import Fore, Style, init
from tabulate import tabulate

init(autoreset=True)


def _dinh_dang_trang_thai(hop_le: bool) -> str:
    """Chuyển giá trị boolean sang biểu tượng trạng thái."""
    return "✅ Hợp lệ" if hop_le else "⚠ Có lỗi"


def tao_bang_tom_tat(danh_sach_bao_cao: list[dict]) -> pd.DataFrame:
    """
    Tạo bảng tóm tắt tổng hợp từ danh sách báo cáo kiểm định.

    Tham số:
        danh_sach_bao_cao: Danh sách dict kết quả từ kiem_dinh.py

    Trả về:
        pd.DataFrame: Bảng tóm tắt chất lượng dữ liệu
    """
    cac_dong = []

    for bao_cao in danh_sach_bao_cao:
        # Tạo chuỗi tóm tắt giá trị thiếu
        if bao_cao["gia_tri_thieu"]:
            tom_tat_thieu = "; ".join(
                f"{cot}: {so:,}"
                for cot, so in bao_cao["gia_tri_thieu"].items()
            )
        else:
            tom_tat_thieu = "Không có"

        # Tổng số lỗi toàn vẹn
        so_loi_toan_ven = len(bao_cao["loi_toan_ven"])

        cac_dong.append({
            "File CSV"          : bao_cao["ten_file"],
            "Số dòng"           : f"{bao_cao['so_dong']:,}",
            "Số cột"            : bao_cao["so_cot"],
            "Giá trị thiếu"     : tom_tat_thieu,
            "Dòng trùng lặp"    : (
                f"⚠ {bao_cao['dong_trung_lap']:,}"
                if bao_cao["dong_trung_lap"] > 0
                else "0"
            ),
            "Lỗi toàn vẹn"      : (
                f"⚠ {so_loi_toan_ven} lỗi"
                if so_loi_toan_ven > 0
                else "Không có"
            ),
            "Trạng thái"        : _dinh_dang_trang_thai(bao_cao["hop_le"]),
        })

    bang_tom_tat = pd.DataFrame(cac_dong)
    return bang_tom_tat


def in_bang_tom_tat(bang_tom_tat: pd.DataFrame) -> None:
    """In bảng tóm tắt ra terminal theo định dạng đẹp."""
    print(f"\n{Fore.BLUE}{'═'*60}")
    print("  📋  BẢNG TÓM TẮT KIỂM ĐỊNH DỮ LIỆU")
    print(f"  🕐  {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'═'*60}{Style.RESET_ALL}\n")

    print(tabulate(
        bang_tom_tat,
        headers="keys",
        tablefmt="rounded_outline",
        showindex=False,
    ))


def luu_bao_cao_csv(
    bang_tom_tat: pd.DataFrame,
    thu_muc_output: Path,
    ten_file: str = "bao_cao_kiem_dinh.csv",
) -> Path:
    """
    Lưu bảng báo cáo kiểm định ra file CSV.

    Tham số:
        bang_tom_tat  : DataFrame chứa báo cáo tóm tắt
        thu_muc_output: Thư mục lưu file
        ten_file      : Tên file đầu ra

    Trả về:
        Path: Đường dẫn đến file đã lưu
    """
    thu_muc_output.mkdir(parents=True, exist_ok=True)
    duong_dan_luu = thu_muc_output / ten_file

    # Xóa emoji trước khi lưu CSV để tránh lỗi encoding
    bang_sach = bang_tom_tat.copy()
    for cot in bang_sach.select_dtypes(include="object").columns:
        bang_sach[cot] = (
            bang_sach[cot]
            .str.replace("✅ ", "", regex=False)
            .str.replace("⚠ ", "", regex=False)
        )

    bang_sach.to_csv(duong_dan_luu, index=False, encoding="utf-8-sig")
    return duong_dan_luu


def in_thong_ke_tong(danh_sach_bao_cao: list[dict]) -> None:
    """In thống kê tổng quan cuối cùng."""
    tong_file    = len(danh_sach_bao_cao)
    file_hop_le  = sum(1 for r in danh_sach_bao_cao if r["hop_le"])
    file_co_loi  = tong_file - file_hop_le

    print(f"\n{Fore.BLUE}{'─'*40}{Style.RESET_ALL}")
    print(f"  📊 TỔNG KẾT:")
    print(f"     • Tổng số file kiểm định : {tong_file}")
    print(f"     • {Fore.GREEN}File hợp lệ             : {file_hop_le}{Style.RESET_ALL}")
    if file_co_loi > 0:
        print(f"     • {Fore.YELLOW}File có vấn đề          : {file_co_loi}{Style.RESET_ALL}")
    print(f"{Fore.BLUE}{'─'*40}{Style.RESET_ALL}")
