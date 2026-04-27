from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.feature_contract import get_model_feature_columns, persist_active_feature_profile
from src.predictor import _prepare_recursive_frame, _run_recursive_residual_model
from src.seasonal_baseline import DEFAULT_SEASONAL_WEIGHTS, build_in_sample_seasonal_baseline, forecast_seasonal_baseline
from src.seasonal_xgb_trainer import _get_locked_xgb_target_config, _load_locked_xgb_config, _make_xgb_model


ROOT = Path(__file__).resolve().parents[1]


def _parse_scales(raw: str) -> list[float]:
    if ":" in raw:
        start, stop, step = [float(part) for part in raw.split(":")]
        values = []
        current = start
        while current <= stop + 1e-9:
            values.append(round(current, 6))
            current += step
        return values
    return [float(part.strip()) for part in raw.split(",") if part.strip()]


def _weighted_mae(revenue_mae: float, cogs_mae: float, profit_mae: float) -> float:
    return float((revenue_mae + cogs_mae + profit_mae) / 3.0)


def run_backtest(
    feature_table_path: Path,
    report_output_dir: Path,
    holdout_start: str,
    holdout_end: str,
    feature_profile: str,
    scales: list[float],
    output_path: Path,
) -> pd.DataFrame:
    persist_active_feature_profile(feature_profile)

    df = pd.read_parquet(feature_table_path, engine="pyarrow")
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)

    start = pd.Timestamp(holdout_start)
    end = pd.Timestamp(holdout_end)
    train_df = df[df["Date"] < start].copy()
    holdout_df = df[(df["Date"] >= start) & (df["Date"] <= end)].copy()
    if train_df.empty or holdout_df.empty:
        raise ValueError("Train or holdout split is empty. Check holdout dates.")

    features = get_model_feature_columns(df, feature_profile)
    if not features:
        raise ValueError(f"No features selected for profile={feature_profile}")

    locked_config = _load_locked_xgb_config(report_output_dir, "seasonal_xgb_ratio")
    X_train = train_df[features].fillna(0)
    sample_weight = train_df["sample_weight"] if "sample_weight" in train_df.columns else None

    revenue_baseline_train = build_in_sample_seasonal_baseline(train_df, "Revenue")
    revenue_residual_train = train_df["Revenue"].astype(float) - revenue_baseline_train.astype(float)

    safe_revenue = train_df["Revenue"].replace(0, np.nan).astype(float)
    cogs_ratio_train = (train_df["COGS"].astype(float) / safe_revenue).replace([np.inf, -np.inf], np.nan)
    cogs_ratio_train = cogs_ratio_train.fillna(cogs_ratio_train.median()).clip(lower=0.0, upper=2.0)
    ratio_q01 = float(cogs_ratio_train.quantile(0.01))
    ratio_q99 = float(cogs_ratio_train.quantile(0.99))

    revenue_model = _make_xgb_model(locked_xgb_config=_get_locked_xgb_target_config(locked_config, "Revenue_Residual"))
    revenue_model.fit(X_train, revenue_residual_train, sample_weight=sample_weight)

    cogs_ratio_model = _make_xgb_model(locked_xgb_config=_get_locked_xgb_target_config(locked_config, "COGS_Ratio"))
    cogs_ratio_model.fit(X_train, cogs_ratio_train, sample_weight=sample_weight)

    sample_df = holdout_df[["Date"]].copy()
    recursive_df, train_max, source_vars = _prepare_recursive_frame(
        train_df.copy(),
        sample_df,
        features,
    )
    future_dates = [d for d in recursive_df.index if d > train_max]

    history_df = train_df.copy()
    seasonal_baseline = forecast_seasonal_baseline(
        history_df,
        future_dates,
        "Revenue",
        weights=DEFAULT_SEASONAL_WEIGHTS,
    )
    _, revenue_residual = _run_recursive_residual_model(
        revenue_model,
        recursive_df,
        features,
        "Revenue",
        train_max,
        source_vars,
        "Backtest Seasonal-XGB Revenue",
        verbose=False,
    )
    _, cogs_ratio_raw = _run_recursive_residual_model(
        cogs_ratio_model,
        recursive_df,
        features,
        "COGS",
        train_max,
        source_vars,
        "Backtest XGB COGS Ratio",
        verbose=False,
    )

    holdout_actual = holdout_df.set_index("Date").loc[future_dates]
    cogs_ratio = np.clip(cogs_ratio_raw, ratio_q01, ratio_q99)
    rows = []
    for scale in scales:
        revenue_pred = np.maximum(seasonal_baseline + revenue_residual * scale, 0)
        cogs_pred = np.maximum(revenue_pred * cogs_ratio, 0)
        profit_pred = revenue_pred - cogs_pred
        profit_actual = holdout_actual["Revenue"].to_numpy() - holdout_actual["COGS"].to_numpy()

        revenue_mae = mean_absolute_error(holdout_actual["Revenue"], revenue_pred)
        cogs_mae = mean_absolute_error(holdout_actual["COGS"], cogs_pred)
        profit_mae = mean_absolute_error(profit_actual, profit_pred)
        rows.append(
            {
                "feature_profile": feature_profile,
                "holdout_start": str(start.date()),
                "holdout_end": str(end.date()),
                "train_days": len(train_df),
                "holdout_days": len(holdout_actual),
                "residual_scale": scale,
                "revenue_mae": revenue_mae,
                "cogs_mae": cogs_mae,
                "profit_mae": profit_mae,
                "overall_mae": _weighted_mae(revenue_mae, cogs_mae, profit_mae),
                "pred_revenue_mean": float(np.mean(revenue_pred)),
                "pred_cogs_mean": float(np.mean(cogs_pred)),
                "actual_revenue_mean": float(holdout_actual["Revenue"].mean()),
                "actual_cogs_mean": float(holdout_actual["COGS"].mean()),
                "residual_pred_mean": float(np.mean(revenue_residual * scale)),
            }
        )

    result = pd.DataFrame(rows).sort_values("overall_mae")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)

    detail_path = output_path.with_name(output_path.stem + "_metadata.json")
    detail_path.write_text(
        json.dumps(
            {
                "feature_table": str(feature_table_path),
                "feature_profile": feature_profile,
                "feature_count": len(features),
                "locked_xgb_config_used": bool(locked_config),
                "cogs_ratio_clip": {"q01": ratio_q01, "q99": ratio_q99},
                "train_start": str(train_df["Date"].min().date()),
                "train_end": str(train_df["Date"].max().date()),
                "holdout_start": str(start.date()),
                "holdout_end": str(end.date()),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest seasonal XGB residual scaling on a holdout period.")
    parser.add_argument("--feature-table", type=Path, default=ROOT / "data/output/featured_table.parquet")
    parser.add_argument("--reports-dir", type=Path, default=ROOT / "reports")
    parser.add_argument("--holdout-start", default="2022-01-01")
    parser.add_argument("--holdout-end", default="2022-12-31")
    parser.add_argument("--feature-profile", default="full")
    parser.add_argument("--scales", default="0.80:1.80:0.05", help="Comma list or start:stop:step, e.g. 1.0,1.1 or 0.8:1.8:0.05")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/backtest_residual_scale_2022.csv")
    args = parser.parse_args()

    scales = _parse_scales(args.scales)
    result = run_backtest(
        feature_table_path=args.feature_table,
        report_output_dir=args.reports_dir,
        holdout_start=args.holdout_start,
        holdout_end=args.holdout_end,
        feature_profile=args.feature_profile,
        scales=scales,
        output_path=args.output,
    )
    print(f"Saved report -> {args.output}")
    print(result.head(12).to_string(index=False))


if __name__ == "__main__":
    main()
