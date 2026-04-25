import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import joblib
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from src.logger import logger

# 1. Reproducibility: Set Random Seed
np.random.seed(42)


def _train_single_target(
    X: pd.DataFrame,
    y: pd.Series,
    target_name: str,
    weights: pd.Series = None,
    n_splits: int = 5,
    verbose: bool = True,
) -> xgb.XGBRegressor:
    """
    Internal helper: train XGBoost with TimeSeriesSplit cross-validation,
    then fit a final model on all data. Returns the final fitted model.
    """
    tscv = TimeSeriesSplit(n_splits=n_splits)
    scores = []

    for fold, (train_idx, val_idx) in enumerate(tscv.split(X)):
        X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]
        w_train = weights.iloc[train_idx] if weights is not None else None

        model = xgb.XGBRegressor(
            n_estimators=1000,
            learning_rate=0.05,
            max_depth=5,
            subsample=0.8,
            colsample_bytree=0.8,
            n_jobs=-1,
            random_state=42,
            early_stopping_rounds=50,
        )
        model.fit(X_train, y_train, sample_weight=w_train, eval_set=[(X_val, y_val)], verbose=False)

        preds = model.predict(X_val)
        mae  = mean_absolute_error(y_val, preds)
        rmse = np.sqrt(mean_squared_error(y_val, preds))
        r2   = r2_score(y_val, preds)
        scores.append(mae)

        if verbose:
            logger.info(
                f"     [{target_name}] Fold {fold + 1} | "
                f"MAE: {mae:,.2f} | RMSE: {rmse:,.2f} | R2: {r2:.4f}"
            )

    avg_mae = np.mean(scores)
    if verbose:
        logger.info(
            f"  Cross-Validation complete for '{target_name}'. "
            f"Avg MAE: {avg_mae:,.2f}"
        )

    # Final model trained on ALL data
    final_model = xgb.XGBRegressor(
        n_estimators=500,
        learning_rate=0.05,
        max_depth=5,
        random_state=42,
    )
    final_model.fit(X, y, sample_weight=weights)
    return final_model


