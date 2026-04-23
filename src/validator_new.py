"""
============================================================
MODULE: validator_new.py  (Data Validation Module - Updated)
============================================================
Purpose: Validate data quality for each CSV file using datatypes.yaml.
"""

import pandas as pd
import numpy as np
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

def _section_header(filename: str) -> str:
    """Return a formatted separator header for terminal output."""
    line = "─" * 60
    return f"\n{Fore.CYAN}{line}\n  📄  {filename}\n{line}{Style.RESET_ALL}"

def check_missing_values(df: pd.DataFrame) -> dict[str, int]:
    """Count missing values (NaN / NULL) per column."""
    missing_counts = df.isnull().sum()
    return missing_counts[missing_counts > 0].to_dict()

def check_duplicates(df: pd.DataFrame) -> int:
    """Count fully-duplicate rows."""
    return int(df.duplicated().sum())

def check_data_integrity(df: pd.DataFrame, filename: str) -> list[str]:
    """
    Verify that columns expected to be numeric (integer/float) or datetime
    match their intended types.
    """
    errors: list[str] = []
    
    table_name = filename.replace(".csv", "")
    table_config = DATATYPES_CONFIG.get(table_name, {})

    for col, dtype in table_config.items():
        if col not in df.columns:
            continue

        if dtype in ["integer", "float"]:
            coerced = pd.to_numeric(df[col], errors="coerce")
            original_nulls = int(df[col].isna().sum())
            coerced_nulls  = int(coerced.isna().sum())
            non_numeric_count = max(0, coerced_nulls - original_nulls)

            if non_numeric_count > 0:
                errors.append(
                    f"Column '{col}' must be {dtype} but contains "
                    f"{non_numeric_count} non-numeric value(s)."
                )
        
        elif dtype == "datetime":
            coerced = pd.to_datetime(df[col], errors="coerce")
            original_nulls = int(df[col].isna().sum())
            coerced_nulls  = int(coerced.isna().sum())
            invalid_date_count = max(0, coerced_nulls - original_nulls)

            if invalid_date_count > 0:
                errors.append(
                    f"Column '{col}' must be datetime but contains "
                    f"{invalid_date_count} invalid date value(s)."
                )

    return errors

def validate_file(path: Path, verbose: bool = True) -> dict:
    """Run a full validation suite on a single CSV file."""
    filename = path.name
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

    if verbose:
        print(_section_header(filename))
        print(f"  📊 Shape: {df.shape[0]:,} rows × {df.shape[1]} columns")

        if missing:
            print(f"  {Fore.YELLOW}⚠  Missing values:{Style.RESET_ALL}")
            for col, count in missing.items():
                pct = count / len(df) * 100
                print(f"       • {col}: {count:,} cells ({pct:.1f}%)")

        if dupes > 0:
            print(f"  {Fore.YELLOW}⚠  Duplicate rows: {dupes:,}{Style.RESET_ALL}")

        if integrity:
            print(f"  {Fore.RED}✗  Data integrity errors:{Style.RESET_ALL}")
            for err in integrity:
                print(f"       • {err}")

        if not has_issues:
            print(f"  {Fore.GREEN}✅ All checks passed — no issues found.{Style.RESET_ALL}")

    return report

def validate_files(paths: list[Path], verbose: bool = True) -> list[dict]:
    """Validate multiple CSV files and collect their reports."""
    return [validate_file(p, verbose=verbose) for p in paths]
