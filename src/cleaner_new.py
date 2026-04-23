"""
============================================================
MODULE: cleaner_new.py  (Null-Value Handler + Rule Cleaner)
============================================================
Purpose: 
  1. Impute (fill) missing values using datatypes.yaml.
  2. Apply text normalization and data-quality rules from
     cleaning_rules.yaml (strip, title_case, upper_case,
     lower_case, digits_only, drop_negatives).

Fix (Audit Issue #4 — Data Quality):
  cleaning_rules.yaml was defined but never applied.
  Both column_rules and type_rules are now enforced after
  null filling.
"""

from __future__ import annotations
import re
import pandas as pd
import yaml
from pathlib import Path
from colorama import Fore, Style, init

init(autoreset=True)

# ──────────────────────────────────────────────────────────
# CONFIG PATHS
# ──────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).parent.parent
_DATATYPES_CONFIG_PATH  = _PROJECT_ROOT / "configs" / "datatypes.yaml"
_CLEANING_RULES_CONFIG_PATH = _PROJECT_ROOT / "configs" / "cleaning_rules.yaml"


# ──────────────────────────────────────────────────────────
# CONFIG LOADERS
# ──────────────────────────────────────────────────────────
def load_datatypes_config(config_path: str | Path = None) -> dict:
    """Load the datatypes configuration from a YAML file."""
    path = Path(config_path) if config_path else _DATATYPES_CONFIG_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"{Fore.RED}Error loading datatypes config {path}: {e}{Style.RESET_ALL}")
        return {}


def load_cleaning_rules_config(config_path: str | Path = None) -> dict:
    """Load cleaning rules configuration from cleaning_rules.yaml."""
    path = Path(config_path) if config_path else _CLEANING_RULES_CONFIG_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"{Fore.YELLOW}Warning: Could not load cleaning rules from {path}: {e}{Style.RESET_ALL}")
        return {}


DATATYPES_CONFIG    = load_datatypes_config()
CLEANING_RULES_CONFIG = load_cleaning_rules_config()

# ──────────────────────────────────────────────────────────
# PER-COLUMN FILL SENTINELS
# ──────────────────────────────────────────────────────────
COLUMN_FILL_VALUES: dict[str, object] = {
    "promo_id"            : "NO_PROMO",
    "promo_id_2"          : "NO_PROMO",
    "applicable_category" : "ALL",
}


# ──────────────────────────────────────────────────────────
# CLEANING RULE APPLICATORS
# ──────────────────────────────────────────────────────────
def _apply_column_rules(df: pd.DataFrame, column_rules: dict) -> tuple[pd.DataFrame, dict]:
    """
    Apply per-column text normalization rules from cleaning_rules.yaml.

    Supported rules:
      strip       : str.strip()
      title_case  : str.title()
      upper_case  : str.upper()
      lower_case  : str.lower()
      digits_only : keep only [0-9] characters

    Returns:
        (modified df, dict mapping col -> list of rules applied)
    """
    applied: dict[str, list[str]] = {}

    for col, rules in column_rules.items():
        if col not in df.columns:
            continue
        if df[col].dtype == object or pd.api.types.is_string_dtype(df[col]):
            col_applied = []
            for rule in rules:
                rule = str(rule)
                if rule == "strip":
                    df[col] = df[col].astype(str).str.strip()
                    col_applied.append("strip")
                elif rule == "title_case":
                    df[col] = df[col].astype(str).str.title()
                    col_applied.append("title_case")
                elif rule == "upper_case":
                    df[col] = df[col].astype(str).str.upper()
                    col_applied.append("upper_case")
                elif rule == "lower_case":
                    df[col] = df[col].astype(str).str.lower()
                    col_applied.append("lower_case")
                elif rule == "digits_only":
                    df[col] = df[col].astype(str).str.replace(r"\D", "", regex=True)
                    col_applied.append("digits_only")
            if col_applied:
                applied[col] = col_applied

    return df, applied


