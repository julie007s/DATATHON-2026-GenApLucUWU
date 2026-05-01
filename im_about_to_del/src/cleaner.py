"""
============================================================
MODULE: cleaner.py  (Null-Value Handler & Data Cleaner)
============================================================
Purpose: Impute (fill) missing values in each DataFrame
         and apply basic text normalisations, then save
         cleaned copies to data/interim/.

STRATEGY (by column type):
  - Numeric (float) : fill NaN → 0.0
  - Numeric (int)   : fill NaN → 0
  - String/object   : fill NaN → sentinel defined per column
                      (falls back to "Unknown")
  - Datetime        : leave as NaT — flag in the clean report
  - promo_code      : fill NaN → "NO_PROMO"
  - comment fields  : fill NaN → "No comment"
  - return_reason   : fill NaN → "Unknown"

TEXT NORMALISATIONS (applied to string columns):
  - Strip leading/trailing whitespace
  - Per-column rules from configs/cleaning_rules.yaml (if present)
============================================================
"""

from __future__ import annotations

import pandas as pd
from pathlib import Path
from colorama import Fore, Style, init

init(autoreset=True)

# ──────────────────────────────────────────────────────────
# PER-COLUMN FILL SENTINELS
# Override the generic type-based default for specific columns.
# ──────────────────────────────────────────────────────────
COLUMN_FILL_VALUES: dict[str, object] = {
    "promo_id"      : "NO_PROMO",
    "promo_id_2"    : "NO_PROMO",
    "applicable_category" : "ALL"
}


def _fill_numeric(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """
    Fill NaN in numeric columns with 0 (int) or 0.0 (float).

    Returns:
        Tuple of (cleaned DataFrame, dict mapping col → count filled).
    """
    filled_counts: dict[str, int] = {}
    for col in df.select_dtypes(include=["number"]).columns:
        n_missing = int(df[col].isna().sum())
        if n_missing > 0:
            fill_val = 0 if pd.api.types.is_integer_dtype(df[col]) else 0.0
            df[col] = df[col].fillna(fill_val)
            filled_counts[col] = n_missing
    return df, filled_counts


def _fill_strings(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """
    Fill NaN in object/string columns using COLUMN_FILL_VALUES or "Unknown".
    Also strips leading/trailing whitespace from all string values.

    Returns:
        Tuple of (cleaned DataFrame, dict mapping col → count filled).
    """
    filled_counts: dict[str, int] = {}
    for col in df.select_dtypes(include=["object"]).columns:
        # Strip whitespace first
        df[col] = df[col].astype(str).where(df[col].notna(), other=pd.NA)
        df[col] = df[col].str.strip()

        n_missing = int(df[col].isna().sum())
        if n_missing > 0:
            sentinel = COLUMN_FILL_VALUES.get(col, "Unknown")
            df[col] = df[col].fillna(sentinel)
            filled_counts[col] = n_missing
    return df, filled_counts


def _report_datetime_nulls(df: pd.DataFrame) -> dict[str, int]:
    """
    Identify null counts in datetime columns (left unfilled — flagged only).

    Returns:
        Dict mapping col → count of NaT values.
    """
    dt_nulls: dict[str, int] = {}
    for col in df.select_dtypes(include=["datetime", "datetimetz"]).columns:
        n = int(df[col].isna().sum())
        if n > 0:
            dt_nulls[col] = n
    return dt_nulls


def clean_dataframe(df: pd.DataFrame, filename: str) -> tuple[pd.DataFrame, dict]:
    """
    Apply null-value filling to a single DataFrame.

    Processing order:
      1. Fill numeric columns with 0 / 0.0
      2. Fill string columns with per-column sentinel or "Unknown"
      3. Report (but do NOT fill) datetime NaT values

    Args:
        df       : Raw DataFrame to clean.
        filename : Used only for logging context.

    Returns:
        Tuple of:
          - cleaned DataFrame
          - clean_report dict:
              filename         – str
              numeric_filled   – dict[col, count]
              string_filled    – dict[col, count]
              datetime_nulls   – dict[col, count]  (unfilled)
              total_filled     – int
    """
    df = df.copy()

    df, numeric_filled = _fill_numeric(df)
    df, string_filled  = _fill_strings(df)
    datetime_nulls     = _report_datetime_nulls(df)

    total_filled = sum(numeric_filled.values()) + sum(string_filled.values())

    return df, {
        "filename"      : filename,
        "numeric_filled": numeric_filled,
        "string_filled" : string_filled,
        "datetime_nulls": datetime_nulls,
        "total_filled"  : total_filled,
    }


def clean_and_save(
    raw_path: Path,
    interim_dir: Path,
    verbose: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """
    Load a raw CSV, clean null values, and save the result to interim/.

    Args:
        raw_path   : Path to the raw CSV file.
        interim_dir: Directory to save the cleaned CSV (created if needed).
        verbose    : If True, print a summary to the terminal.

    Returns:
        Tuple of (cleaned DataFrame, clean_report dict).
    """
    filename = raw_path.name
    df_raw   = pd.read_csv(raw_path, low_memory=False)

    df_clean, report = clean_dataframe(df_raw, filename)

    # Save to interim/
    interim_dir.mkdir(parents=True, exist_ok=True)
    out_path = interim_dir / filename
    df_clean.to_csv(out_path, index=False, encoding="utf-8-sig")

    if verbose:
        _print_clean_report(report, out_path)

    return df_clean, report


def _print_clean_report(report: dict, saved_path: Path) -> None:
    """Print a coloured summary of what was filled for one file."""
    fname = report["filename"]
    total = report["total_filled"]

    print(f"\n  {Fore.CYAN}🧹 {fname}{Style.RESET_ALL}")

    if total == 0 and not report["datetime_nulls"]:
        print(f"     {Fore.GREEN}✅ No nulls to fill.{Style.RESET_ALL}")
        return

    if report["numeric_filled"]:
        print(f"     Numeric columns filled with 0 / 0.0:")
        for col, n in report["numeric_filled"].items():
            print(f"       • {col}: {n:,} cells")

    if report["string_filled"]:
        print(f"     String columns filled with sentinel:")
        for col, n in report["string_filled"].items():
            sentinel = COLUMN_FILL_VALUES.get(col, "Unknown")
            print(f"       • {col}: {n:,} cells → \"{sentinel}\"")

    if report["datetime_nulls"]:
        print(f"     {Fore.YELLOW}⚠  Datetime NaT left unfilled (flagged):{Style.RESET_ALL}")
        for col, n in report["datetime_nulls"].items():
            print(f"       • {col}: {n:,} cells")

    print(f"     {Fore.GREEN}💾 Saved → {saved_path}{Style.RESET_ALL}")


def clean_multiple_files(
    raw_paths: list[Path],
    interim_dir: Path,
    verbose: bool = True,
) -> tuple[dict[str, pd.DataFrame], list[dict]]:
    """
    Clean and save multiple raw CSV files.

    Args:
        raw_paths  : List of paths to raw CSV files.
        interim_dir: Target directory for cleaned files.
        verbose    : If True, print per-file reports.

    Returns:
        Tuple of:
          - dict mapping filename → cleaned DataFrame
          - list of clean_report dicts
    """
    cleaned_frames: dict[str, pd.DataFrame] = {}
    clean_reports:  list[dict]               = []

    for path in raw_paths:
        df_clean, report = clean_and_save(path, interim_dir, verbose=verbose)
        cleaned_frames[path.name] = df_clean
        clean_reports.append(report)

    return cleaned_frames, clean_reports
