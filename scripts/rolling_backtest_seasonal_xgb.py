from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

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


DEFAULT_FOLDS = [
    {"fold": "recovery_2021", "holdout_start": "2021-01-01", "holdout_end": "2021-12-31"},
    {"fold": "recovery_2022", "holdout_start": "2022-01-01", "holdout_end": "2022-12-31"},
    {"fold": "recovery_2022_h2", "holdout_start": "2022-07-01", "holdout_end": "2022-12-31"},
]


def _load_candidate_config(path: Path) -> dict[str, dict[str, Any]]:
    try:
        import yaml  # type: ignore

        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to read config/model_candidates.yaml") from exc

    candidates = data.get("candidates", {}) if isinstance(data, dict) else {}
    if not candidates:
        raise ValueError(f"No candidates found in {path}")
    return candidates


def _official_mae(revenue_actual: pd.Series, revenue_pred: np.ndarray, cogs_actual: pd.Series, cogs_pred: np.ndarray) -> tuple[float, float, float]:
    revenue_mae = float(mean_absolute_error(revenue_actual, revenue_pred))
    cogs_mae = float(mean_absolute_error(cogs_actual, cogs_pred))
    official_mae = float((revenue_mae + cogs_mae) / 2.0)
    return revenue_mae, cogs_mae, official_mae


def _fit_and_predict_fold(
    df: pd.DataFrame,
    report_output_dir: Path,
    feature_profile: str,
    holdout_start: str,
    holdout_end: str,
) -> dict[str, Any]:
    persist_active_feature_profile(feature_profile)
    start = pd.Timestamp(holdout_start)
    end = pd.Timestamp(holdout_end)
    train_df = df[df["Date"] < start].copy()
    holdout_df = df[(df["Date"] >= start) & (df["Date"] <= end)].copy()
    if train_df.empty or holdout_df.empty:
        raise ValueError(f"Empty train/holdout split for {holdout_start} to {holdout_end}")

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
    recursive_df, train_max, source_vars = _prepare_recursive_frame(train_df.copy(), sample_df, features)
    future_dates = [d for d in recursive_df.index if d > train_max and start <= d <= end]

    seasonal_baseline = forecast_seasonal_baseline(
        train_df.copy(),
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
        "Rolling Backtest Seasonal-XGB Revenue",
        verbose=False,
    )
    _, cogs_ratio_raw = _run_recursive_residual_model(
        cogs_ratio_model,
        recursive_df,
        features,
        "COGS",
        train_max,
        source_vars,
        "Rolling Backtest XGB COGS Ratio",
        verbose=False,
    )

    holdout_actual = holdout_df.set_index("Date").loc[future_dates]
    return {
        "feature_count": len(features),
        "train_start": train_df["Date"].min(),
        "train_end": train_df["Date"].max(),
        "holdout_actual": holdout_actual,
        "future_dates": future_dates,
        "seasonal_baseline": np.asarray(seasonal_baseline, dtype=float),
        "revenue_residual": np.asarray(revenue_residual, dtype=float),
        "cogs_ratio": np.clip(np.asarray(cogs_ratio_raw, dtype=float), ratio_q01, ratio_q99),
        "cogs_ratio_clip_q01": ratio_q01,
        "cogs_ratio_clip_q99": ratio_q99,
    }


def _score_candidate_on_fold(fold_payload: dict[str, Any], candidate_name: str, candidate: dict[str, Any], fold_name: str) -> tuple[dict[str, Any], pd.DataFrame]:
    scale = float(candidate.get("residual_scale", 1.0))
    cogs_mix = float(candidate.get("cogs_mix_factor", 1.0))
    actual = fold_payload["holdout_actual"]
    revenue_pred = np.maximum(fold_payload["seasonal_baseline"] + fold_payload["revenue_residual"] * scale, 0)
    cogs_ratio = fold_payload["cogs_ratio"] * cogs_mix
    cogs_pred = np.maximum(revenue_pred * cogs_ratio, 0)
    revenue_mae, cogs_mae, official_mae = _official_mae(actual["Revenue"], revenue_pred, actual["COGS"], cogs_pred)

    detail = pd.DataFrame(
        {
            "fold": fold_name,
            "candidate": candidate_name,
            "Date": actual.index,
            "actual_revenue": actual["Revenue"].to_numpy(),
            "pred_revenue": revenue_pred,
            "actual_cogs": actual["COGS"].to_numpy(),
            "pred_cogs": cogs_pred,
            "revenue_abs_error": np.abs(actual["Revenue"].to_numpy() - revenue_pred),
            "cogs_abs_error": np.abs(actual["COGS"].to_numpy() - cogs_pred),
        }
    )
    row = {
        "fold": fold_name,
        "candidate": candidate_name,
        "feature_profile": candidate.get("feature_profile", "full"),
        "residual_scale": scale,
        "cogs_mix_factor": cogs_mix,
        "feature_count": fold_payload["feature_count"],
        "train_start": str(fold_payload["train_start"].date()),
        "train_end": str(fold_payload["train_end"].date()),
        "holdout_days": len(actual),
        "revenue_mae": revenue_mae,
        "cogs_mae": cogs_mae,
        "official_mae": official_mae,
        "pred_revenue_mean": float(np.mean(revenue_pred)),
        "actual_revenue_mean": float(actual["Revenue"].mean()),
        "pred_cogs_mean": float(np.mean(cogs_pred)),
        "actual_cogs_mean": float(actual["COGS"].mean()),
        "description": candidate.get("description", ""),
    }
    return row, detail


