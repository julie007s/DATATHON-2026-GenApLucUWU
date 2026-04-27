import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.ensemble import (
    DEFAULT_RESIDUAL_WEIGHTS,
    blend_residual_predictions,
    forecast_arima_baseline,
    load_hybrid_metadata,
    load_model,
    log_progress,
    log_stage,
)
from src.feature_contract import get_model_feature_columns, get_recursive_base_columns
from src.logger import logger


def _load_saved_feature_list(model_dir: Path) -> list[str] | None:
    metadata_path = model_dir / "model_features.json"
    if not metadata_path.exists():
        return None
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        features = payload.get("features", [])
        return features if isinstance(features, list) else None
    except Exception:
        return None


def _prepare_recursive_frame(features_df: pd.DataFrame, sample_df: pd.DataFrame, feature_cols: list[str]) -> tuple[pd.DataFrame, pd.Timestamp, list[str]]:
    train_max = features_df["Date"].max()
    all_dates = pd.DataFrame({
        "Date": pd.concat([features_df["Date"], sample_df["Date"]]).drop_duplicates().sort_values()
    })

    base_cols = get_recursive_base_columns(features_df)
    all_df = all_dates.merge(features_df, on="Date", how="left")
    all_df = all_df.sort_values("Date").reset_index(drop=True)
    all_df.set_index("Date", inplace=True)

    exog_bases = [c for c in base_cols if c not in ["Revenue", "COGS", "cogs_to_revenue_ratio"]]
    if exog_bases:
        all_df[exog_bases] = all_df[exog_bases].ffill()

    if "day_of_week" in all_df.columns:
        all_df["day_of_week"] = all_df.index.dayofweek
    if "month" in all_df.columns:
        all_df["month"] = all_df.index.month
    if "year" in all_df.columns:
        all_df["year"] = all_df.index.year
    if "day_of_year" in all_df.columns:
        all_df["day_of_year"] = all_df.index.dayofyear
    if "week_of_year" in all_df.columns:
        all_df["week_of_year"] = all_df.index.isocalendar().week.astype(int)

    month = all_df.index.month
    quarter = all_df.index.quarter
    deterministic_updates = {
        "is_q2_peak": np.isin(month, [4, 5, 6]).astype(int),
        "is_pre_peak_ramp": np.isin(month, [2, 3]).astype(int),
        "is_post_peak_decay": np.isin(month, [7, 8, 9]).astype(int),
        "is_august_cost_risk": (month == 8).astype(int),
        "is_late_summer_cost_risk": np.isin(month, [7, 8, 9]).astype(int),
        "is_year_end_pressure": np.isin(month, [11, 12]).astype(int),
        "is_december_pressure": (month == 12).astype(int),
        "is_q4": (quarter == 4).astype(int),
        "month_in_quarter": ((month - 1) % 3) + 1,
    }
    margin_risk_score = {1: 0.2, 2: 0.1, 3: 0.2, 4: 0.3, 5: 0.1, 6: 0.3, 7: 0.8, 8: 1.0, 9: 0.8, 10: 0.4, 11: 0.7, 12: 1.0}
    pre_pandemic_revenue_share = {1: 0.0504, 2: 0.0602, 3: 0.0927, 4: 0.1256, 5: 0.1328, 6: 0.1264, 7: 0.0924, 8: 0.0887, 9: 0.0700, 10: 0.0644, 11: 0.0488, 12: 0.0478}
    deterministic_updates["margin_risk_month_score"] = pd.Index(month).map(margin_risk_score).astype(float).to_numpy()
    deterministic_updates["pre_pandemic_month_revenue_share"] = pd.Index(month).map(pre_pandemic_revenue_share).astype(float).to_numpy()
    months_since_recovery = (all_df.index.year - 2022) * 12 + month
    deterministic_updates["recovery_trend_index"] = np.clip(months_since_recovery, 0, None).astype(int)
    deterministic_updates["is_recovery_regime"] = (all_df.index.year >= 2022).astype(int)
    deterministic_updates["recovery_x_q2_peak"] = deterministic_updates["is_recovery_regime"] * deterministic_updates["is_q2_peak"]
    deterministic_updates["recovery_x_year_end_pressure"] = deterministic_updates["is_recovery_regime"] * deterministic_updates["is_year_end_pressure"]
    deterministic_updates["recovery_x_august_cost_risk"] = deterministic_updates["is_recovery_regime"] * deterministic_updates["is_august_cost_risk"]
    for col, values in deterministic_updates.items():
        if col in all_df.columns:
            all_df[col] = values
    if "days_until_holiday" in all_df.columns:
        holidays_fixed = ["01-01", "04-30", "05-01", "09-02", "12-25"]

        def _get_countdown(dt):
            curr_year = dt.year
            potential = [pd.to_datetime(f"{y}-{h}") for y in [curr_year, curr_year + 1] for h in holidays_fixed]
            future = [h for h in potential if h >= dt]
            return (min(future) - dt).days if future else 365

        all_df["days_until_holiday"] = all_df.index.to_series().apply(_get_countdown)

    if "market_era" in all_df.columns:
        all_df["market_era"] = np.select(
            [all_df.index < pd.Timestamp("2020-02-01"), all_df.index <= pd.Timestamp("2021-09-30")],
            [0.0, 1.0],
            default=2.0,
        )

    if "covid_intensity" in all_df.columns:
        def _calc_covid_intensity(dt):
            if dt < pd.Timestamp("2020-02-01"):
                return 0.0
            if dt < pd.Timestamp("2021-05-01"):
                total_days = (pd.Timestamp("2021-05-01") - pd.Timestamp("2020-02-01")).days
                days = (dt - pd.Timestamp("2020-02-01")).days
                return 0.7 * (days / total_days)
            if dt <= pd.Timestamp("2021-09-30"):
                return 1.0
            days_passed = (dt - pd.Timestamp("2021-09-30")).days
            lambda_ = np.log(1 / 0.1) / ((pd.Timestamp("2023-01-01") - pd.Timestamp("2021-09-30")).days)
            return float(np.exp(-lambda_ * days_passed))

        all_df["covid_intensity"] = all_df.index.to_series().apply(_calc_covid_intensity)

    source_vars = [
        c for c in all_df.columns
        if any(f"{c}_{sfx}" in feature_cols for sfx in ["lag7", "lag30", "lag365", "roll7", "roll30"])
    ]
    return all_df, train_max, source_vars


