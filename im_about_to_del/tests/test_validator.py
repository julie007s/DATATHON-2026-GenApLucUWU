"""
============================================================
UNIT TESTS: test_validator.py
============================================================
Tests for src/validator.py

HOW TO RUN:
    pytest tests/ -v
    pytest tests/ --cov=src --cov-report=term-missing
============================================================
"""

import sys
import pytest
import pandas as pd
import numpy as np
from pathlib import Path

# Add project root to sys.path so imports resolve correctly
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.validator import (
    check_missing_values,
    check_duplicates,
    check_data_integrity,
)


# ──────────────────────────────────────────────────────────
# FIXTURES — sample DataFrames used across multiple tests
# ──────────────────────────────────────────────────────────

@pytest.fixture
def df_clean():
    """A perfectly clean DataFrame with no issues."""
    return pd.DataFrame({
        "product_id"  : [1, 2, 3],
        "product_name": ["Alpha", "Beta", "Gamma"],
        "price"       : [10.0, 20.0, 30.0],
        "cogs"        : [5.0, 10.0, 15.0],
    })


@pytest.fixture
def df_with_missing():
    """DataFrame that has NaN in two columns."""
    return pd.DataFrame({
        "product_id"  : [1, 2, None],
        "product_name": ["Alpha", None, "Gamma"],
        "price"       : [10.0, 20.0, 30.0],
    })


@pytest.fixture
def df_with_duplicates():
    """DataFrame where one row is a complete duplicate."""
    return pd.DataFrame({
        "product_id"  : [1, 2, 1],
        "product_name": ["Alpha", "Beta", "Alpha"],
        "price"       : [10.0, 20.0, 10.0],
    })


@pytest.fixture
def df_with_bad_types():
    """DataFrame where a numeric column contains a non-numeric string."""
    return pd.DataFrame({
        "product_id": [1, 2, 3],
        "price"     : ["10.0", "abc", "30.0"],   # "abc" is non-numeric
        "cogs"      : [5.0, 10.0, 15.0],
    })


# ──────────────────────────────────────────────────────────
# TEST: check_missing_values
# ──────────────────────────────────────────────────────────

class TestCheckMissingValues:
    def test_clean_df_returns_empty_dict(self, df_clean):
        result = check_missing_values(df_clean)
        assert result == {}, "A clean DataFrame should return no missing values"

    def test_detects_missing_in_two_columns(self, df_with_missing):
        result = check_missing_values(df_with_missing)
        assert "product_id"   in result, "product_id has one NaN — should appear"
        assert "product_name" in result, "product_name has one NaN — should appear"
        assert result["product_id"]   == 1
        assert result["product_name"] == 1

    def test_full_column_not_in_result(self, df_with_missing):
        result = check_missing_values(df_with_missing)
        assert "price" not in result, "Fully-populated columns must not appear in result"


# ──────────────────────────────────────────────────────────
# TEST: check_duplicates
# ──────────────────────────────────────────────────────────

class TestCheckDuplicates:
    def test_clean_df_returns_zero(self, df_clean):
        assert check_duplicates(df_clean) == 0

    def test_detects_one_duplicate(self, df_with_duplicates):
        result = check_duplicates(df_with_duplicates)
        assert result == 1, "Expected exactly 1 duplicate row"

    def test_all_rows_identical(self):
        df = pd.DataFrame({"a": [1, 1, 1], "b": ["x", "x", "x"]})
        # The first occurrence is NOT counted as a duplicate
        assert check_duplicates(df) == 2

    def test_no_false_positives_with_partial_match(self):
        """Rows that share some — but not all — column values are not duplicates."""
        df = pd.DataFrame({
            "a": [1, 1],
            "b": ["x", "y"],   # column b differs
        })
        assert check_duplicates(df) == 0


# ──────────────────────────────────────────────────────────
# TEST: check_data_integrity
# ──────────────────────────────────────────────────────────

class TestCheckDataIntegrity:
    def test_clean_df_returns_no_errors(self, df_clean):
        result = check_data_integrity(df_clean, "products.csv")
        assert result == [], "A clean DataFrame should have no integrity errors"

    def test_detects_non_numeric_value(self, df_with_bad_types):
        result = check_data_integrity(df_with_bad_types, "products.csv")
        assert len(result) == 1, "Expected exactly one integrity error"
        assert "price" in result[0], "Error message should mention the 'price' column"

    def test_unknown_file_returns_no_errors(self, df_clean):
        """Files not in NUMERIC_COLUMNS_BY_FILE should never raise errors."""
        result = check_data_integrity(df_clean, "unknown_file.csv")
        assert result == []

    def test_non_numeric_count_never_negative(self):
        """
        Guard against negative counts: if a column is entirely NaN in the
        original data, the coerced NaN count should never exceed the original.
        """
        df = pd.DataFrame({"price": [None, None, None], "cogs": [1.0, 2.0, 3.0]})
        result = check_data_integrity(df, "products.csv")
        # All NaNs are original — zero non-numeric violations expected
        assert result == []
