from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import TimeSeriesSplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ensemble import fit_arima_model, forecast_arima_baseline, get_arima_in_sample_baseline, log_progress, log_stage  # noqa: E402
from src.feature_contract import get_model_feature_columns  # noqa: E402
from src.logger import logger  # noqa: E402
from src.seasonal_baseline import build_in_sample_seasonal_baseline  # noqa: E402

DEFAULT_PARAM_GRID = [
    {"learning_rate": 0.05, "max_depth": 4, "subsample": 0.85, "colsample_bytree": 0.85, "min_child_weight": 3, "reg_alpha": 0.1, "reg_lambda": 3.0},
    {"learning_rate": 0.04, "max_depth": 5, "subsample": 0.85, "colsample_bytree": 0.85, "min_child_weight": 3, "reg_alpha": 0.1, "reg_lambda": 3.0},
    {"learning_rate": 0.03, "max_depth": 5, "subsample": 0.80, "colsample_bytree": 0.80, "min_child_weight": 5, "reg_alpha": 0.3, "reg_lambda": 5.0},
    {"learning_rate": 0.03, "max_depth": 6, "subsample": 0.80, "colsample_bytree": 0.80, "min_child_weight": 5, "reg_alpha": 0.5, "reg_lambda": 8.0},
]


def _auto_growth_factor(n_splits: int) -> float:
    return float(min(1.25, 1.0 + 1.0 / max(n_splits, 1)))


def _make_xgb(params: dict, early_stopping_rounds: int, max_estimators: int) -> xgb.XGBRegressor:
    return xgb.XGBRegressor(
        objective="reg:squarederror",
        n_estimators=max_estimators,
        early_stopping_rounds=early_stopping_rounds,
        n_jobs=-1,
        random_state=42,
        **params,
    )


def _score_xgb_target(
    X: pd.DataFrame,
    y: pd.Series,
    sample_weight: pd.Series | None,
    target_key: str,
    n_splits: int,
    growth_factor: float,
    early_stopping_rounds: int,
    max_estimators: int,
) -> tuple[dict, list[dict]]:
    tscv = TimeSeriesSplit(n_splits=n_splits)
    results = []
    log_stage(f"Locked-estimator XGBoost tuning started for {target_key}")

    for param_idx, params in enumerate(DEFAULT_PARAM_GRID, start=1):
        fold_mae = []
        fold_best_iterations = []
        for fold, (train_idx, val_idx) in enumerate(tscv.split(X), start=1):
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]
            w_train = sample_weight.iloc[train_idx] if sample_weight is not None else None

            model = _make_xgb(params, early_stopping_rounds, max_estimators)
            model.fit(
                X_train,
                y_train,
                sample_weight=w_train,
                eval_set=[(X_val, y_val)],
                verbose=False,
            )
            pred = model.predict(X_val)
            mae = float(mean_absolute_error(y_val, pred))
            best_iteration = int(getattr(model, "best_iteration", max_estimators - 1)) + 1
            fold_mae.append(mae)
            fold_best_iterations.append(best_iteration)
            log_progress(
                f"XGB {target_key} params {param_idx}/{len(DEFAULT_PARAM_GRID)}",
                fold,
                n_splits,
                extra=f"MAE={mae:,.4f} best_iter={best_iteration}",
            )

        locked_n = int(math.ceil(float(np.median(fold_best_iterations)) * growth_factor))
        locked_n = max(25, min(locked_n, max_estimators))
        result = {
            "target_key": target_key,
            "param_index": param_idx,
            "params": params,
            "cv_mae": float(np.mean(fold_mae)),
            "fold_mae": fold_mae,
            "cv_best_iterations": fold_best_iterations,
            "median_best_iteration": float(np.median(fold_best_iterations)),
            "growth_factor": growth_factor,
            "locked_n_estimators": locked_n,
        }
        results.append(result)
        logger.info(
            f"  XGB trial {target_key} #{param_idx} | MAE={result['cv_mae']:,.4f} | "
            f"median_iter={result['median_best_iteration']:.1f} | locked_n={locked_n}"
        )

    best = min(results, key=lambda r: r["cv_mae"])
    logger.info(f"  Best XGB locked config for {target_key}: MAE={best['cv_mae']:,.4f}, locked_n={best['locked_n_estimators']}")
    return best, results


