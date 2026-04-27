import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit

from src.ensemble import (
    DEFAULT_RESIDUAL_WEIGHTS,
    blend_residual_predictions,
    fit_arima_model,
    forecast_arima_baseline,
    get_arima_in_sample_baseline,
    get_target_hybrid_config,
    load_best_hybrid_config,
    log_progress,
    log_stage,
    save_hybrid_metadata,
    save_model,
    train_elasticnet_model,
)
from src.feature_contract import get_model_feature_columns
from src.logger import logger

np.random.seed(42)


def _evaluate_predictions(y_true: pd.Series, preds: np.ndarray) -> tuple[float, float, float]:
    mae = mean_absolute_error(y_true, preds)
    rmse = np.sqrt(mean_squared_error(y_true, preds))
    r2 = r2_score(y_true, preds)
    return mae, rmse, r2


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


def _train_xgboost_residual_model(
    X: pd.DataFrame,
    residual: pd.Series,
    target_name: str,
    weights: pd.Series | None = None,
    locked_xgb_config: dict | None = None,
) -> xgb.XGBRegressor:
    log_stage(f"Fitting final XGBoost residual model for {target_name}")
    locked_xgb_config = locked_xgb_config or {}
    params = locked_xgb_config.get("params", {})
    n_estimators = int(locked_xgb_config.get("locked_n_estimators", 500))
    if locked_xgb_config:
        logger.info(f"     Using locked XGB config for {target_name}: n_estimators={n_estimators}, params={params}")
    model = xgb.XGBRegressor(
        objective="reg:squarederror",
        n_estimators=n_estimators,
        learning_rate=params.get("learning_rate", 0.05),
        max_depth=params.get("max_depth", 5),
        subsample=params.get("subsample", 0.8),
        colsample_bytree=params.get("colsample_bytree", 0.8),
        min_child_weight=params.get("min_child_weight", 1),
        reg_alpha=params.get("reg_alpha", 0.0),
        reg_lambda=params.get("reg_lambda", 1.0),
        n_jobs=-1,
        random_state=42,
    )
    model.fit(X, residual, sample_weight=weights)
    return model


def _run_hybrid_cv(
    X: pd.DataFrame,
    y: pd.Series,
    target_name: str,
    weights: pd.Series | None = None,
    n_splits: int = 5,
    verbose: bool = True,
    arima_order: tuple[int, int, int] = (7, 1, 1),
    residual_weights: dict[str, float] | None = None,
) -> dict[str, float]:
    tscv = TimeSeriesSplit(n_splits=n_splits)
    arima_scores = []
    hybrid_scores = []

    if verbose:
        log_stage(f"Hybrid CV started for {target_name}")

    for fold, (train_idx, val_idx) in enumerate(tscv.split(X), start=1):
        X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]
        w_train = weights.iloc[train_idx] if weights is not None else None

        if verbose:
            log_progress(
                f"Hybrid {target_name} folds",
                fold,
                n_splits,
                extra=f"train={len(train_idx)} val={len(val_idx)}",
            )

        arima_model = fit_arima_model(y_train, order=arima_order)
        train_baseline = get_arima_in_sample_baseline(arima_model, y_train)
        val_baseline = forecast_arima_baseline(arima_model, len(y_val))
        residual_train = y_train - train_baseline

        xgb_model = xgb.XGBRegressor(
            n_estimators=1000,
            learning_rate=0.05,
            max_depth=5,
            subsample=0.8,
            colsample_bytree=0.8,
            n_jobs=-1,
            random_state=42,
            early_stopping_rounds=50,
        )
        xgb_model.fit(
            X_train,
            residual_train,
            sample_weight=w_train,
            eval_set=[(X_val, y_val - val_baseline)],
            verbose=False,
        )
        enet_model = train_elasticnet_model(X_train, residual_train)

        xgb_residual = xgb_model.predict(X_val)
        enet_residual = enet_model.predict(X_val)
        residual_blend = blend_residual_predictions(
            {"xgboost": xgb_residual, "elasticnet": enet_residual},
            residual_weights or DEFAULT_RESIDUAL_WEIGHTS,
        )
        hybrid_pred = val_baseline + residual_blend

        arima_mae, arima_rmse, arima_r2 = _evaluate_predictions(y_val, val_baseline)
        hybrid_mae, hybrid_rmse, hybrid_r2 = _evaluate_predictions(y_val, hybrid_pred)
        arima_scores.append(arima_mae)
        hybrid_scores.append(hybrid_mae)

        if verbose:
            logger.info(
                f"     [ARIMA baseline:{target_name}] Fold {fold} | "
                f"MAE: {arima_mae:,.2f} | RMSE: {arima_rmse:,.2f} | R2: {arima_r2:.4f}"
            )
            logger.info(
                f"     [Hybrid residual:{target_name}] Fold {fold} | "
                f"MAE: {hybrid_mae:,.2f} | RMSE: {hybrid_rmse:,.2f} | R2: {hybrid_r2:.4f}"
            )

    avg_arima = float(np.mean(arima_scores))
    avg_hybrid = float(np.mean(hybrid_scores))
    if verbose:
        logger.info(f"  ARIMA baseline CV complete for '{target_name}'. Avg MAE: {avg_arima:,.2f}")
        logger.info(f"  Hybrid residual CV complete for '{target_name}'. Avg MAE: {avg_hybrid:,.2f}")
    return {"arima_mae": avg_arima, "hybrid_mae": avg_hybrid}