def _apply_type_rules(
    df: pd.DataFrame,
    type_rules: dict,
    table_config: dict,
) -> tuple[pd.DataFrame, int]:
    """
    Apply data-type-level cleaning rules from cleaning_rules.yaml.

    Currently handles:
      numeric_money    : drop_negatives (removes rows with negative money values)
      numeric_quantity : drop_negatives

    Returns:
        (modified df, total rows dropped)
    """
    money_rules    = type_rules.get("numeric_money", [])
    quantity_rules = type_rules.get("numeric_quantity", [])
    rows_dropped   = 0

    # Identify money columns (float type in datatypes.yaml, except dates)
    money_cols = [
        col for col, dtype in table_config.items()
        if dtype == "float" and col in df.columns
    ]
    # Identify quantity columns (integer type in datatypes.yaml)
    quantity_cols = [
        col for col, dtype in table_config.items()
        if dtype == "integer" and col in df.columns
    ]

    # Apply drop_negatives for money columns
    if any(str(r) == "drop_negatives" for r in money_rules):
        for col in money_cols:
            before = len(df)
            df = df[~(pd.to_numeric(df[col], errors="coerce") < 0)]
            rows_dropped += before - len(df)

    # Apply drop_negatives for quantity columns
    if any(str(r) == "drop_negatives" for r in quantity_rules):
        for col in quantity_cols:
            before = len(df)
            df = df[~(pd.to_numeric(df[col], errors="coerce") < 0)]
            rows_dropped += before - len(df)

    return df.reset_index(drop=True), rows_dropped


# ──────────────────────────────────────────────────────────
# NULL REPORTING
# ──────────────────────────────────────────────────────────
def _report_datetime_nulls(df: pd.DataFrame, table_config: dict) -> dict[str, int]:
    """Identify null counts in datetime columns."""
    dt_nulls: dict[str, int] = {}
    for col, dtype in table_config.items():
        if dtype == "datetime" and col in df.columns:
            n = int(df[col].isna().sum())
            if n > 0:
                dt_nulls[col] = n
    return dt_nulls


# ──────────────────────────────────────────────────────────
# MAIN CLEAN FUNCTION
# ──────────────────────────────────────────────────────────
def clean_dataframe(df: pd.DataFrame, filename: str) -> tuple[pd.DataFrame, dict]:
    """
    Apply full cleaning pipeline:
      1. Null-value filling (datatypes.yaml)
      2. Chronological sort on datetime columns
      3. Column-level text normalization (cleaning_rules.yaml → column_rules)
      4. Type-level data quality rules (cleaning_rules.yaml → type_rules)
    """
    df = df.copy()

    table_name   = filename.replace(".csv", "")
    table_config = DATATYPES_CONFIG.get(table_name, {})

    column_rules = CLEANING_RULES_CONFIG.get("column_rules", {})
    type_rules   = CLEANING_RULES_CONFIG.get("type_rules", {})

    numeric_filled: dict[str, int] = {}
    string_filled:  dict[str, int] = {}
    datetime_cols:  list[str]      = []

    # ── Step 1: Null filling (datatypes.yaml) ──────────────────────────────
    for col, dtype in table_config.items():
        if col not in df.columns:
            continue

        if dtype == "datetime":
            df[col] = pd.to_datetime(df[col], errors="coerce")
            datetime_cols.append(col)

        n_missing = int(df[col].isna().sum())
        if n_missing == 0:
            if dtype == "string":
                df[col] = df[col].astype(str).str.strip()
            continue

        if dtype in ("integer", "float"):
            fill_val = 0 if dtype == "integer" else 0.0
            df[col] = df[col].fillna(fill_val)
            numeric_filled[col] = n_missing

        elif dtype == "string":
            df[col] = df[col].astype(str).where(df[col].notna(), other=pd.NA)
            df[col] = df[col].str.strip()
            sentinel = COLUMN_FILL_VALUES.get(col, "Unknown")
            df[col] = df[col].fillna(sentinel)
            string_filled[col] = n_missing

    # ── Step 2: Chronological sort ─────────────────────────────────────────
    sort_col = None
    if datetime_cols:
        sort_col = datetime_cols[0]
        df = df.sort_values(sort_col).reset_index(drop=True)

    # ── Step 3: Column-level text normalization (cleaning_rules.yaml) ──────
    df, col_rules_applied = _apply_column_rules(df, column_rules)

    # ── Step 4: Type-level data quality rules (cleaning_rules.yaml) ────────
    df, rows_dropped = _apply_type_rules(df, type_rules, table_config)

    datetime_nulls = _report_datetime_nulls(df, table_config)
    total_filled   = sum(numeric_filled.values()) + sum(string_filled.values())

    return df, {
        "filename"         : filename,
        "numeric_filled"   : numeric_filled,
        "string_filled"    : string_filled,
        "datetime_nulls"   : datetime_nulls,
        "total_filled"     : total_filled,
        "sort_col"         : sort_col,
        "col_rules_applied": col_rules_applied,
        "rows_dropped"     : rows_dropped,
    }


