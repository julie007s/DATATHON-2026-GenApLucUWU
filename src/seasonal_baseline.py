from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_SEASONAL_WEIGHTS = {
    "lag365": 0.70,
    "roll28": 0.20,
    "roll7": 0.10,
}


def _safe_float(value: object, fallback: float) -> float:
    try:
        value = float(value)
    except Exception:
        return float(fallback)
    if not np.isfinite(value):
        return float(fallback)
    return value


def _weighted_average(parts: dict[str, float | None], weights: dict[str, float], fallback: float) -> float:
    total = 0.0
    total_weight = 0.0
    for name, value in parts.items():
        if value is None or not np.isfinite(value):
            continue
        weight = float(weights.get(name, 0.0))
        if weight <= 0:
            continue
        total += float(value) * weight
        total_weight += weight
    if total_weight <= 0:
        return float(fallback)
    return float(total / total_weight)


def build_in_sample_seasonal_baseline(
    df: pd.DataFrame,
    target_col: str,
    date_col: str = "Date",
    weights: dict[str, float] | None = None,
) -> pd.Series:
    """Build leakage-safe seasonal baseline for historical rows.

    Each row only uses values before the current date:
    - same calendar day one year ago when available,
    - rolling 28-day mean shifted by one day,
    - rolling 7-day mean shifted by one day.
    """
    weights = weights or DEFAULT_SEASONAL_WEIGHTS
    work = df[[date_col, target_col]].copy()
    work[date_col] = pd.to_datetime(work[date_col])
    work = work.sort_values(date_col).set_index(date_col)
    series = work[target_col].astype(float)

    lag365 = series.shift(365)
    roll28 = series.shift(1).rolling(28, min_periods=7).mean()
    roll7 = series.shift(1).rolling(7, min_periods=3).mean()
    expanding = series.shift(1).expanding(min_periods=1).median()
    global_fallback = _safe_float(series.median(), 0.0)

    values = []
    for idx in series.index:
        fallback = _safe_float(expanding.loc[idx], global_fallback)
        baseline = _weighted_average(
            {
                "lag365": lag365.loc[idx],
                "roll28": roll28.loc[idx],
                "roll7": roll7.loc[idx],
            },
            weights,
            fallback,
        )
        values.append(max(baseline, 0.0))

    return pd.Series(values, index=df.sort_values(date_col).index, name=f"{target_col}_seasonal_baseline").reindex(df.index)


def forecast_seasonal_baseline(
    history_df: pd.DataFrame,
    future_dates: list[pd.Timestamp] | pd.Series | pd.DatetimeIndex,
    target_col: str,
    date_col: str = "Date",
    weights: dict[str, float] | None = None,
) -> np.ndarray:
    """Forecast future seasonal baseline recursively from historical target values."""
    weights = weights or DEFAULT_SEASONAL_WEIGHTS
    future_dates = pd.to_datetime(pd.Series(list(future_dates))).sort_values().tolist()
    work = history_df[[date_col, target_col]].copy()
    work[date_col] = pd.to_datetime(work[date_col])
    work = work.sort_values(date_col).set_index(date_col)
    values = work[target_col].astype(float).to_dict()

    if values:
        fallback = _safe_float(pd.Series(values).median(), 0.0)
    else:
        fallback = 0.0

    baselines = []
    for dt in future_dates:
        dt = pd.Timestamp(dt)
        known = pd.Series(values).sort_index()
        prior = known[known.index < dt]
        lag_date = dt - pd.Timedelta(days=365)
        lag365 = values.get(lag_date)
        roll28 = prior.tail(28).mean() if len(prior) >= 7 else None
        roll7 = prior.tail(7).mean() if len(prior) >= 3 else None
        rolling_fallback = _safe_float(prior.tail(90).median() if len(prior) else np.nan, fallback)
        baseline = _weighted_average(
            {"lag365": lag365, "roll28": roll28, "roll7": roll7},
            weights,
            rolling_fallback,
        )
        baseline = max(float(baseline), 0.0)
        baselines.append(baseline)
        values[dt] = baseline

    return np.asarray(baselines, dtype=float)
