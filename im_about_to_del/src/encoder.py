import pandas as pd
import numpy as np
import yaml
import joblib
from pathlib import Path
from src.logger import logger

def _load_encoding_config(config_path: Path) -> dict:
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found at {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f).get("target_encoding", {})

def run_encoding(
    master_table_path: Path,
    output_dir: Path,
    model_output_dir: Path,
    config_path: Path = None,
    verbose: bool = True
) -> pd.DataFrame:
    """
    Advanced Time-Series Target Encoder (Temporal Leakage-Free).

    Uses an EXPANDING WINDOW with a DATE-LEVEL cumulative prior so that
    each observation is encoded using only data from strictly earlier dates.

    Fix applied (Audit Issue #2 — Data Leakage):
    - global_mean is NO LONGER a single scalar computed from all rows.
    - Instead, each date gets its own expanding_global_mean = cumulative mean
      of all PREVIOUS dates' average target values (shift-1 on the daily level).
    - This eliminates look-ahead bias in the smoothing prior.

    Reads  : master_table.csv
    Saves  : advanced_encoders.joblib, encoded_master.parquet
    """
    if verbose:
        logger.info(f"\n{'=' * 60}")
        logger.info("  Starting Advanced Time-Series Target Encoding...")
        logger.info(f"{'=' * 60}")

    if config_path is None:
        config_path = Path(__file__).parent.parent / "configs" / "encoding.yaml"

    config = _load_encoding_config(config_path)
    columns_to_encode = config.get("columns", [])
    target_col = config.get("target_col", "line_revenue")
    weight = config.get("smoothing_weight", 10)

    if not columns_to_encode:
        logger.warning("  WARNING: No columns to encode found in config.")
        return pd.read_csv(master_table_path, low_memory=False)

    df = pd.read_csv(master_table_path, low_memory=False)

    if verbose:
        logger.info(f"  Loaded master table: {df.shape[0]:,} rows x {df.shape[1]} columns")

    # Ensure datetime and chronological sort
    date_col = "order_date"
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.sort_values(date_col).reset_index(drop=True)

    if target_col not in df.columns:
        raise ValueError(
            f"Target column '{target_col}' not found in master_table. "
            f"Available columns: {list(df.columns)}"
        )

    # ── FIX: Compute LEAK-FREE expanding global mean (daily, shift-1) ─────
    # Step 1: Daily average target value per date
    daily_global = (
        df.groupby(date_col)[target_col]
        .mean()
        .reset_index()
        .rename(columns={target_col: "daily_avg"})
        .sort_values(date_col)
        .reset_index(drop=True)
    )

    # Step 2: Expanding cumulative mean of daily averages, shifted by 1 day.
    #   On date D: expanding_global_mean = mean of daily_avg for ALL days BEFORE D.
    #   This means the first date gets no prior from past dates → fallback to its own avg.
    daily_global["cum_sum"]   = daily_global["daily_avg"].cumsum().shift(1).fillna(0.0)
    daily_global["cum_count"] = pd.Series(np.arange(len(daily_global), dtype=float))
    # cum_count = 0 for the first row → avoid division by zero
    with np.errstate(divide="ignore", invalid="ignore"):
        daily_global["expanding_global_mean"] = np.where(
            daily_global["cum_count"] == 0,
            daily_global["daily_avg"],          # first date: fallback to its own mean
            daily_global["cum_sum"] / daily_global["cum_count"]
        )

    # Merge expanding_global_mean back to row-level df
    df = df.merge(daily_global[[date_col, "expanding_global_mean"]], on=date_col, how="left")
    # ──────────────────────────────────────────────────────────────────────

    # Inference-time global mean = mean over ALL training data (correct: test set is future)
    inference_global_mean = float(df[target_col].mean())

    saved_encoders = {}

    for col in columns_to_encode:
        if col not in df.columns:
            logger.warning(f"  WARNING: Column '{col}' not found in master_table, skipping.")
            continue

        if verbose:
            logger.info(f"     Encoding '{col}' using Expanding Window & Leak-Free Prior...")

        encoded_col_name = f"{col}_encoded"

        # Drop previous encoded column if it exists (re-run safety)
        if encoded_col_name in df.columns:
            df = df.drop(columns=[encoded_col_name])

        # Cumulative sum/count per (date, category) — EXCLUDING current date
        daily_stats = (
            df.groupby([date_col, col])[target_col]
            .agg(["sum", "count"])
            .reset_index()
            .sort_values(date_col)
        )
        daily_stats["cum_sum"]   = (
            daily_stats.groupby(col)["sum"].cumsum()   - daily_stats["sum"]
        )
        daily_stats["cum_count"] = (
            daily_stats.groupby(col)["count"].cumsum() - daily_stats["count"]
        )

        # Attach per-date leak-free global prior
        daily_stats = daily_stats.merge(
            daily_global[[date_col, "expanding_global_mean"]],
            on=date_col,
            how="left"
        )

        # Smoothed expanding mean: (historical_sum + weight * prior) / (historical_count + weight)
        daily_stats[encoded_col_name] = (
            (daily_stats["cum_sum"] + weight * daily_stats["expanding_global_mean"])
            / (daily_stats["cum_count"] + weight)
        )

        # Merge encoded values back to row-level df
        df = df.merge(
            daily_stats[[date_col, col, encoded_col_name]],
            on=[date_col, col],
            how="left"
        )

        # Fallback for first occurrence of any category: use that date's expanding global mean
        df[encoded_col_name] = df[encoded_col_name].fillna(df["expanding_global_mean"])

        # Save inference mapping (uses ALL training data — no leakage at inference time)
        final_stats = df.groupby(col)[target_col].agg(["sum", "count"])
        saved_encoders[col] = (
            (final_stats["sum"] + weight * inference_global_mean)
            / (final_stats["count"] + weight)
        ).to_dict()
        saved_encoders[f"{col}_global_mean"] = inference_global_mean

    # Drop helper column before saving
    df = df.drop(columns=["expanding_global_mean"], errors="ignore")

    # Save inference encoder mapping
    model_output_dir.mkdir(parents=True, exist_ok=True)
    joblib_path = model_output_dir / "advanced_encoders.joblib"
    joblib.dump(saved_encoders, joblib_path)
    if verbose:
        logger.info(f"  Encoders saved to: {joblib_path}")

    # Save encoded master table
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "encoded_master.parquet"
    df.to_parquet(output_path, index=False, engine="pyarrow")

    if verbose:
        logger.info(f"  Encoding complete! Output shape: {df.shape[0]:,} rows x {df.shape[1]} columns")

    return df


if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    run_encoding(
        project_root / "data/output/master_table.csv",
        project_root / "data/output",
        project_root / "models"
    )