# ──────────────────────────────────────────────────────────
# FILE-LEVEL INTERFACE
# ──────────────────────────────────────────────────────────
def clean_and_save(
    raw_path: Path,
    interim_dir: Path,
    verbose: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """Load raw CSV, clean, and save to interim/."""
    filename = raw_path.name
    df_raw   = pd.read_csv(raw_path, low_memory=False)
    df_clean, report = clean_dataframe(df_raw, filename)

    interim_dir.mkdir(parents=True, exist_ok=True)
    out_path = interim_dir / filename
    df_clean.to_csv(out_path, index=False, encoding="utf-8-sig")

    if verbose:
        _print_clean_report(report, out_path)

    return df_clean, report


def _print_clean_report(report: dict, saved_path: Path) -> None:
    """Print clean summary."""
    fname = report["filename"]
    total = report["total_filled"]
    print(f"\n  {Fore.CYAN}{fname}{Style.RESET_ALL}")

    if total == 0 and not report["datetime_nulls"] and not report.get("col_rules_applied") and report.get("rows_dropped", 0) == 0:
        print(f"     {Fore.GREEN}No nulls, no rules to apply.{Style.RESET_ALL}")
        _print_saved(report, saved_path)
        return

    if report["numeric_filled"]:
        print(f"     Numeric columns filled with 0 / 0.0:")
        for col, n in report["numeric_filled"].items():
            print(f"       - {col}: {n:,} cells")

    if report["string_filled"]:
        print(f"     String columns filled with sentinel:")
        for col, n in report["string_filled"].items():
            sentinel = COLUMN_FILL_VALUES.get(col, "Unknown")
            print(f"       - {col}: {n:,} cells -> \"{sentinel}\"")

    if report.get("sort_col"):
        print(f"     {Fore.CYAN}Sorted chronologically by '{report['sort_col']}'{Style.RESET_ALL}")

    if report.get("col_rules_applied"):
        print(f"     Text normalization rules applied (cleaning_rules.yaml):")
        for col, rules in report["col_rules_applied"].items():
            print(f"       - {col}: {', '.join(rules)}")

    if report.get("rows_dropped", 0) > 0:
        print(
            f"     {Fore.YELLOW}drop_negatives: {report['rows_dropped']:,} rows removed "
            f"(negative money/quantity values){Style.RESET_ALL}"
        )

    if report["datetime_nulls"]:
        print(f"     {Fore.YELLOW}Datetime NaT left unfilled (flagged):{Style.RESET_ALL}")
        for col, n in report["datetime_nulls"].items():
            print(f"       - {col}: {n:,} cells")

    _print_saved(report, saved_path)


def _print_saved(report: dict, saved_path: Path) -> None:
    print(f"     {Fore.GREEN}Saved -> {saved_path}{Style.RESET_ALL}")


def clean_multiple_files(
    raw_paths: list[Path],
    interim_dir: Path,
    verbose: bool = True,
) -> tuple[dict[str, pd.DataFrame], list[dict]]:
    """Clean and save multiple files."""
    cleaned_frames: dict[str, pd.DataFrame] = {}
    clean_reports:  list[dict]              = []
    for path in raw_paths:
        df_clean, report = clean_and_save(path, interim_dir, verbose=verbose)
        cleaned_frames[path.name] = df_clean
        clean_reports.append(report)
    return cleaned_frames, clean_reports