def _run_recursive_residual_model(
    model,
    all_df: pd.DataFrame,
    feature_cols: list[str],
    feedback_col: str,
    train_max: pd.Timestamp,
    source_vars: list[str],
    learner_name: str,
    verbose: bool,
) -> tuple[pd.Series, np.ndarray]:
    work_df = all_df.copy()
    test_dates_only = [d for d in work_df.index if d > train_max]
    total_steps = len(test_dates_only)
    residual_preds = []

    if verbose:
        log_stage(f"Recursive residual inference started for {learner_name} -> {feedback_col}")

    for step_idx, t_date in enumerate(test_dates_only, start=1):
        for var in source_vars:
            t_minus_7 = t_date - pd.Timedelta(days=7)
            t_minus_30 = t_date - pd.Timedelta(days=30)
            t_minus_365 = t_date - pd.Timedelta(days=365)

            if f"{var}_lag7" in feature_cols:
                work_df.loc[t_date, f"{var}_lag7"] = work_df.loc[t_minus_7, var] if t_minus_7 in work_df.index else 0
            if f"{var}_lag30" in feature_cols:
                work_df.loc[t_date, f"{var}_lag30"] = work_df.loc[t_minus_30, var] if t_minus_30 in work_df.index else 0
            if f"{var}_lag365" in feature_cols:
                work_df.loc[t_date, f"{var}_lag365"] = work_df.loc[t_minus_365, var] if t_minus_365 in work_df.index else 0

            if f"{var}_roll7" in feature_cols:
                p7 = [t_date - pd.Timedelta(days=i) for i in range(1, 8)]
                valid_p7 = [d for d in p7 if d in work_df.index]
                work_df.loc[t_date, f"{var}_roll7"] = work_df.loc[valid_p7, var].mean() if valid_p7 else 0

            if f"{var}_roll30" in feature_cols:
                p30 = [t_date - pd.Timedelta(days=i) for i in range(1, 31)]
                valid_p30 = [d for d in p30 if d in work_df.index]
                work_df.loc[t_date, f"{var}_roll30"] = work_df.loc[valid_p30, var].mean() if valid_p30 else 0

        X_t = work_df.loc[[t_date], feature_cols].fillna(0)
        residual_pred = float(model.predict(X_t)[0])
        residual_preds.append(residual_pred)

        # Temporary feedback uses residual correction only. Final target feedback is overwritten
        # after residual blending by caller when both learners have produced corrections.
        work_df.loc[t_date, feedback_col] = work_df.loc[t_date, feedback_col] if pd.notna(work_df.loc[t_date, feedback_col]) else 0

        if verbose and (step_idx == 1 or step_idx == total_steps or step_idx % 50 == 0):
            log_progress(
                f"{learner_name} {feedback_col} residual",
                step_idx,
                total_steps,
                extra=str(t_date.date()),
            )

    return work_df[feedback_col], np.asarray(residual_preds, dtype=float)