def _prepare_targets(
    df: pd.DataFrame,
    X: pd.DataFrame,
    model_arch: str,
) -> dict[str, pd.Series]:
    targets: dict[str, pd.Series] = {}
    if model_arch == "seasonal_xgb_ratio":
        revenue_baseline = build_in_sample_seasonal_baseline(df, "Revenue")
        targets["Revenue_Residual"] = df["Revenue"].astype(float) - revenue_baseline.astype(float)
        safe_revenue = df["Revenue"].replace(0, np.nan).astype(float)
        ratio = (df["COGS"].astype(float) / safe_revenue).replace([np.inf, -np.inf], np.nan)
        targets["COGS_Ratio"] = ratio.fillna(ratio.median()).clip(lower=0.0, upper=2.0)
        return targets

    if model_arch == "arima_hybrid":
        for target_name in ["Revenue", "COGS"]:
            arima_model = fit_arima_model(df[target_name].astype(float))
            baseline = get_arima_in_sample_baseline(arima_model, df[target_name].astype(float))
            targets[f"{target_name}_Residual"] = df[target_name].astype(float) - baseline.astype(float)
        return targets

    raise ValueError(f"Unsupported model_arch: {model_arch}")


def tune_locked_estimators(
    feature_table_path: Path,
    report_dir: Path,
    model_arch: str,
    n_splits: int,
    growth_factor: float | None,
    max_rows: int | None,
    early_stopping_rounds: int,
    max_estimators: int,
) -> dict:
    if model_arch not in {"arima_hybrid", "seasonal_xgb_ratio"}:
        raise ValueError("model_arch must be 'arima_hybrid' or 'seasonal_xgb_ratio'")

    log_stage("Loading feature table for locked XGBoost tuning")
    df = pd.read_parquet(feature_table_path, engine="pyarrow")
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    if max_rows:
        df = df.tail(max_rows).copy().reset_index(drop=True)
        logger.info(f"  Using last {len(df)} rows for faster tuning")

    features = get_model_feature_columns(df)
    X = df[features].fillna(0)
    sample_weight = df["sample_weight"] if "sample_weight" in df.columns else None
    growth_factor = float(growth_factor) if growth_factor is not None else _auto_growth_factor(n_splits)
    logger.info(f"  Growth factor for locked n_estimators: {growth_factor:.3f}")

    target_series = _prepare_targets(df, X, model_arch)
    all_rows = []
    best_config = {
        "model_arch": model_arch,
        "n_splits": n_splits,
        "growth_factor": growth_factor,
        "early_stopping_rounds": early_stopping_rounds,
        "max_estimators": max_estimators,
        "features": features,
        "targets": {},
    }

    for target_key, y in target_series.items():
        best, results = _score_xgb_target(
            X,
            y,
            sample_weight,
            target_key,
            n_splits,
            growth_factor,
            early_stopping_rounds,
            max_estimators,
        )
        best_config["targets"][target_key] = best
        for row in results:
            flat = row.copy()
            flat["params"] = json.dumps(flat["params"])
            flat["fold_mae"] = json.dumps(flat["fold_mae"])
            flat["cv_best_iterations"] = json.dumps(flat["cv_best_iterations"])
            all_rows.append(flat)

    report_dir.mkdir(parents=True, exist_ok=True)
    results_path = report_dir / "xgb_locked_tuning_results.csv"
    pd.DataFrame(all_rows).to_csv(results_path, index=False)
    config_path = report_dir / "best_xgb_config.json"
    config_path.write_text(json.dumps(best_config, indent=2), encoding="utf-8")
    logger.info(f"  Locked XGB tuning results saved to: {results_path}")
    logger.info(f"  Best locked XGB config saved to: {config_path}")
    return best_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Tune XGBoost best_iteration and lock n_estimators for final full-data training.")
    parser.add_argument("--feature-table", type=Path, default=PROJECT_ROOT / "data/output/featured_table.parquet")
    parser.add_argument("--report-dir", type=Path, default=PROJECT_ROOT / "reports")
    parser.add_argument("--model_arch", choices=["arima_hybrid", "seasonal_xgb_ratio"], default="seasonal_xgb_ratio")
    parser.add_argument("--splits", type=int, default=3)
    parser.add_argument("--growth-factor", type=float, default=None, help="Override auto growth factor. Auto=min(1.25, 1+1/splits).")
    parser.add_argument("--max-rows", "--sample-rows", dest="max_rows", type=int, default=None)
    parser.add_argument("--early-stopping-rounds", type=int, default=50)
    parser.add_argument("--max-estimators", type=int, default=2500)
    args = parser.parse_args()

    tune_locked_estimators(
        feature_table_path=args.feature_table,
        report_dir=args.report_dir,
        model_arch=args.model_arch,
        n_splits=args.splits,
        growth_factor=args.growth_factor,
        max_rows=args.max_rows,
        early_stopping_rounds=args.early_stopping_rounds,
        max_estimators=args.max_estimators,
    )


if __name__ == "__main__":
    main()