def _save_feature_metadata(model_output_dir: Path, features: list[str]) -> Path:
    metadata_path = model_output_dir / "model_features.json"
    metadata_path.write_text(json.dumps({"features": features}, indent=2), encoding="utf-8")
    return metadata_path


def _train_target_hybrid_bundle(
    X: pd.DataFrame,
    y: pd.Series,
    target_name: str,
    model_output_dir: Path,
    weights: pd.Series | None = None,
    verbose: bool = True,
    arima_order: tuple[int, int, int] = (7, 1, 1),
    residual_weights: dict[str, float] | None = None,
    locked_xgb_config: dict | None = None,
) -> dict[str, object]:
    if verbose:
        log_stage(f"Training ARIMA-first residual hybrid bundle for {target_name}")
        logger.info(f"     ARIMA order      : {arima_order}")
        logger.info(f"     Residual weights : {residual_weights or DEFAULT_RESIDUAL_WEIGHTS}")

    cv_metrics = _run_hybrid_cv(
        X,
        y,
        target_name,
        weights=weights,
        verbose=verbose,
        arima_order=arima_order,
        residual_weights=residual_weights,
    )

    if verbose:
        log_stage(f"Fitting final ARIMA baseline for {target_name}")
    arima_model = fit_arima_model(y, order=arima_order)
    arima_baseline = get_arima_in_sample_baseline(arima_model, y)
    residual = y - arima_baseline

    if verbose:
        logger.info(
            f"  Residual diagnostics [{target_name}] | "
            f"mean={residual.mean():,.2f} | std={residual.std():,.2f} | "
            f"min={residual.min():,.2f} | max={residual.max():,.2f}"
        )

    xgb_residual_model = _train_xgboost_residual_model(
        X,
        residual,
        target_name,
        weights=weights,
        locked_xgb_config=locked_xgb_config,
    )
    if verbose:
        log_stage(f"Fitting final ElasticNet residual model for {target_name}")
    enet_residual_model = train_elasticnet_model(X, residual)

    save_model(model_output_dir / f"arima_{target_name.lower()}_baseline.joblib", arima_model)
    save_model(model_output_dir / f"xgboost_{target_name.lower()}_residual.joblib", xgb_residual_model)
    save_model(model_output_dir / f"elasticnet_{target_name.lower()}_residual.joblib", enet_residual_model)

    if verbose:
        log_stage(f"Saved hybrid residual artifacts for {target_name}")

    return {
        "arima": arima_model,
        "xgboost_residual": xgb_residual_model,
        "elasticnet_residual": enet_residual_model,
        "cv_metrics": cv_metrics,
    }


