"""
============================================================
MODULE: validator.py  (Data Validation Module)
============================================================
Purpose: Validate data quality for each CSV file.

TERMINOLOGY:
  - Missing Values  : Cells with no data (NaN / NULL)
  - Duplicates      : Rows with identical content across all columns
  - Data Integrity  : Data must match the expected type (e.g. no text in numeric columns)
  - Schema          : Table structure — the set of column names and their data types
  - Primary Key     : Column(s) that uniquely identify each row
  - DataFrame       : pandas 2D tabular data structure
============================================================
"""

import pandas as pd
import numpy as np
from pathlib import Path
from colorama import Fore, Style, init

init(autoreset=True)

# ──────────────────────────────────────────────────────────
# VALIDATION CONFIG
# Maps each CSV filename → list of columns that must be numeric
# ──────────────────────────────────────────────────────────
NUMERIC_COLUMNS_BY_FILE: dict[str, list[str]] = {
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


def _section_header(filename: str) -> str:
    """Return a formatted separator header for terminal output."""
    line = "─" * 60
    return f"\n{Fore.CYAN}{line}\n  📄  {filename}\n{line}{Style.RESET_ALL}"


def check_missing_values(df: pd.DataFrame) -> dict[str, int]:
    """
    Count missing values (NaN / NULL) per column.

    Args:
        df: Input DataFrame to inspect.

    Returns:
        dict mapping column name → count of missing cells.
        Only columns with at least one missing value are included.
    """
    missing_counts = df.isnull().sum()
    return missing_counts[missing_counts > 0].to_dict()


def check_duplicates(df: pd.DataFrame) -> int:
    """
    Count fully-duplicate rows (every column identical).

    Args:
        df: Input DataFrame to inspect.

    Returns:
        Number of duplicate rows (first occurrence is not counted).
    """
    return int(df.duplicated().sum())


def check_data_integrity(df: pd.DataFrame, filename: str) -> list[str]:
    """
    Verify that columns expected to be numeric contain no non-numeric values.

    For each column listed in NUMERIC_COLUMNS_BY_FILE[filename], attempt
    coercion to numeric. Any values that cannot be converted are counted
    as integrity violations.

    Args:
        df       : Input DataFrame to inspect.
        filename : CSV filename used to look up the expected numeric columns.

    Returns:
        List of human-readable error descriptions (empty if no issues).
    """
    errors: list[str] = []
    expected_numeric = NUMERIC_COLUMNS_BY_FILE.get(filename, [])

    for col in expected_numeric:
        if col not in df.columns:
            continue

        coerced = pd.to_numeric(df[col], errors="coerce")
        # Count values that became NaN *only because* of failed conversion
        # (exclude cells that were already NaN in the original data)
        original_nulls = int(df[col].isna().sum())
        coerced_nulls  = int(coerced.isna().sum())
        non_numeric_count = max(0, coerced_nulls - original_nulls)

        if non_numeric_count > 0:
            errors.append(
                f"Column '{col}' must be numeric but contains "
                f"{non_numeric_count} non-numeric value(s)."
            )

    return errors


def validate_file(path: Path, verbose: bool = True) -> dict:
    """
    Run a full validation suite on a single CSV file.

    Checks performed:
      1. Missing values (per column)
      2. Fully-duplicate rows
      3. Data-type integrity for numeric columns

    Args:
        path    : Absolute path to the CSV file.
        verbose : If True, print a formatted report to the terminal.

    Returns:
        dict with keys:
          filename        – str
          row_count       – int
          col_count       – int
          missing_values  – dict[col, count]
          duplicates      – int
          integrity_errors– list[str]
          is_valid        – bool  (True only when all checks pass)
    """
    filename = path.name

    # ── Load CSV ──────────────────────────────────────────────
    try:
        df = pd.read_csv(path, low_memory=False)
    except Exception as exc:
        report = {
            "filename"        : filename,
            "row_count"       : 0,
            "col_count"       : 0,
            "missing_values"  : {},
            "duplicates"      : 0,
            "integrity_errors": [f"Cannot read file: {exc}"],
            "is_valid"        : False,
        }
        if verbose:
            print(_section_header(filename))
            print(f"  {Fore.RED}❌ Read error: {exc}{Style.RESET_ALL}")
        return report

    # ── Run the three checks ──────────────────────────────────
    missing   = check_missing_values(df)
    dupes     = check_duplicates(df)
    integrity = check_data_integrity(df, filename)

    has_issues = bool(missing) or dupes > 0 or bool(integrity)

    report = {
        "filename"        : filename,
        "row_count"       : len(df),
        "col_count"       : len(df.columns),
        "missing_values"  : missing,
        "duplicates"      : dupes,
        "integrity_errors": integrity,
        "is_valid"        : not has_issues,
    }

    # ── Print terminal report ─────────────────────────────────
    if verbose:
        print(_section_header(filename))
        print(f"  📊 Shape: {df.shape[0]:,} rows × {df.shape[1]} columns")

        if missing:
            print(f"  {Fore.YELLOW}⚠  Missing values:{Style.RESET_ALL}")
            for col, count in missing.items():
                pct = count / len(df) * 100
                print(f"       • {col}: {count:,} cells ({pct:.1f}%)")

        if dupes > 0:
            print(
                f"  {Fore.YELLOW}⚠  Duplicate rows: "
                f"{dupes:,}{Style.RESET_ALL}"
            )

        if integrity:
            print(f"  {Fore.RED}✗  Data integrity errors:{Style.RESET_ALL}")
            for err in integrity:
                print(f"       • {err}")

        if not has_issues:
            print(f"  {Fore.GREEN}✅ All checks passed — no issues found.{Style.RESET_ALL}")

    return report


def validate_files(paths: list[Path], verbose: bool = True) -> list[dict]:
    """
    Validate multiple CSV files and collect their reports.

    Args:
        paths   : List of absolute paths to CSV files.
        verbose : If True, print per-file reports to the terminal.

    Returns:
        List of report dicts (one per file, in input order).
    """
    return [validate_file(p, verbose=verbose) for p in paths]
