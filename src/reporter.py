"""
============================================================
MODULE: reporter.py  (Reporting Module)
============================================================
Purpose: Aggregate validation results into a summary table,
         print it to the terminal, and save it as a CSV.

TERMINOLOGY:
  - Summary Report : High-level overview of data quality across all files
  - Data Quality   : Degree to which data is complete, accurate, and consistent
  - KPI            : Key Performance Indicator — a measurable quality metric
============================================================
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
from colorama import Fore, Style, init
from tabulate import tabulate

init(autoreset=True)


def _format_status(is_valid: bool) -> str:
    """Convert a boolean validity flag to a human-readable status symbol."""
    return "✅ Valid" if is_valid else "⚠  Has issues"


def build_summary_table(reports: list[dict]) -> pd.DataFrame:
    """
    Build a summary DataFrame from a list of validation reports.

    Args:
        reports: List of dicts returned by validator.validate_files().

    Returns:
        pd.DataFrame with one row per file and columns:
        CSV File | Rows | Columns | Missing Values | Duplicates |
        Integrity Errors | Status
    """
    rows = []

    for r in reports:
        # Summarise missing values as "col: count; col: count" or "None"
        if r["missing_values"]:
            missing_summary = "; ".join(
                f"{col}: {cnt:,}"
                for col, cnt in r["missing_values"].items()
            )
        else:
            missing_summary = "None"

        integrity_count = len(r["integrity_errors"])

        rows.append({
            "CSV File"        : r["filename"],
            "Rows"            : f"{r['row_count']:,}",
            "Columns"         : r["col_count"],
            "Missing Values"  : missing_summary,
            "Duplicates"      : (
                f"⚠  {r['duplicates']:,}" if r["duplicates"] > 0 else "0"
            ),
            "Integrity Errors": (
                f"⚠  {integrity_count}" if integrity_count > 0 else "None"
            ),
            "Status"          : _format_status(r["is_valid"]),
        })

    return pd.DataFrame(rows)


def print_summary_table(summary: pd.DataFrame) -> None:
    """Print the summary table to the terminal with a formatted header."""
    print(f"\n{Fore.BLUE}{'═' * 60}")
    print("  📋  DATA VALIDATION SUMMARY")
    print(f"  🕐  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═' * 60}{Style.RESET_ALL}\n")

    print(tabulate(
        summary,
        headers="keys",
        tablefmt="rounded_outline",
        showindex=False,
    ))


def save_report_csv(
    summary: pd.DataFrame,
    output_dir: Path,
    filename: str = "validation_report.csv",
) -> Path:
    """
    Save the validation summary to a CSV file.

    Emoji characters are stripped before saving so the file opens cleanly
    in Excel or any plain-text tool.

    Args:
        summary    : Summary DataFrame from build_summary_table().
        output_dir : Directory where the CSV will be written (created if needed).
        filename   : Output filename (default: 'validation_report.csv').

    Returns:
        Path to the saved file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    save_path = output_dir / filename

    # Strip emoji prefixes so the CSV is plain-text friendly
    clean = summary.copy()
    emoji_prefixes = ["✅ ", "⚠  ", "✗  ", "⚠ ", "✗ "]
    for col in clean.select_dtypes(include="object").columns:
        for prefix in emoji_prefixes:
            clean[col] = clean[col].str.replace(prefix, "", regex=False)

    clean.to_csv(save_path, index=False, encoding="utf-8-sig")
    return save_path


def print_overall_stats(reports: list[dict]) -> None:
    """Print a concise overall quality summary to the terminal."""
    total   = len(reports)
    valid   = sum(1 for r in reports if r["is_valid"])
    invalid = total - valid

    print(f"\n{Fore.BLUE}{'─' * 40}{Style.RESET_ALL}")
    print("  📊 OVERALL STATS:")
    print(f"     • Files validated : {total}")
    print(f"     • {Fore.GREEN}Files passing    : {valid}{Style.RESET_ALL}")
    if invalid > 0:
        print(f"     • {Fore.YELLOW}Files with issues: {invalid}{Style.RESET_ALL}")
    print(f"{Fore.BLUE}{'─' * 40}{Style.RESET_ALL}")