def run_rolling_backtest(feature_table: Path, reports_dir: Path, config_path: Path, output_dir: Path) -> pd.DataFrame:
    df = pd.read_parquet(feature_table, engine="pyarrow")
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    candidates = _load_candidate_config(config_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    fold_cache: dict[tuple[str, str], dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    details: list[pd.DataFrame] = []

    for fold in DEFAULT_FOLDS:
        fold_name = fold["fold"]
        for candidate_name, candidate in candidates.items():
            profile = str(candidate.get("feature_profile", "full"))
            cache_key = (fold_name, profile)
            if cache_key not in fold_cache:
                print(f"Training fold={fold_name}, profile={profile}")
                fold_cache[cache_key] = _fit_and_predict_fold(
                    df,
                    reports_dir,
                    profile,
                    fold["holdout_start"],
                    fold["holdout_end"],
                )
            row, detail = _score_candidate_on_fold(fold_cache[cache_key], candidate_name, candidate, fold_name)
            rows.append(row)
            details.append(detail)

    fold_summary = pd.DataFrame(rows)
    predictions = pd.concat(details, ignore_index=True)
    candidate_summary = (
        fold_summary.groupby("candidate", as_index=False)
        .agg(
            feature_profile=("feature_profile", "first"),
            residual_scale=("residual_scale", "first"),
            cogs_mix_factor=("cogs_mix_factor", "first"),
            folds=("fold", "nunique"),
            mean_official_mae=("official_mae", "mean"),
            std_official_mae=("official_mae", "std"),
            max_official_mae=("official_mae", "max"),
            mean_revenue_mae=("revenue_mae", "mean"),
            mean_cogs_mae=("cogs_mae", "mean"),
            description=("description", "first"),
        )
        .sort_values(["mean_official_mae", "std_official_mae"], ascending=[True, True])
    )
    predictions["month"] = pd.to_datetime(predictions["Date"]).dt.to_period("M").astype(str)
    monthly = (
        predictions.groupby(["candidate", "fold", "month"], as_index=False)
        .agg(
            revenue_mae=("revenue_abs_error", "mean"),
            cogs_mae=("cogs_abs_error", "mean"),
        )
    )
    monthly["official_mae"] = (monthly["revenue_mae"] + monthly["cogs_mae"]) / 2.0

    fold_summary.to_csv(output_dir / "fold_summary.csv", index=False)
    candidate_summary.to_csv(output_dir / "summary.csv", index=False)
    predictions.to_csv(output_dir / "fold_predictions.csv", index=False)
    monthly.to_csv(output_dir / "metric_by_month.csv", index=False)

    best = candidate_summary.iloc[0].to_dict()
    model_selection = output_dir.parent / "model_selection.md"
    model_selection.write_text(
        "# Model Selection Report\n\n"
        "## Official metric\n\n"
        "The validation selector uses the leaderboard metric confirmed by the user: average MAE across `Revenue` and `COGS`. `Profit` is not part of the selection metric.\n\n"
        "## Backtest folds\n\n"
        "Recovery-era folds only: 2021, 2022, and 2022-H2. COVID-heavy 2020 is excluded because it is an anomalous regime relative to the 2023 forecast target.\n\n"
        "## Selected candidate\n\n"
        f"`{best['candidate']}`\n\n"
        f"- Mean official MAE: `{best['mean_official_mae']:.3f}`\n"
        f"- Std official MAE: `{best['std_official_mae']:.3f}`\n"
        f"- Max fold official MAE: `{best['max_official_mae']:.3f}`\n"
        f"- Residual scale: `{best['residual_scale']}`\n"
        f"- COGS mix factor: `{best['cogs_mix_factor']}`\n\n"
        "## Candidate ranking\n\n"
        + candidate_summary[["candidate", "mean_official_mae", "std_official_mae", "max_official_mae", "mean_revenue_mae", "mean_cogs_mae"]].to_markdown(index=False)
        + "\n\n## Notes\n\n"
        "Public leaderboard should be used only as a final sanity check after this validation step, not as the primary model selector.\n",
        encoding="utf-8",
    )
    (output_dir / "metadata.json").write_text(
        json.dumps({"feature_table": str(feature_table), "config": str(config_path), "folds": DEFAULT_FOLDS}, indent=2),
        encoding="utf-8",
    )
    return candidate_summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run recovery-era rolling-origin backtests for seasonal-XGB candidates.")
    parser.add_argument("--feature-table", type=Path, default=ROOT / "data/output/featured_table.parquet")
    parser.add_argument("--reports-dir", type=Path, default=ROOT / "reports")
    parser.add_argument("--config", type=Path, default=ROOT / "config/model_candidates.yaml")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports/rolling_backtest")
    args = parser.parse_args()

    summary = run_rolling_backtest(args.feature_table, args.reports_dir, args.config, args.output_dir)
    print(f"Saved rolling backtest reports -> {args.output_dir}")
    print(summary.head(20).to_string(index=False))


if __name__ == "__main__":
    main()
