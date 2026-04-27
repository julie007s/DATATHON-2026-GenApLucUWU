from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from src.ensemble import log_stage
from src.feature_contract import get_active_feature_profile, get_model_feature_columns, persist_active_feature_profile
from src.logger import logger
from src.seasonal_baseline import DEFAULT_SEASONAL_WEIGHTS, build_in_sample_seasonal_baseline, forecast_seasonal_baseline


def _evaluate_predictions(y_true: pd.Series, preds: np.ndarray) -> tuple[float, float, float]:
    mae = mean_absolute_error(y_true, preds)
    rmse = np.sqrt(mean_squared_error(y_true, preds))
    r2 = r2_score(y_true, preds)
    return float(mae), float(rmse), float(r2)


def _load_locked_xgb_config(report_output_dir: Path, model_arch: str) -> dict:
    config_path = report_output_dir / "best_xgb_config.json"
    if not config_path.exists():
        return {}
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning(f"  Could not parse {config_path}: {exc}")
        return {}
    if config.get("model_arch") != model_arch:
        logger.info(
            f"  Ignoring {config_path.name}: config model_arch={config.get('model_arch')} "
            f"does not match active architecture={model_arch}"
        )
        return {}
    return config


def _get_locked_xgb_target_config(locked_config: dict, target_key: str) -> dict:
    return locked_config.get("targets", {}).get(target_key, {})


def _make_xgb_model(objective: str = "reg:squarederror", locked_xgb_config: dict | None = None) -> xgb.XGBRegressor:
    locked_xgb_config = locked_xgb_config or {}
    params = locked_xgb_config.get("params", {})
    n_estimators = int(locked_xgb_config.get("locked_n_estimators", 700))
    if locked_xgb_config:
        logger.info(f"  Using locked XGB config: n_estimators={n_estimators}, params={params}")
    return xgb.XGBRegressor(
        objective=objective,
        n_estimators=n_estimators,
        learning_rate=params.get("learning_rate", 0.04),
        max_depth=params.get("max_depth", 5),
        subsample=params.get("subsample", 0.85),
        colsample_bytree=params.get("colsample_bytree", 0.85),
        min_child_weight=params.get("min_child_weight", 3),
        reg_alpha=params.get("reg_alpha", 0.1),
        reg_lambda=params.get("reg_lambda", 3.0),
        n_jobs=-1,
        random_state=42,
    )