def train_revenue_model(
    feature_table_path: Path,
    model_output_dir: Path,
    report_output_dir: Path,
    train_until: str = None,
    verbose: bool = True,
):
    """
    Trains TWO XGBoost Regressors:
      1. Revenue model  → xgboost_revenue_model.joblib
      2. COGS model     → xgboost_cogs_model.joblib   (Fix: Audit Issue #3)

    Both targets come from sales.csv (Revenue and COGS columns).
    Uses TimeSeriesSplit for validation.
    """
    if verbose:
        logger.info("  Starting Model Training (XGBoost — Revenue + COGS)...")

    # 2. Load Data
    if not feature_table_path.exists():
        raise FileNotFoundError(f"Feature table not found at {feature_table_path}")

    df = pd.read_parquet(feature_table_path, engine="pyarrow")
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date")  # Chronological order for TimeSeriesSplit

    # Identify candidate features
    drop_cols = ["Date", "Revenue", "COGS"]
    all_features = [c for c in df.columns if c not in drop_cols]
    
    # Filter only numeric types
    features_numeric = [c for c in all_features if pd.api.types.is_numeric_dtype(df[c])]

    # --- ANTI-LEAKAGE FILTER ---
    # We must ONLY use features that are available at the START of the day.
    # Safe features are: Lags, Rolling windows, and Calendar/Holiday features.
    # Unsafe features are: Lag-0 aggregates (daily_order_count, daily_total_item_revenue, etc.)
    
    safe_patterns = [
        "_lag", "_roll", "day_", "week_", "month_", "year_", 
        "is_holiday", "days_until_holiday",
        "covid_intensity"  # Deterministic & safe for current day
    ]
    features = [
        c for c in features_numeric 
        if any(pat in c for pat in safe_patterns)
    ]

    if verbose:
        logger.info(f"     Feature count (After Leakage Filter): {len(features)}")
        logger.info(f"     Selected Features: {features}")

    if verbose:
        logger.info(f"     Feature count : {len(features)}")
        logger.info(f"     Features      : {features}")

    # Split into train / holdout if train_until is given
    if train_until:
        if verbose:
            logger.info(f"  Isolating data: Training strictly before {train_until}")
        train_df = df[df["Date"] < train_until].copy()
        test_df  = df[df["Date"] >= train_until].copy()
    else:
        if verbose:
            logger.info("  Full Training Mode: Using all available data.")
        train_df = df.copy()
        test_df  = pd.DataFrame()

    if verbose:
        logger.info(f"     Training days : {len(train_df)}")

    X = train_df[features]
    weights = train_df["sample_weight"] if "sample_weight" in train_df.columns else None

    # ── 3a. Train Revenue Model ───────────────────────────────────────────────
    if verbose:
        logger.info("  Training Revenue model...")

    if "Revenue" not in train_df.columns or train_df["Revenue"].isna().all():
        raise ValueError("Revenue column missing or all-null in feature table.")

    y_revenue = train_df["Revenue"]
    revenue_model = _train_single_target(X, y_revenue, "Revenue", weights=weights, verbose=verbose)

    # ── 3b. Train COGS Model (Fix: Audit Issue #3) ────────────────────────────
    if verbose:
        logger.info("  Training COGS model...")

    if "COGS" in train_df.columns and not train_df["COGS"].isna().all():
        y_cogs = train_df["COGS"]
        cogs_model = _train_single_target(X, y_cogs, "COGS", weights=weights, verbose=verbose)
        has_cogs_model = True
    else:
        logger.warning("  COGS column missing or all-null — COGS model not trained.")
        cogs_model = None
        has_cogs_model = False

    # ── 4. Holdout Evaluation ─────────────────────────────────────────────────
    if not test_df.empty:
        X_test = test_df[features]

        for target_name, model in [("Revenue", revenue_model), ("COGS", cogs_model)]:
            if model is None:
                continue
            if target_name not in test_df.columns or test_df[target_name].isna().all():
                continue
            y_test = test_df[target_name]
            preds  = model.predict(X_test)
            mae    = mean_absolute_error(y_test, preds)
            rmse   = np.sqrt(mean_squared_error(y_test, preds))
            r2     = r2_score(y_test, preds)
            if verbose:
                logger.info(
                    f"  HOLDOUT [{target_name}] | "
                    f"MAE: {mae:,.2f} | RMSE: {rmse:,.2f} | R2: {r2:.4f}"
                )

    # ── 5. Save Models ────────────────────────────────────────────────────────
    model_output_dir.mkdir(parents=True, exist_ok=True)

    revenue_path = model_output_dir / "xgboost_revenue_model.joblib"
    joblib.dump(revenue_model, revenue_path)
    if verbose:
        logger.info(f"  Revenue model saved to: {revenue_path}")

    if has_cogs_model:
        cogs_path = model_output_dir / "xgboost_cogs_model.joblib"
        joblib.dump(cogs_model, cogs_path)
        if verbose:
            logger.info(f"  COGS model saved to: {cogs_path}")

    # ── 6. Feature Importance (Revenue) ──────────────────────────────────────
    plt.figure(figsize=(10, 6))
    importance_df = pd.DataFrame({
        "Feature":    features,
        "Importance": revenue_model.feature_importances_,
    }).sort_values("Importance", ascending=False)

    top_n = min(15, len(features))
    sns.barplot(
        data=importance_df.head(top_n),
        x="Importance",
        y="Feature",
        hue="Feature",
        palette="viridis",
        legend=False,
    )
    plt.title(f"Top {top_n} Feature Importances (Daily Revenue Prediction)")
    plt.tight_layout()

    report_output_dir.mkdir(parents=True, exist_ok=True)
    plot_path = report_output_dir / "feature_importance.png"
    plt.savefig(plot_path)
    plt.close()

    if verbose:
        logger.info(f"  Feature Importance plot saved to: {plot_path}")

    return revenue_model


if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    train_revenue_model(
        project_root / "data/output/featured_table.parquet",
        project_root / "models",
        project_root / "reports",
    )