def _predict_target_hybrid(
    target_name: str,
    model_dir: Path,
    recursive_df: pd.DataFrame,
    feature_cols: list[str],
    train_max: pd.Timestamp,
    source_vars: list[str],
    future_dates: list[pd.Timestamp],
    residual_weights: dict[str, float],
    verbose: bool,
) -> dict[str, np.ndarray]:
    target_key = target_name.lower()
    arima_model = load_model(model_dir / f"arima_{target_key}_baseline.joblib")
    xgb_model = load_model(model_dir / f"xgboost_{target_key}_residual.joblib")
    enet_model = load_model(model_dir / f"elasticnet_{target_key}_residual.joblib")

    if arima_model is None or xgb_model is None or enet_model is None:
        raise FileNotFoundError(f"Missing hybrid residual artifacts for {target_name} in {model_dir}")

    future_count = len(future_dates)
    if verbose:
        log_stage(f"ARIMA baseline forecasting started for {target_name} ({future_count} steps)")
    baseline = forecast_arima_baseline(arima_model, future_count)

    _, xgb_residual = _run_recursive_residual_model(
        xgb_model,
        recursive_df,
        feature_cols,
        target_name,
        train_max,
        source_vars,
        "XGBoost",
        verbose,
    )
    _, enet_residual = _run_recursive_residual_model(
        enet_model,
        recursive_df,
        feature_cols,
        target_name,
        train_max,
        source_vars,
        "ElasticNet",
        verbose,
    )

    if verbose:
        log_stage(f"Blending residual corrections for {target_name}")
    residual_blend = blend_residual_predictions(
        {"xgboost": xgb_residual, "elasticnet": enet_residual},
        residual_weights,
    )
    final = baseline + residual_blend
    final = np.maximum(final, 0)

    return {
        "final": final,
        "baseline": baseline,
        "xgb_residual": xgb_residual,
        "enet_residual": enet_residual,
        "residual_blend": residual_blend,
    }