def _save_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def train_seasonal_xgb_model(
    feature_table_path: Path,
    model_output_dir: Path,
    report_output_dir: Path,
    train_until: str = None,
    verbose: bool = True,
):
    if verbose:
        logger.info("  Starting Seasonal Baseline + XGBoost Residual + COGS Ratio Training...")
        log_stage("Loading feature table for seasonal_xgb_ratio training")

    if not feature_table_path.exists():
        raise FileNotFoundError(f"Feature table not found at {feature_table_path}")

    df = pd.read_parquet(feature_table_path, engine="pyarrow")
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)

    active_feature_profile = get_active_feature_profile()
    features = get_model_feature_columns(df, active_feature_profile)
    if not features:
        raise ValueError("No leakage-safe model features were found in featured_table.parquet")
    if "Revenue" not in df.columns or df["Revenue"].isna().all():
        raise ValueError("Revenue column missing or all-null in feature table.")
    if "COGS" not in df.columns or df["COGS"].isna().all():
        raise ValueError("COGS column missing or all-null in feature table.")

    if train_until:
        if verbose:
            logger.info(f"  Isolating data: Training strictly before {train_until}")
        train_df = df[df["Date"] < train_until].copy()
        test_df = df[df["Date"] >= train_until].copy()
    else:
        train_df = df.copy()
        test_df = pd.DataFrame()

    X = train_df[features].fillna(0)
    sample_weight = train_df["sample_weight"] if "sample_weight" in train_df.columns else None
    locked_xgb_config = _load_locked_xgb_config(report_output_dir, "seasonal_xgb_ratio")
    if verbose and locked_xgb_config.get("targets"):
        log_stage(f"Loaded locked XGBoost estimator config from {report_output_dir / 'best_xgb_config.json'}")

    if verbose:
        logger.info(f"     Training days : {len(train_df)}")
        logger.info(f"     Feature profile: {active_feature_profile}")
        logger.info(f"     Feature count : {len(features)}")
        log_stage("Building seasonal revenue baseline")

    revenue_baseline = build_in_sample_seasonal_baseline(train_df, "Revenue")
    revenue_residual = train_df["Revenue"].astype(float) - revenue_baseline.astype(float)

    safe_revenue = train_df["Revenue"].replace(0, np.nan).astype(float)
    cogs_ratio = (train_df["COGS"].astype(float) / safe_revenue).replace([np.inf, -np.inf], np.nan)
    cogs_ratio = cogs_ratio.fillna(cogs_ratio.median()).clip(lower=0.0, upper=2.0)
    ratio_q01 = float(cogs_ratio.quantile(0.01))
    ratio_q99 = float(cogs_ratio.quantile(0.99))

    if verbose:
        logger.info(
            f"  Revenue residual diagnostics | mean={revenue_residual.mean():,.2f} | "
            f"std={revenue_residual.std():,.2f} | min={revenue_residual.min():,.2f} | max={revenue_residual.max():,.2f}"
        )
        logger.info(f"  COGS ratio clip range: {ratio_q01:.4f} — {ratio_q99:.4f}")
        log_stage("Fitting XGBoost revenue residual model")

    revenue_model = _make_xgb_model(locked_xgb_config=_get_locked_xgb_target_config(locked_xgb_config, "Revenue_Residual"))
    revenue_model.fit(X, revenue_residual, sample_weight=sample_weight)

    if verbose:
        log_stage("Fitting XGBoost COGS ratio model")
    cogs_ratio_model = _make_xgb_model(locked_xgb_config=_get_locked_xgb_target_config(locked_xgb_config, "COGS_Ratio"))
    cogs_ratio_model.fit(X, cogs_ratio, sample_weight=sample_weight)

    if not test_df.empty:
        if verbose:
            log_stage("Running holdout diagnostics for seasonal_xgb_ratio")
        X_test = test_df[features].fillna(0)
        test_baseline = forecast_seasonal_baseline(train_df, test_df["Date"], "Revenue")
        revenue_pred = np.maximum(test_baseline + revenue_model.predict(X_test), 0)
        ratio_pred_raw = cogs_ratio_model.predict(X_test)
        ratio_pred = np.clip(ratio_pred_raw, ratio_q01, ratio_q99)
        cogs_pred = np.maximum(revenue_pred * ratio_pred, 0)

        rev_mae, rev_rmse, rev_r2 = _evaluate_predictions(test_df["Revenue"], revenue_pred)
        cogs_mae, cogs_rmse, cogs_r2 = _evaluate_predictions(test_df["COGS"], cogs_pred)
        logger.info(f"  HOLDOUT [Revenue seasonal_xgb] | MAE: {rev_mae:,.2f} | RMSE: {rev_rmse:,.2f} | R2: {rev_r2:.4f}")
        logger.info(f"  HOLDOUT [COGS ratio]          | MAE: {cogs_mae:,.2f} | RMSE: {cogs_rmse:,.2f} | R2: {cogs_r2:.4f}")

    model_output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(revenue_model, model_output_dir / "seasonal_xgb_revenue_residual.joblib")
    joblib.dump(cogs_ratio_model, model_output_dir / "seasonal_xgb_cogs_ratio.joblib")

    metadata = {
        "architecture": "seasonal_xgb_ratio",
        "feature_profile": active_feature_profile,
        "features": features,
        "targets": ["Revenue", "COGS"],
        "seasonal_weights": DEFAULT_SEASONAL_WEIGHTS,
        "cogs_ratio_clip": {"q01": ratio_q01, "q99": ratio_q99},
        "train_start": str(train_df["Date"].min().date()),
        "train_end": str(train_df["Date"].max().date()),
        "locked_xgb_config_used": bool(locked_xgb_config),
    }
    persist_active_feature_profile(active_feature_profile)
    if locked_xgb_config:
        locked_metadata_path = model_output_dir / "seasonal_xgb_locked_xgb_config.json"
        locked_metadata_path.write_text(json.dumps(locked_xgb_config, indent=2), encoding="utf-8")
    metadata_path = _save_json(model_output_dir / "seasonal_xgb_metadata.json", metadata)
    _save_json(model_output_dir / "seasonal_xgb_features.json", {"features": features})

    if verbose:
        logger.info(f"  Seasonal XGB metadata saved to: {metadata_path}")
        log_stage("seasonal_xgb_ratio training finished")

    return {"revenue_model": revenue_model, "cogs_ratio_model": cogs_ratio_model, "metadata": metadata}
