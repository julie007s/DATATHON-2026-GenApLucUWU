"""
============================================================
MODULE: cleaner_new.py  (Null-Value Handler - Updated)
============================================================
Purpose: Impute (fill) missing values using datatypes.yaml.
"""

from __future__ import annotations
import pandas as pd
import yaml
from pathlib import Path
from colorama import Fore, Style, init

init(autoreset=True)

# ──────────────────────────────────────────────────────────
# CONFIG LOADER
# ──────────────────────────────────────────────────────────
def load_datatypes_config(config_path: str = "configs/datatypes.yaml") -> dict:
    """Load the datatypes configuration from a YAML file."""
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"{Fore.RED}❌ Error loading config {config_path}: {e}{Style.RESET_ALL}")
        return {}

DATATYPES_CONFIG = load_datatypes_config()

# ──────────────────────────────────────────────────────────
# PER-COLUMN FILL SENTINELS
# ──────────────────────────────────────────────────────────
COLUMN_FILL_VALUES: dict[str, object] = {
    "promo_id"      : "NO_PROMO",
    "promo_id_2"    : "NO_PROMO",
    "applicable_category" : "ALL"
}

def _report_datetime_nulls(df: pd.DataFrame) -> dict[str, int]:
    """Identify null counts in datetime columns."""
    dt_nulls: dict[str, int] = {}
    for col in df.select_dtypes(include=["datetime", "datetimetz"]).columns:
        n = int(df[col].isna().sum())
        if n > 0:
            dt_nulls[col] = n
    return dt_nulls

def clean_dataframe(df: pd.DataFrame, filename: str) -> tuple[pd.DataFrame, dict]:
    """Apply null-value filling based on datatypes.yaml."""
    df = df.copy()
    
    table_name = filename.replace(".csv", "")
    table_config = DATATYPES_CONFIG.get(table_name, {})

    numeric_filled: dict[str, int] = {}
    string_filled:  dict[str, int] = {}
    
    for col, dtype in table_config.items():
        if col not in df.columns:
            continue
            
        n_missing = int(df[col].isna().sum())
        if n_missing == 0:
            if dtype == "string":
                df[col] = df[col].astype(str).str.strip()
            continue

        if dtype in ["integer", "float"]:
            fill_val = 0 if dtype == "integer" else 0.0
            df[col] = df[col].fillna(fill_val)
            numeric_filled[col] = n_missing
            
        elif dtype == "string":
            df[col] = df[col].astype(str).where(df[col].notna(), other=pd.NA)
            df[col] = df[col].str.strip()
            
            sentinel = COLUMN_FILL_VALUES.get(col, "Unknown")
            df[col] = df[col].fillna(sentinel)
            string_filled[col] = n_missing

    datetime_nulls = _report_datetime_nulls(df)
    total_filled = sum(numeric_filled.values()) + sum(string_filled.values())

    return df, {
        "filename"      : filename,
        "numeric_filled": numeric_filled,
        "string_filled" : string_filled,
        "datetime_nulls": datetime_nulls,
        "total_filled"  : total_filled,
    }

def clean_and_save(raw_path: Path, interim_dir: Path, verbose: bool = True) -> tuple[pd.DataFrame, dict]:
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

def clean_multiple_files(raw_paths: list[Path], interim_dir: Path, verbose: bool = True) -> tuple[dict[str, pd.DataFrame], list[dict]]:
    """Clean and save multiple files."""
    cleaned_frames: dict[str, pd.DataFrame] = {}
    clean_reports:  list[dict]               = []
    for path in raw_paths:
        df_clean, report = clean_and_save(path, interim_dir, verbose=verbose)
        cleaned_frames[path.name] = df_clean
        clean_reports.append(report)
    return cleaned_frames, clean_reports
