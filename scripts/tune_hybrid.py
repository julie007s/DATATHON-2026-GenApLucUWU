from __future__ import annotations

import argparse
import json
from itertools import product
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import TimeSeriesSplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ensemble import (  # noqa: E402
    blend_residual_predictions,
    fit_arima_model,
    forecast_arima_baseline,
    get_arima_in_sample_baseline,
    log_progress,
    log_stage,
    train_elasticnet_model,
)
from src.feature_contract import get_model_feature_columns  # noqa: E402
from src.logger import logger  # noqa: E402


DEFAULT_ORDERS = [
    (1, 0, 0),
    (1, 1, 0),
    (2, 1, 0),
    (3, 1, 0),
    (5, 1, 0),
    (3, 1, 1),
    (3, 1, 2),
    (5, 1, 1),
    (7, 1, 1),
    (7, 1, 2),
    (14, 1, 1),
]

DEFAULT_WEIGHT_GRID = [
    {"xgboost": 1.00, "elasticnet": 0.00},
    {"xgboost": 0.95, "elasticnet": 0.05},
    {"xgboost": 0.90, "elasticnet": 0.10},
    {"xgboost": 0.85, "elasticnet": 0.15},
    {"xgboost": 0.80, "elasticnet": 0.20},
    {"xgboost": 0.75, "elasticnet": 0.25},
    {"xgboost": 0.70, "elasticnet": 0.30},
]


def _parse_order_grid(value: str | None) -> list[tuple[int, int, int]]:
    if not value:
        return DEFAULT_ORDERS
    orders = []
    for chunk in value.split(";"):
        parts = [int(x.strip()) for x in chunk.split(",")]
        if len(parts) != 3:
            raise ValueError(f"Invalid order '{chunk}'. Expected p,d,q")
        orders.append(tuple(parts))
    return orders


def _score_arima_order(
    y: pd.Series,
    order: tuple[int, int, int],
    n_splits: int,
    target_name: str,
) -> dict:
    tscv = TimeSeriesSplit(n_splits=n_splits)
    fold_scores = []
    for fold, (train_idx, val_idx) in enumerate(tscv.split(y), start=1):
        y_train = y.iloc[train_idx]
        y_val = y.iloc[val_idx]
        model = fit_arima_model(y_train, order=order)
        pred = forecast_arima_baseline(model, len(y_val))
        mae = mean_absolute_error(y_val, pred)
        fold_scores.append(float(mae))
        log_progress(f"ARIMA {target_name} {order}", fold, n_splits, extra=f"MAE={mae:,.0f}")
    return {
        "target": target_name,
        "stage": "arima_order",
        "order": str(order),
        "mae": float(np.mean(fold_scores)),
        "fold_mae": fold_scores,
    }


def search_arima_orders(
    y: pd.Series,
    orders: list[tuple[int, int, int]],
    n_splits: int,
    target_name: str,
) -> tuple[tuple[int, int, int], list[dict]]:
    log_stage(f"ARIMA order search started for {target_name}")
    results = []
    for idx, order in enumerate(orders, start=1):
        try:
            log_progress(f"ARIMA order candidates for {target_name}", idx, len(orders), extra=str(order))
            result = _score_arima_order(y, order, n_splits, target_name)
        except Exception as exc:
            logger.warning(f"  ARIMA order {order} failed for {target_name}: {exc}")
            result = {
                "target": target_name,
                "stage": "arima_order",
                "order": str(order),
                "mae": float("inf"),
                "fold_mae": [],
                "error": str(exc),
            }
        results.append(result)
    best = min(results, key=lambda r: r["mae"])
    best_order = tuple(int(x) for x in best["order"].strip("()").split(","))
    logger.info(f"  Best ARIMA order for {target_name}: {best_order} | MAE={best['mae']:,.2f}")
    return best_order, results


