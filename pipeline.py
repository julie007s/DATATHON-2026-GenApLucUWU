"""
============================================================
FILE: pipeline.py  (Main Pipeline Entry Point)
============================================================
Purpose: Orchestrate the full data validation, cleaning,
         and merging workflow.

HOW TO RUN:
    python pipeline.py

    With options:
    python pipeline.py --data_dir data/raw --validate_only

EXECUTION FLOW:
    1. Discover CSV files in data/raw/
    2. Validate each file  → print per-file report
    3. Print + save validation summary table
    4. Clean null values   → save cleaned copies to data/interim/
    5. Merge all tables    → save data/output/master_table.csv
    6. Print final summary
============================================================
"""

import sys
import io
import argparse

# Set stdout to UTF-8 so emoji and special characters display correctly on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from pathlib import Path
from colorama import Fore, Style, init

# Make sure the project root is on sys.path so internal imports work
sys.path.insert(0, str(Path(__file__).parent))

# --- NEW VERSION (Uses datatypes.yaml) ---
from src.validator_new import validate_files
from src.cleaner_new   import clean_multiple_files
from src.featurizer    import run_featurization
from src.trainer       import train_revenue_model
from src.predictor     import generate_submission

# --- ORIGINAL VERSION (Hardcoded) ---
# from src.validator import validate_files
# from src.cleaner   import clean_multiple_files

from src.reporter  import build_summary_table, print_summary_table, save_report_csv, print_overall_stats
from src.merger    import merge_tables
from src.logger    import logger

init(autoreset=True)

# ──────────────────────────────────────────────────────────
# CSV FILES TO PROCESS
# Remove or comment-out any file that is not present.
# ──────────────────────────────────────────────────────────
CSV_FILES = [
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


def run_pipeline(
    raw_dir: Path,
    validate_only: bool = False,
    train: bool = False,
    predict: bool = False,
) -> None:
    """
    Main orchestrator for the data pipeline.

    Args:
        raw_dir       : Absolute path to the directory containing raw CSV files.
        validate_only : If True, skip cleaning and merging steps.
    """
    logger.info(f"\n{'█' * 60}")
    logger.info("  DATA PIPELINE — VALIDATE · CLEAN · MERGE · FEATURE · TRAIN")
    logger.info(f"  📁 Source directory: {raw_dir}")
    logger.info(f"{'█' * 60}")

    # ── STEP 1: Collect existing CSV paths ────────────────────
    csv_paths: list[Path] = []
    for name in CSV_FILES:
        path = raw_dir / name
        if path.exists():
            csv_paths.append(path)
        else:
            print(f"  {Fore.YELLOW}⚠  Not found (skipped): {name}{Style.RESET_ALL}")

    if not csv_paths:
        print(f"  {Fore.RED}❌ No CSV files found in: {raw_dir}{Style.RESET_ALL}")
        sys.exit(1)

    print(f"\n  📂 Found {len(csv_paths)} CSV file(s) to process.")

    # ── STEP 2: Validate ──────────────────────────────────────
    print(f"\n{Fore.BLUE}{'═' * 60}")
    print("  STAGE 1: DATA VALIDATION")
    print(f"{'═' * 60}{Style.RESET_ALL}")

    reports = validate_files(csv_paths, verbose=True)

    # ── STEP 3: Print + save validation summary ───────────────
    summary = build_summary_table(reports)
    print_summary_table(summary)
    print_overall_stats(reports)

    output_dir = raw_dir.parent / "output"
    report_path = save_report_csv(summary, output_dir)
    print(f"\n  {Fore.GREEN}💾 Validation report → {report_path}{Style.RESET_ALL}")

    if validate_only:
        print(f"\n  {Fore.CYAN}ℹ  --validate_only flag set. Skipping clean + merge.{Style.RESET_ALL}")
        return

    # ── STEP 4: Clean null values ─────────────────────────────
    print(f"\n{Fore.BLUE}{'═' * 60}")
    print("  STAGE 2: NULL-VALUE CLEANING")
    print(f"{'═' * 60}{Style.RESET_ALL}")

    interim_dir = raw_dir.parent / "interim"
    _cleaned_frames, _clean_reports = clean_multiple_files(
        csv_paths, interim_dir, verbose=True
    )

    total_cells_filled = sum(r["total_filled"] for r in _clean_reports)
    print(
        f"\n  {Fore.GREEN}✅ Cleaning complete — "
        f"{total_cells_filled:,} null cell(s) filled across all files.{Style.RESET_ALL}"
    )

    # ── STEP 5: Merge into master table ───────────────────────
    master = merge_tables(
        interim_dir=interim_dir,
        output_dir=output_dir,
        output_filename="master_table.csv",
        verbose=True,
    )

    # ── STEP 6: Feature Engineering (Daily Aggregation) ──────
    logger.info(f"\n{Fore.BLUE}{'═' * 60}")
    logger.info("  STAGE 3: FEATURE ENGINEERING")
    logger.info(f"{'═' * 60}{Style.RESET_ALL}")
    
    feature_table = run_featurization(
        master_table_path=output_dir / "master_table.csv",
        raw_dir=raw_dir,
        output_dir=output_dir,
        verbose=True
    )

    # ── STEP 7: Training ──────────────────────────────────────
    if train:
        logger.info(f"\n{Fore.BLUE}{'═' * 60}")
        logger.info("  STAGE 4: MODEL TRAINING")
        logger.info(f"{'═' * 60}{Style.RESET_ALL}")
        
        train_revenue_model(
            feature_table_path=output_dir / "processed_features.csv",
            model_output_dir=raw_dir.parent.parent / "models",
            report_output_dir=raw_dir.parent.parent / "reports",
            verbose=True
        )

    # ── STEP 8: Prediction ────────────────────────────────────
    if predict:
        logger.info(f"\n{Fore.BLUE}{'═' * 60}")
        logger.info("  STAGE 5: PREDICTION")
        logger.info(f"{'═' * 60}{Style.RESET_ALL}")
        
        generate_submission(
            model_path=raw_dir.parent.parent / "models/xgboost_revenue_model.joblib",
            feature_table_path=output_dir / "processed_features.csv",
            sample_submission_path=raw_dir / "sample_submission.csv",
            output_dir=output_dir,
            verbose=True
        )

    # ── STEP 9: Final summary ─────────────────────────────────
    logger.info(f"\n{Fore.MAGENTA}{'█' * 60}")
    logger.info("  ✅ PIPELINE COMPLETE!")
    logger.info(f"  📊 Features saved : data/output/processed_features.csv")
    if predict:
        logger.info(f"  📄 Submission     : data/output/submission.csv")
    logger.info(f"{'█' * 60}{Style.RESET_ALL}\n")


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Data Pipeline — Validate, Clean, and Merge CSV files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pipeline.py
  python pipeline.py --data_dir data/raw
  python pipeline.py --validate_only
        """,
    )
    parser.add_argument(
        "--data_dir",
        type=str,
        default="data/raw",
        help="Path to the directory containing raw CSV files (default: data/raw)",
    )
    parser.add_argument(
        "--validate_only",
        action="store_true",
        help="Run validation only — skip null cleaning and table merging",
    )
    parser.add_argument(
        "--train",
        action="store_true",
        help="Trigger XGBoost model training",
    )
    parser.add_argument(
        "--predict",
        action="store_true",
        help="Generate submission.csv based on trained model",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args    = _parse_args()
    project_root = Path(__file__).parent
    raw_dir      = (project_root / args.data_dir).resolve()

    run_pipeline(
        raw_dir=raw_dir,
        validate_only=args.validate_only,
        train=args.train,
        predict=args.predict,
    )
