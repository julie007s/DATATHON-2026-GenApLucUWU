from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.ensemble import log_stage
from src.feature_contract import get_model_feature_columns
from src.logger import logger
from src.predictor import _load_saved_feature_list, _prepare_recursive_frame, _run_recursive_residual_model
from src.seasonal_baseline import DEFAULT_SEASONAL_WEIGHTS, forecast_seasonal_baseline


def _load_metadata(model_dir: Path) -> dict:
    metadata_path = model_dir / "seasonal_xgb_metadata.json"
    if not metadata_path.exists():
        return {
            "architecture": "seasonal_xgb_ratio",
            "features": [],
            "seasonal_weights": DEFAULT_SEASONAL_WEIGHTS,
            "cogs_ratio_clip": {"q01": 0.0, "q99": 1.5},
        }
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def generate_seasonal_xgb_submission(
    model_dir: Path,
    feature_table_path: Path,
    sample_submission_path: Path,
    output_dir: Path,
    verbose: bool = True,
):
    if verbose:
        logger.info("  Generating Predictions (Seasonal Baseline + XGB Residual + COGS Ratio)...")
        log_stage("Loading seasonal_xgb_ratio models and metadata")

    revenue_model_path = model_dir / "seasonal_xgb_revenue_residual.joblib"
    cogs_ratio_model_path = model_dir / "seasonal_xgb_cogs_ratio.joblib"
    if not revenue_model_path.exists() or not cogs_ratio_model_path.exists():
        raise FileNotFoundError(
            "Missing seasonal_xgb_ratio artifacts. Run: "
            "python pipeline.py --train --model_arch seasonal_xgb_ratio"
        )

    revenue_model = joblib.load(revenue_model_path)
    cogs_ratio_model = joblib.load(cogs_ratio_model_path)
    metadata = _load_metadata(model_dir)

    if not feature_table_path.exists():
        raise FileNotFoundError(f"Feature table not found at {feature_table_path}")
    features_df = pd.read_parquet(feature_table_path, engine="pyarrow")
    features_df["Date"] = pd.to_datetime(features_df["Date"])

    if not sample_submission_path.exists():
        raise FileNotFoundError(f"Sample submission not found at {sample_submission_path}")
    sample_df = pd.read_csv(sample_submission_path)
    sample_df["Date"] = pd.to_datetime(sample_df["Date"])

    feature_cols = metadata.get("features") or _load_saved_feature_list(model_dir) or get_model_feature_columns(features_df)
    missing_features = [c for c in feature_cols if c not in features_df.columns]
    if missing_features:
        raise ValueError(f"Feature table is missing model features required for inference: {missing_features[:10]}")

    if verbose:
        log_stage("Preparing recursive feature frame")
    recursive_df, train_max, source_vars = _prepare_recursive_frame(features_df, sample_df, feature_cols)
    future_dates = [d for d in recursive_df.index if d > train_max]

    if verbose:
        logger.info(f"  Training data ends : {train_max.date()}")
        logger.info(f"  Test dates start   : {sample_df['Date'].min().date()}")
        logger.info(f"  Using {len(feature_cols)} model features for inference.")
        logger.info(f"  {len(future_dates)} test dates will be predicted recursively.")

    history_df = features_df[features_df["Date"] <= train_max].copy()
    seasonal_weights = metadata.get("seasonal_weights", DEFAULT_SEASONAL_WEIGHTS)
    revenue_baseline = forecast_seasonal_baseline(
        history_df,
        future_dates,
        "Revenue",
        weights=seasonal_weights,
    )

    _, revenue_residual = _run_recursive_residual_model(
        revenue_model,
        recursive_df,
        feature_cols,
        "Revenue",
        train_max,
        source_vars,
        "Seasonal-XGB Revenue",
        verbose,
    )
    revenue = np.maximum(revenue_baseline + revenue_residual, 0)

    _, cogs_ratio_raw = _run_recursive_residual_model(
        cogs_ratio_model,
        recursive_df,
        feature_cols,
        "COGS",
        train_max,
        source_vars,
        "XGB COGS Ratio",
        verbose,
    )
    ratio_clip = metadata.get("cogs_ratio_clip", {"q01": 0.0, "q99": 1.5})
    ratio_low = float(ratio_clip.get("q01", 0.0))
    ratio_high = float(ratio_clip.get("q99", 1.5))
    cogs_ratio = np.clip(cogs_ratio_raw, ratio_low, ratio_high)
    cogs = np.maximum(revenue * cogs_ratio, 0)

    full_output = sample_df[["Date"]].copy()
    full_output["Revenue"] = revenue
    full_output["COGS"] = cogs
    full_output["Profit"] = full_output["Revenue"] - full_output["COGS"]
    full_output["Revenue_Seasonal_Baseline"] = revenue_baseline
    full_output["Revenue_XGB_Residual"] = revenue_residual
    full_output["COGS_Ratio_Raw"] = cogs_ratio_raw
    full_output["COGS_Ratio_Clipped"] = cogs_ratio

    output_dir.mkdir(parents=True, exist_ok=True)
    submission_path = output_dir / "submission.csv"
    full_output[["Date", "Revenue", "COGS"]].to_csv(submission_path, index=False)

    analysis_path = output_dir / "analysis_report.csv"
    full_output.to_csv(analysis_path, index=False)

    if verbose:
        log_stage("seasonal_xgb_ratio outputs written to disk")
        logger.info("  Prediction complete!")
        logger.info(f"  Predicted {len(full_output)} rows with seasonal_xgb_ratio.")
        logger.info(f"  Revenue range: {full_output['Revenue'].min():,.2f} — {full_output['Revenue'].max():,.2f}")
        logger.info(f"  COGS range   : {full_output['COGS'].min():,.2f} — {full_output['COGS'].max():,.2f}")
        logger.info(f"  Profit range : {full_output['Profit'].min():,.2f} — {full_output['Profit'].max():,.2f}")
        logger.info(f"  ✅ Submission saved (3 cols): {submission_path}")
        logger.info(f"  📊 Analysis saved           : {analysis_path}")

    return full_output