def generate_submission(
    model_path: Path,
    feature_table_path: Path,
    sample_submission_path: Path,
    output_dir: Path,
    cogs_model_path: Path = None,
    verbose: bool = True,
):
    if verbose:
        logger.info("  Generating Predictions (ARIMA-first Residual Hybrid)...")
        log_stage("Loading hybrid residual models and metadata")

    model_dir = model_path.parent

    if not feature_table_path.exists():
        raise FileNotFoundError(f"Feature table not found at {feature_table_path}")
    features_df = pd.read_parquet(feature_table_path, engine="pyarrow")
    features_df["Date"] = pd.to_datetime(features_df["Date"])

    if not sample_submission_path.exists():
        raise FileNotFoundError(f"Sample submission not found at {sample_submission_path}")
    sample_df = pd.read_csv(sample_submission_path)
    sample_df["Date"] = pd.to_datetime(sample_df["Date"])

    metadata = load_hybrid_metadata(model_dir)
    feature_cols = metadata.get("features") or _load_saved_feature_list(model_dir) or get_model_feature_columns(features_df)
    target_configs = metadata.get("target_configs", {})
    default_residual_weights = metadata.get("default_residual_weights", DEFAULT_RESIDUAL_WEIGHTS)
    revenue_weights = target_configs.get("Revenue", {}).get("residual_weights", default_residual_weights)
    cogs_weights = target_configs.get("COGS", {}).get("residual_weights", default_residual_weights)
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
        logger.info(f"  Revenue residual weights: {revenue_weights}")
        logger.info(f"  COGS residual weights   : {cogs_weights}")

    revenue = _predict_target_hybrid(
        "Revenue",
        model_dir,
        recursive_df,
        feature_cols,
        train_max,
        source_vars,
        future_dates,
        revenue_weights,
        verbose,
    )
    cogs = _predict_target_hybrid(
        "COGS",
        model_dir,
        recursive_df,
        feature_cols,
        train_max,
        source_vars,
        future_dates,
        cogs_weights,
        verbose,
    )

    full_output = sample_df[["Date"]].copy()
    full_output["Revenue"] = revenue["final"]
    full_output["COGS"] = cogs["final"]
    full_output["Profit"] = full_output["Revenue"] - full_output["COGS"]

    full_output["Revenue_ARIMA_Baseline"] = revenue["baseline"]
    full_output["Revenue_XGB_Residual"] = revenue["xgb_residual"]
    full_output["Revenue_ElasticNet_Residual"] = revenue["enet_residual"]
    full_output["Revenue_Residual_Blend"] = revenue["residual_blend"]
    full_output["COGS_ARIMA_Baseline"] = cogs["baseline"]
    full_output["COGS_XGB_Residual"] = cogs["xgb_residual"]
    full_output["COGS_ElasticNet_Residual"] = cogs["enet_residual"]
    full_output["COGS_Residual_Blend"] = cogs["residual_blend"]

    output_dir.mkdir(parents=True, exist_ok=True)
    submission_path = output_dir / "submission.csv"
    full_output[["Date", "Revenue", "COGS"]].to_csv(submission_path, index=False)

    analysis_path = output_dir / "analysis_report.csv"
    full_output.to_csv(analysis_path, index=False)

    if verbose:
        log_stage("Hybrid residual outputs written to disk")
        logger.info("  Prediction complete!")
        logger.info(f"  Predicted {len(full_output)} rows with ARIMA-first residual hybrid.")
        logger.info(f"  Revenue range: {full_output['Revenue'].min():,.2f} — {full_output['Revenue'].max():,.2f}")
        logger.info(f"  COGS range   : {full_output['COGS'].min():,.2f} — {full_output['COGS'].max():,.2f}")
        logger.info(f"  Profit range : {full_output['Profit'].min():,.2f} — {full_output['Profit'].max():,.2f}")
        logger.info(f"  ✅ Submission saved (3 cols)  : {submission_path}")
        logger.info(f"  📊 Analysis saved (with hybrid debug cols): {analysis_path}")

    return full_output


if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    generate_submission(
        model_path=project_root / "models/xgboost_revenue_residual.joblib",
        feature_table_path=project_root / "data/output/featured_table.parquet",
        sample_submission_path=project_root / "data/raw/sample_submission.csv",
        output_dir=project_root / "data/output",
        cogs_model_path=project_root / "models/xgboost_cogs_residual.joblib",
    )
