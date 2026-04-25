import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.feature_contract import get_model_feature_columns, get_recursive_base_columns
from src.logger import logger


def _load_saved_feature_list(model_path: Path) -> list[str] | None:
    metadata_path = model_path.parent / "model_features.json"
    if not metadata_path.exists():
        return None
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        features = payload.get("features", [])
        return features if isinstance(features, list) else None
    except Exception:
        return None


def generate_submission(
    model_path: Path,
    feature_table_path: Path,
    sample_submission_path: Path,
    output_dir: Path,
    cogs_model_path: Path = None,
    verbose: bool = True,
):
    """
    Generate submission.csv using recursive forecasting on leakage-safe features.
    """
    if verbose:
        logger.info("  Generating Predictions (Revenue + COGS) using Recursive Loop...")

    if cogs_model_path is None:
        cogs_model_path = model_path.parent / "xgboost_cogs_model.joblib"

    if not model_path.exists():
        raise FileNotFoundError(f"Revenue model not found at {model_path}")
    revenue_model = joblib.load(model_path)

    cogs_model = None
    if cogs_model_path.exists():
        cogs_model = joblib.load(cogs_model_path)
        if verbose:
            logger.info(f"  COGS model loaded from: {cogs_model_path}")
    else:
        logger.warning(
            f"  COGS model not found at {cogs_model_path}. "
            "COGS will fall back to 0 for profit calculation."
        )

    if not feature_table_path.exists():
        raise FileNotFoundError(f"Feature table not found at {feature_table_path}")
    features_df = pd.read_parquet(feature_table_path, engine="pyarrow")
    features_df["Date"] = pd.to_datetime(features_df["Date"])

    if not sample_submission_path.exists():
        raise FileNotFoundError(f"Sample submission not found at {sample_submission_path}")
    sample_df = pd.read_csv(sample_submission_path)
    sample_df["Date"] = pd.to_datetime(sample_df["Date"])

    feature_cols = _load_saved_feature_list(model_path) or get_model_feature_columns(features_df)
    missing_features = [c for c in feature_cols if c not in features_df.columns]
    if missing_features:
        raise ValueError(f"Feature table is missing model features required for inference: {missing_features[:10]}")

    if verbose:
        train_max = features_df["Date"].max()
        test_min = sample_df["Date"].min()
        logger.info(f"  Training data ends : {train_max.date()}")
        logger.info(f"  Test dates start   : {test_min.date()}")
        logger.info(f"  Using {len(feature_cols)} model features for inference.")
        future_count = (sample_df["Date"] > train_max).sum()
        if future_count > 0:
            logger.info(f"  {future_count} test dates will be predicted recursively.")

    all_dates = pd.DataFrame({
        "Date": pd.concat([features_df["Date"], sample_df["Date"]]).drop_duplicates().sort_values()
    })

    base_cols = get_recursive_base_columns(features_df)
    all_df = all_dates.merge(features_df, on="Date", how="left")
    all_df = all_df.sort_values("Date").reset_index(drop=True)
    all_df.set_index("Date", inplace=True)

    exog_bases = [c for c in base_cols if c not in ["Revenue", "COGS"]]
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

    test_dates_only = [d for d in all_df.index if d > train_max]
    source_vars = [
        c for c in all_df.columns
        if any(f"{c}_{sfx}" in feature_cols for sfx in ["lag7", "lag30", "lag365", "roll7", "roll30"])
    ]

    for t_date in test_dates_only:
        for var in source_vars:
            t_minus_7 = t_date - pd.Timedelta(days=7)
            t_minus_30 = t_date - pd.Timedelta(days=30)
            t_minus_365 = t_date - pd.Timedelta(days=365)

            if f"{var}_lag7" in feature_cols:
                all_df.loc[t_date, f"{var}_lag7"] = all_df.loc[t_minus_7, var] if t_minus_7 in all_df.index else 0
            if f"{var}_lag30" in feature_cols:
                all_df.loc[t_date, f"{var}_lag30"] = all_df.loc[t_minus_30, var] if t_minus_30 in all_df.index else 0
            if f"{var}_lag365" in feature_cols:
                all_df.loc[t_date, f"{var}_lag365"] = all_df.loc[t_minus_365, var] if t_minus_365 in all_df.index else 0

            if f"{var}_roll7" in feature_cols:
                p7 = [t_date - pd.Timedelta(days=i) for i in range(1, 8)]
                valid_p7 = [d for d in p7 if d in all_df.index]
                all_df.loc[t_date, f"{var}_roll7"] = all_df.loc[valid_p7, var].mean() if valid_p7 else 0

            if f"{var}_roll30" in feature_cols:
                p30 = [t_date - pd.Timedelta(days=i) for i in range(1, 31)]
                valid_p30 = [d for d in p30 if d in all_df.index]
                all_df.loc[t_date, f"{var}_roll30"] = all_df.loc[valid_p30, var].mean() if valid_p30 else 0

        X_t = all_df.loc[[t_date], feature_cols].fillna(0)
        rev_pred = revenue_model.predict(X_t)[0]
        all_df.loc[t_date, "Revenue"] = rev_pred

        if cogs_model is not None:
            cogs_pred = cogs_model.predict(X_t)[0]
            all_df.loc[t_date, "COGS"] = cogs_pred
        else:
            all_df.loc[t_date, "COGS"] = 0

    full_output = sample_df[["Date"]].copy()
    full_output = full_output.merge(all_df[["Revenue", "COGS"]], left_on="Date", right_index=True, how="left")
    full_output["Profit"] = full_output["Revenue"] - full_output["COGS"]

    output_dir.mkdir(parents=True, exist_ok=True)
    submission_path = output_dir / "submission.csv"
    full_output[["Date", "Revenue", "COGS"]].to_csv(submission_path, index=False)

    analysis_path = output_dir / "analysis_report.csv"
    full_output.to_csv(analysis_path, index=False)

    if verbose:
        logger.info("  Prediction complete!")
        logger.info(f"  Predicted {len(full_output)} rows recursively.")
        logger.info(f"  Revenue range: {full_output['Revenue'].min():,.2f} — {full_output['Revenue'].max():,.2f}")
        if cogs_model is not None:
            logger.info(f"  COGS range   : {full_output['COGS'].min():,.2f} — {full_output['COGS'].max():,.2f}")
        logger.info(f"  Profit range : {full_output['Profit'].min():,.2f} — {full_output['Profit'].max():,.2f}")
        logger.info(f"  ✅ Submission saved (3 cols)  : {submission_path}")
        logger.info(f"  📊 Analysis saved (with Profit): {analysis_path}")

    return full_output


if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    generate_submission(
        model_path=project_root / "models/xgboost_revenue_model.joblib",
        feature_table_path=project_root / "data/output/featured_table.parquet",
        sample_submission_path=project_root / "data/raw/sample_submission.csv",
        output_dir=project_root / "data/output",
        cogs_model_path=project_root / "models/xgboost_cogs_model.joblib",
    )
