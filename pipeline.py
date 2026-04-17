"""
============================================================
FILE CHÍNH: pipeline.py  (Main Pipeline Entry Point)
============================================================
Mục đích: Điều phối toàn bộ quá trình kiểm định và hợp nhất dữ liệu.

CÁCH CHẠY:
    python pipeline.py

    Hoặc với tùy chọn:
    python pipeline.py --thu_muc data/raw --khong_hop_nhat

LUỒNG THỰC THI (Execution Flow):
    1. Đọc tất cả file CSV từ thư mục data/raw/
    2. Kiểm định từng file → báo cáo lỗi chi tiết
    3. In bảng tóm tắt kiểm định
    4. Lưu báo cáo CSV
    5. Hợp nhất tất cả bảng theo Star Schema
    6. Lưu kết quả → data/output/du_lieu_tong_hop.csv
============================================================
"""

import sys
import io
import argparse

# Đặt stdout thành UTF-8 để hiển thị đúng ký tự tiếng Việt và emoji trên Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
from pathlib import Path
from colorama import Fore, Style, init

# Thêm thư mục gốc vào sys.path để import các module nội bộ
sys.path.insert(0, str(Path(__file__).parent))

from src.kiem_dinh import kiem_dinh_nhieu_file
from src.hop_nhat  import hop_nhat_du_lieu
from src.bao_cao   import tao_bang_tom_tat, in_bang_tom_tat, luu_bao_cao_csv, in_thong_ke_tong

init(autoreset=True)


# ──────────────────────────────────────────────────────────────
# DANH SÁCH FILE CẦN XỬ LÝ (có thể tùy chỉnh)
# ──────────────────────────────────────────────────────────────
DANH_SACH_FILE_CSV = [
    "customers.csv",
    "geography.csv",
    "products.csv",
    "promotions.csv",
    "orders.csv",
    "order_items.csv",
    "payments.csv",
    "shipments.csv",
    "reviews.csv",
    "returns.csv",
    "inventory.csv",
    "sales.csv",
    "web_traffic.csv",
]


def chay_pipeline(
    thu_muc_raw: Path,
    co_hop_nhat: bool = True,
    chi_kiem_dinh: bool = False,
) -> None:
    """
    Hàm điều phối chính của toàn bộ Data Pipeline.

    Tham số:
        thu_muc_raw   : Đường dẫn đến thư mục chứa file CSV gốc
        co_hop_nhat   : True → thực hiện bước hợp nhất dữ liệu
        chi_kiem_dinh : True → chỉ kiểm định, không hợp nhất
    """
    print(f"\n{Fore.MAGENTA}{'█'*60}")
    print("  DATA PIPELINE — KIỂM ĐỊNH & HỢP NHẤT DỮ LIỆU")
    print(f"  📁 Thư mục nguồn: {thu_muc_raw}")
    print(f"{'█'*60}{Style.RESET_ALL}")

    # ── BƯỚC 1: Thu thập danh sách file cần xử lý ────────────
    danh_sach_duong_dan = []
    for ten_file in DANH_SACH_FILE_CSV:
        duong_dan = thu_muc_raw / ten_file
        if duong_dan.exists():
            danh_sach_duong_dan.append(duong_dan)
        else:
            print(f"  {Fore.YELLOW}⚠ Không tìm thấy: {ten_file}{Style.RESET_ALL}")

    if not danh_sach_duong_dan:
        print(f"  {Fore.RED}❌ Không tìm thấy file CSV nào trong: {thu_muc_raw}{Style.RESET_ALL}")
        sys.exit(1)

    print(f"\n  📂 Tìm thấy {len(danh_sach_duong_dan)} file CSV để xử lý.")

    # ── BƯỚC 2: Kiểm định từng file ───────────────────────────
    print(f"\n{Fore.BLUE}{'═'*60}")
    print("  GIAI ĐOẠN 1: KIỂM ĐỊNH DỮ LIỆU (Data Validation)")
    print(f"{'═'*60}{Style.RESET_ALL}")

    danh_sach_bao_cao = kiem_dinh_nhieu_file(
        danh_sach_duong_dan=danh_sach_duong_dan,
        in_ra_terminal=True,
    )

    # ── BƯỚC 3: In bảng tóm tắt ──────────────────────────────
    bang_tom_tat = tao_bang_tom_tat(danh_sach_bao_cao)
    in_bang_tom_tat(bang_tom_tat)
    in_thong_ke_tong(danh_sach_bao_cao)

    # ── BƯỚC 4: Lưu báo cáo kiểm định ───────────────────────
    thu_muc_output = thu_muc_raw.parent / "output"
    duong_dan_bao_cao = luu_bao_cao_csv(bang_tom_tat, thu_muc_output)
    print(f"\n  {Fore.GREEN}💾 Báo cáo kiểm định → {duong_dan_bao_cao}{Style.RESET_ALL}")

    # ── BƯỚC 5: Hợp nhất dữ liệu (nếu được yêu cầu) ─────────
    if chi_kiem_dinh:
        print(f"\n  {Fore.CYAN}ℹ Bỏ qua bước hợp nhất (--chi_kiem_dinh).{Style.RESET_ALL}")
        return

    print(f"\n{Fore.BLUE}{'═'*60}")
    print("  GIAI ĐOẠN 2: HỢP NHẤT DỮ LIỆU (Data Merging)")
    print(f"{'═'*60}{Style.RESET_ALL}")

    bang_ket_qua = hop_nhat_du_lieu(
        thu_muc_raw=thu_muc_raw,
        ten_file_dau_ra="du_lieu_tong_hop.csv",
        in_ra_terminal=True,
    )

    # ── BƯỚC 6: In tóm tắt kết quả cuối cùng ─────────────────
    print(f"\n{Fore.MAGENTA}{'█'*60}")
    print("  ✅ PIPELINE HOÀN THÀNH!")
    print(f"  📊 Bảng tổng hợp: {len(bang_ket_qua):,} dòng × {len(bang_ket_qua.columns)} cột")
    print(f"  📁 Kết quả lưu tại: data/output/du_lieu_tong_hop.csv")
    print(f"  📋 Báo cáo lưu tại: data/output/bao_cao_kiem_dinh.csv")
    print(f"{'█'*60}{Style.RESET_ALL}\n")


def _phan_tich_tham_so() -> argparse.Namespace:
    """Phân tích tham số dòng lệnh (Command-Line Arguments)."""
    bo_phan_tich = argparse.ArgumentParser(
        description="Data Pipeline — Kiểm định và Hợp nhất dữ liệu CSV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ví dụ:
  python pipeline.py
  python pipeline.py --thu_muc data/raw
  python pipeline.py --chi_kiem_dinh
        """,
    )

    bo_phan_tich.add_argument(
        "--thu_muc",
        type=str,
        default="data/raw",
        help="Đường dẫn đến thư mục chứa file CSV (mặc định: data/raw)",
    )
    bo_phan_tich.add_argument(
        "--chi_kiem_dinh",
        action="store_true",
        help="Chỉ thực hiện kiểm định, bỏ qua bước hợp nhất",
    )

    return bo_phan_tich.parse_args()


if __name__ == "__main__":
    tham_so = _phan_tich_tham_so()

    # Xác định đường dẫn tuyệt đối
    thu_muc_goc = Path(__file__).parent
    thu_muc_raw = (thu_muc_goc / tham_so.thu_muc).resolve()

    chay_pipeline(
        thu_muc_raw=thu_muc_raw,
        co_hop_nhat=not tham_so.chi_kiem_dinh,
        chi_kiem_dinh=tham_so.chi_kiem_dinh,
    )
