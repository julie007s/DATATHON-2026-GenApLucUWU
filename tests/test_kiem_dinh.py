"""
============================================================
UNIT TESTS: test_kiem_dinh.py
============================================================
Kiểm thử tự động cho module kiem_dinh.py

CÁCH CHẠY:
    pytest tests/ -v
    pytest tests/ --cov=src --cov-report=term-missing
============================================================
"""

import sys
import pytest
import pandas as pd
import numpy as np
from pathlib import Path

# Thêm thư mục gốc vào sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.kiem_dinh import (
    kiem_tra_gia_tri_thieu,
    kiem_tra_dong_trung_lap,
    kiem_tra_tinh_toan_ven,
)


# ──────────────────────────────────────────────────────────────
# FIXTURE: Tạo dữ liệu mẫu để kiểm thử
# ──────────────────────────────────────────────────────────────

@pytest.fixture
def bang_sach():
    """DataFrame không có lỗi."""
    return pd.DataFrame({
        "product_id"  : [1, 2, 3],
        "product_name": ["A", "B", "C"],
        "price"       : [10.0, 20.0, 30.0],
        "cogs"        : [5.0, 10.0, 15.0],
    })


@pytest.fixture
def bang_co_gia_tri_thieu():
    """DataFrame có giá trị thiếu."""
    return pd.DataFrame({
        "product_id"  : [1, 2, None],
        "product_name": ["A", None, "C"],
        "price"       : [10.0, 20.0, 30.0],
    })


@pytest.fixture
def bang_co_trung_lap():
    """DataFrame có dòng trùng lặp."""
    return pd.DataFrame({
        "product_id"  : [1, 2, 1],
        "product_name": ["A", "B", "A"],
        "price"       : [10.0, 20.0, 10.0],
    })


@pytest.fixture
def bang_co_loi_kieu():
    """DataFrame có cột số chứa giá trị phi số."""
    return pd.DataFrame({
        "product_id": [1, 2, 3],
        "price"     : ["10.0", "abc", "30.0"],  # "abc" là phi số
        "cogs"      : [5.0, 10.0, 15.0],
    })


# ──────────────────────────────────────────────────────────────
# TEST: kiem_tra_gia_tri_thieu
# ──────────────────────────────────────────────────────────────

class TestKiemTraGiaTriThieu:
    def test_khong_co_gia_tri_thieu(self, bang_sach):
        ket_qua = kiem_tra_gia_tri_thieu(bang_sach)
        assert ket_qua == {}, "Bảng sạch không được có giá trị thiếu"

    def test_phat_hien_gia_tri_thieu(self, bang_co_gia_tri_thieu):
        ket_qua = kiem_tra_gia_tri_thieu(bang_co_gia_tri_thieu)
        assert "product_id"   in ket_qua
        assert "product_name" in ket_qua
        assert ket_qua["product_id"]   == 1
        assert ket_qua["product_name"] == 1

    def test_cot_day_du_khong_xuat_hien(self, bang_co_gia_tri_thieu):
        ket_qua = kiem_tra_gia_tri_thieu(bang_co_gia_tri_thieu)
        assert "price" not in ket_qua, "Cột đầy đủ không được xuất hiện trong kết quả"


# ──────────────────────────────────────────────────────────────
# TEST: kiem_tra_dong_trung_lap
# ──────────────────────────────────────────────────────────────

class TestKiemTraDongTrungLap:
    def test_khong_co_trung_lap(self, bang_sach):
        ket_qua = kiem_tra_dong_trung_lap(bang_sach)
        assert ket_qua == 0

    def test_phat_hien_trung_lap(self, bang_co_trung_lap):
        ket_qua = kiem_tra_dong_trung_lap(bang_co_trung_lap)
        assert ket_qua == 1, "Phải phát hiện đúng 1 dòng trùng lặp"

    def test_tat_ca_trung_lap(self):
        bang = pd.DataFrame({"a": [1, 1, 1], "b": ["x", "x", "x"]})
        ket_qua = kiem_tra_dong_trung_lap(bang)
        # dòng đầu không tính là duplicate, chỉ 2 dòng sau
        assert ket_qua == 2


# ──────────────────────────────────────────────────────────────
# TEST: kiem_tra_tinh_toan_ven
# ──────────────────────────────────────────────────────────────

class TestKiemTraTinhToanVen:
    def test_khong_co_loi(self, bang_sach):
        ket_qua = kiem_tra_tinh_toan_ven(bang_sach, "products.csv")
        assert ket_qua == [], "Dữ liệu hợp lệ không được có lỗi toàn vẹn"

    def test_phat_hien_loi_kieu(self, bang_co_loi_kieu):
        ket_qua = kiem_tra_tinh_toan_ven(bang_co_loi_kieu, "products.csv")
        assert len(ket_qua) == 1
        assert "price" in ket_qua[0]

    def test_file_khong_co_cau_hinh(self, bang_sach):
        # File không trong CAU_HINH_KIEU_SO → không lỗi
        ket_qua = kiem_tra_tinh_toan_ven(bang_sach, "file_la.csv")
        assert ket_qua == []