def train_revenue_model(
    feature_table_path: Path,
    model_output_dir: Path,
    report_output_dir: Path,
    train_until: str = None,
    verbose: bool = True,
):
    if verbose:
        logger.info("  Starting ARIMA-first Residual Hybrid Training...")
        log_stage("Loading feature table for hybrid residual training")

    if not feature_table_path.exists():
        raise FileNotFoundError(f"Feature table not found at {feature_table_path}")

    df = pd.read_parquet(feature_table_path, engine="pyarrow")
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date")

    features = get_model_feature_columns(df)
    if not features:
        raise ValueError("No leakage-safe model features were found in featured_table.parquet")

    if verbose:
        logger.info(f"     Feature count (leakage-safe): {len(features)}")
        logger.info(f"     Selected Features: {features}")

    tuning_config = load_best_hybrid_config(report_output_dir)
    target_configs = tuning_config.get("targets", {})
    locked_xgb_config = _load_locked_xgb_config(report_output_dir, "arima_hybrid")
    if verbose:
        if target_configs:
            log_stage(f"Loaded tuned hybrid config from {report_output_dir / 'best_hybrid_config.json'}")
        else:
            log_stage("No tuned hybrid config found; using default ARIMA order and residual weights")
        if locked_xgb_config.get("targets"):
            log_stage(f"Loaded locked XGBoost estimator config from {report_output_dir / 'best_xgb_config.json'}")

    if train_until:
        if verbose:
            logger.info(f"  Isolating data: Training strictly before {train_until}")
        train_df = df[df["Date"] < train_until].copy()
        test_df = df[df["Date"] >= train_until].copy()
    else:
        if verbose:
            logger.info("  Full Training Mode: Using all available data.")
        train_df = df.copy()
        test_df = pd.DataFrame()

    if verbose:
        logger.info(f"     Training days : {len(train_df)}")

    X = train_df[features].fillna(0)
    weights = train_df["sample_weight"] if "sample_weight" in train_df.columns else None

    if verbose and weights is not None:
        logger.info(f"     Sample weight range: {weights.min():.3f} — {weights.max():.3f}")

    if "Revenue" not in train_df.columns or train_df["Revenue"].isna().all():
        raise ValueError("Revenue column missing or all-null in feature table.")

    model_output_dir.mkdir(parents=True, exist_ok=True)

    revenue_order, revenue_weights = get_target_hybrid_config(tuning_config, "Revenue")
    revenue_bundle = _train_target_hybrid_bundle(
        X,
        train_df["Revenue"],
        "Revenue",
        model_output_dir,
        weights=weights,
        verbose=verbose,
        arima_order=revenue_order,
        residual_weights=revenue_weights,
        locked_xgb_config=_get_locked_xgb_target_config(locked_xgb_config, "Revenue_Residual"),
    )

    cogs_bundle = None
    if "COGS" in train_df.columns and not train_df["COGS"].isna().all():
        cogs_order, cogs_weights = get_target_hybrid_config(tuning_config, "COGS")
        cogs_bundle = _train_target_hybrid_bundle(
            X,
            train_df["COGS"],
            "COGS",
            model_output_dir,
            weights=weights,
            verbose=verbose,
            arima_order=cogs_order,
            residual_weights=cogs_weights,
            locked_xgb_config=_get_locked_xgb_target_config(locked_xgb_config, "COGS_Residual"),
        )
    else:
        logger.warning("  COGS column missing or all-null — COGS hybrid bundle not trained.")

    if not test_df.empty:
        if verbose:
            log_stage("Running holdout diagnostics for hybrid residual bundles")
        X_test = test_df[features].fillna(0)
        for target_name, bundle in [("Revenue", revenue_bundle), ("COGS", cogs_bundle)]:
            if bundle is None or target_name not in test_df.columns or test_df[target_name].isna().all():
                continue
            y_test = test_df[target_name]
            baseline = forecast_arima_baseline(bundle["arima"], len(y_test))
            residual_blend = blend_residual_predictions(
                {
                    "xgboost": bundle["xgboost_residual"].predict(X_test),
                    "elasticnet": bundle["elasticnet_residual"].predict(X_test),
                },
                get_target_hybrid_config(tuning_config, target_name)[1],
            )
            hybrid_pred = baseline + residual_blend
            mae, rmse, r2 = _evaluate_predictions(y_test, hybrid_pred)
            logger.info(
                f"  HOLDOUT [Hybrid:{target_name}] | "
                f"MAE: {mae:,.2f} | RMSE: {rmse:,.2f} | R2: {r2:.4f}"
            )

    metadata_path = _save_feature_metadata(model_output_dir, features)
    hybrid_metadata_path = save_hybrid_metadata(model_output_dir, features, target_configs)
    if locked_xgb_config:
        locked_metadata_path = model_output_dir / "arima_hybrid_locked_xgb_config.json"
        locked_metadata_path.write_text(json.dumps(locked_xgb_config, indent=2), encoding="utf-8")
    if verbose:
        logger.info(f"  Feature metadata saved to: {metadata_path}")
        logger.info(f"  Hybrid metadata saved to: {hybrid_metadata_path}")
        log_stage("Generating residual XGBoost feature importance report")

    plt.figure(figsize=(10, 6))
    importance_df = pd.DataFrame({
        "Feature": features,
        "Importance": revenue_bundle["xgboost_residual"].feature_importances_,
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
    plt.title(f"Top {top_n} XGBoost Feature Importances (Revenue Residual Prediction)")
    plt.tight_layout()

    report_output_dir.mkdir(parents=True, exist_ok=True)
    plot_path = report_output_dir / "feature_importance.png"
    plt.savefig(plot_path)
    plt.close()

    if verbose:
        logger.info(f"  Feature Importance plot saved to: {plot_path}")
        log_stage("ARIMA-first residual hybrid training finished")

    return revenue_bundle


if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    train_revenue_model(
        project_root / "data/output/featured_table.parquet",
        project_root / "models",
        project_root / "reports",
    )
