from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import ElasticNet
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from statsmodels.tsa.arima.model import ARIMA

from src.logger import logger


DEFAULT_ARIMA_ORDER = (7, 1, 1)
DEFAULT_RESIDUAL_WEIGHTS = {
    "xgboost": 0.85,
    "elasticnet": 0.15,
}


def log_stage(message: str) -> None:
    logger.info(f"  🔔 {message}")


def log_progress(prefix: str, current: int, total: int, extra: str = "") -> None:
    total = max(total, 1)
    pct = (current / total) * 100
    suffix = f" | {extra}" if extra else ""
    logger.info(f"     ⏱ {prefix}: {current}/{total} ({pct:.1f}%){suffix}")


def train_elasticnet_model(
    X: pd.DataFrame,
    y: pd.Series,
    alpha: float = 0.1,
    l1_ratio: float = 0.2,
) -> Pipeline:
    model = Pipeline([
        ("scaler", StandardScaler()),
        (
            "elasticnet",
            ElasticNet(
                alpha=alpha,
                l1_ratio=l1_ratio,
                max_iter=20000,
                random_state=42,
            ),
        ),
    ])
    model.fit(X, y)
    return model


def fit_arima_model(
    y: pd.Series,
    order: tuple[int, int, int] = DEFAULT_ARIMA_ORDER,
) -> object:
    series = pd.Series(y).astype(float)
    model = ARIMA(series, order=order)
    return model.fit()


def get_arima_in_sample_baseline(model: object, y: pd.Series) -> pd.Series:
    fitted = pd.Series(np.asarray(model.fittedvalues, dtype=float), index=y.index)
    fitted = fitted.replace([np.inf, -np.inf], np.nan)
    fitted = fitted.bfill().ffill().fillna(float(y.mean()))
    return fitted


def forecast_arima_baseline(model: object, steps: int) -> np.ndarray:
    if steps <= 0:
        return np.array([], dtype=float)
    forecast = np.asarray(model.forecast(steps=steps), dtype=float)
    forecast = np.nan_to_num(forecast, nan=0.0, posinf=0.0, neginf=0.0)
    return forecast


def blend_residual_predictions(
    predictions: dict[str, np.ndarray],
    weights: dict[str, float] | None = None,
) -> np.ndarray:
    if not predictions:
        raise ValueError("No residual predictions provided for blending.")
    weights = weights or DEFAULT_RESIDUAL_WEIGHTS
    first = next(iter(predictions.values()))
    total = np.zeros(len(first), dtype=float)
    total_weight = 0.0
    for name, values in predictions.items():
        w = float(weights.get(name, 0.0))
        if w <= 0:
            continue
        total += np.asarray(values, dtype=float) * w
        total_weight += w
    if total_weight == 0:
        raise ValueError("Residual blend weights sum to zero.")
    return total / total_weight


def load_best_hybrid_config(report_dir: Path) -> dict:
    config_path = report_dir / "best_hybrid_config.json"
    if not config_path.exists():
        return {"targets": {}}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"  Could not read best hybrid config at {config_path}: {exc}")
        return {"targets": {}}


def get_target_hybrid_config(config: dict, target_name: str) -> tuple[tuple[int, int, int], dict[str, float]]:
    target_cfg = config.get("targets", {}).get(target_name, {})
    order = tuple(target_cfg.get("arima_order", DEFAULT_ARIMA_ORDER))
    weights = target_cfg.get("residual_weights", DEFAULT_RESIDUAL_WEIGHTS)
    return order, weights


def save_hybrid_metadata(
    model_output_dir: Path,
    features: list[str],
    target_configs: dict | None = None,
) -> Path:
    metadata_path = model_output_dir / "hybrid_metadata.json"
    target_configs = target_configs or {}
    payload = {
        "architecture": "arima_first_residual_hybrid",
        "baseline_model": "arima",
        "residual_learners": ["xgboost", "elasticnet"],
        "default_arima_order": list(DEFAULT_ARIMA_ORDER),
        "default_residual_weights": DEFAULT_RESIDUAL_WEIGHTS,
        "target_configs": target_configs,
        "features": features,
        "targets": ["Revenue", "COGS"],
    }
    metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return metadata_path


def load_hybrid_metadata(model_dir: Path) -> dict:
    metadata_path = model_dir / "hybrid_metadata.json"
    if not metadata_path.exists():
        return {
            "architecture": "arima_first_residual_hybrid",
            "baseline_model": "arima",
            "residual_learners": ["xgboost", "elasticnet"],
            "default_arima_order": list(DEFAULT_ARIMA_ORDER),
            "default_residual_weights": DEFAULT_RESIDUAL_WEIGHTS,
            "target_configs": {},
            "features": [],
            "targets": ["Revenue", "COGS"],
        }
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def save_model(path: Path, model: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)
    return path


def load_model(path: Path) -> object | None:
    return joblib.load(path) if path.exists() else None