def _score_residual_weights(
    X: pd.DataFrame,
    y: pd.Series,
    order: tuple[int, int, int],
    weight_grid: list[dict[str, float]],
    n_splits: int,
    target_name: str,
    sample_weight: pd.Series | None = None,
) -> list[dict]:
    tscv = TimeSeriesSplit(n_splits=n_splits)
    fold_predictions = []

    log_stage(f"Residual prediction cache started for {target_name} using ARIMA order {order}")
    for fold, (train_idx, val_idx) in enumerate(tscv.split(X), start=1):
        X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]
        w_train = sample_weight.iloc[train_idx] if sample_weight is not None else None

        arima = fit_arima_model(y_train, order=order)
        train_baseline = get_arima_in_sample_baseline(arima, y_train)
        val_baseline = forecast_arima_baseline(arima, len(y_val))
        residual_train = y_train - train_baseline

        xgb_model = xgb.XGBRegressor(
            n_estimators=600,
            learning_rate=0.05,
            max_depth=5,
            subsample=0.8,
            colsample_bytree=0.8,
            n_jobs=-1,
            random_state=42,
        )
        xgb_model.fit(X_train, residual_train, sample_weight=w_train)
        enet_model = train_elasticnet_model(X_train, residual_train)

        fold_predictions.append({
            "fold": fold,
            "y_val": y_val,
            "baseline": val_baseline,
            "xgboost": xgb_model.predict(X_val),
            "elasticnet": enet_model.predict(X_val),
        })
        log_progress(f"Residual folds cached for {target_name}", fold, n_splits)

    results = []
    for weights in weight_grid:
        scores = []
        for fp in fold_predictions:
            residual = blend_residual_predictions(
                {"xgboost": fp["xgboost"], "elasticnet": fp["elasticnet"]},
                weights,
            )
            final_pred = fp["baseline"] + residual
            scores.append(float(mean_absolute_error(fp["y_val"], final_pred)))
        results.append({
            "target": target_name,
            "stage": "residual_weight",
            "order": str(order),
            "weights": json.dumps(weights),
            "mae": float(np.mean(scores)),
            "fold_mae": scores,
        })
        logger.info(f"  Weight trial {target_name} {weights} | MAE={np.mean(scores):,.2f}")
    return results


def tune_hybrid(
    feature_table_path: Path,
    report_dir: Path,
    n_splits: int,
    order_grid: list[tuple[int, int, int]],
    max_rows: int | None = None,
) -> dict:
    log_stage("Loading feature table for hybrid tuning")
    df = pd.read_parquet(feature_table_path, engine="pyarrow")
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date")
    if max_rows:
        df = df.tail(max_rows).copy()
        logger.info(f"  Using last {len(df)} rows for faster tuning")

    features = get_model_feature_columns(df)
    X = df[features].fillna(0)
    sample_weight = df["sample_weight"] if "sample_weight" in df.columns else None

    all_results = []
    best_config = {
        "architecture": "arima_first_residual_hybrid",
        "n_splits": n_splits,
        "features": features,
        "targets": {},
    }

    for target_name in ["Revenue", "COGS"]:
        if target_name not in df.columns or df[target_name].isna().all():
            logger.warning(f"  Skipping {target_name}: missing or all-null")
            continue

        y = df[target_name].astype(float)
        best_order, arima_results = search_arima_orders(y, order_grid, n_splits, target_name)
        all_results.extend(arima_results)

        weight_results = _score_residual_weights(
            X,
            y,
            best_order,
            DEFAULT_WEIGHT_GRID,
            n_splits,
            target_name,
            sample_weight=sample_weight,
        )
        all_results.extend(weight_results)
        best_weight_result = min(weight_results, key=lambda r: r["mae"])
        best_weights = json.loads(best_weight_result["weights"])

        best_config["targets"][target_name] = {
            "arima_order": list(best_order),
            "residual_weights": best_weights,
            "best_arima_mae": min(arima_results, key=lambda r: r["mae"])["mae"],
            "best_hybrid_mae": best_weight_result["mae"],
        }
        logger.info(
            f"  Best hybrid config for {target_name}: order={best_order}, "
            f"weights={best_weights}, MAE={best_weight_result['mae']:,.2f}"
        )

    report_dir.mkdir(parents=True, exist_ok=True)
    results_df = pd.DataFrame(all_results)
    results_path = report_dir / "hybrid_tuning_results.csv"
    results_df.to_csv(results_path, index=False)

    config_path = report_dir / "best_hybrid_config.json"
    config_path.write_text(json.dumps(best_config, indent=2), encoding="utf-8")

    logger.info(f"  Hybrid tuning results saved to: {results_path}")
    logger.info(f"  Best hybrid config saved to: {config_path}")
    return best_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Tune ARIMA-first residual hybrid forecasting config.")
    parser.add_argument("--feature-table", type=Path, default=PROJECT_ROOT / "data/output/featured_table.parquet")
    parser.add_argument("--report-dir", type=Path, default=PROJECT_ROOT / "reports")
    parser.add_argument("--splits", type=int, default=3, help="TimeSeriesSplit folds. Use 3 for speed, 5 for stronger validation.")
    parser.add_argument("--orders", type=str, default=None, help="Semicolon-separated ARIMA orders, e.g. '1,1,0;3,1,1;7,1,1'")
    parser.add_argument("--max-rows", type=int, default=None, help="Optional tail rows for faster experiments.")
    args = parser.parse_args()

    order_grid = _parse_order_grid(args.orders)
    tune_hybrid(args.feature_table, args.report_dir, args.splits, order_grid, max_rows=args.max_rows)


if __name__ == "__main__":
    main()
