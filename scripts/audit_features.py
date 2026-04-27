from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEATURE_TABLE = PROJECT_ROOT / "data" / "output" / "featured_table.parquet"
DEFAULT_IMPORTANCE = PROJECT_ROOT / "reports" / "explainability" / "seasonal_xgb_ratio" / "all_feature_importances.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "reports" / "feature_audit"

TARGET_COLUMNS = {"Date", "Revenue", "COGS", "sample_weight"}
KEEP_ALWAYS = {"day_of_week", "day_of_year", "week_of_year", "month", "days_until_holiday", "covid_intensity"}
DROP_EXACT = {"year"}
DROP_PATTERNS = ("market_era", "promo_id_2")
CORE_BASES = (
    "daily_total_item_revenue",
    "daily_gross_revenue_before_discount",
    "daily_total_cogs",
    "daily_order_count",
    "daily_order_line_count",
    "daily_total_quantity",
    "aov",
    "upt",
    "promo_penetration_rate",
    "daily_discount_depth",
    "daily_discount_amount",
    "daily_promo_order_count",
)
BUSINESS_BASES = (
    "wt_sessions",
    "wt_unique_visitors",
    "wt_page_views",
    "wt_bounce_rate",
    "high_intent_traffic_share",
    "daily_stockout_rate",
    "daily_avg_fill_rate",
    "daily_return_risk_index",
    "size_mix_return_pressure",
    "category_reason_weighted_return_risk",
    "category_encoded",
    "city_encoded",
    "customer_repurchase_cadence_index",
    "payment_method_cancellation_risk",
    "active_customer_demographic_mix_score",
    "financing_intensity_index",
    "legacy_order_ratio",
    "legacy_revenue_share",
    "legacy_aov",
    "new_customer_aov",
    "daily_mobile_order_ratio",
    "daily_cod_order_ratio",
    "regional_revenue_concentration_index",
)
PREFERRED_SUFFIXES = ("lag365", "lag30", "roll7")
BUSINESS_SUFFIXES = ("lag365", "roll30", "roll7")


def _feature_columns(df: pd.DataFrame) -> list[str]:
    return [
        c
        for c in df.columns
        if c not in TARGET_COLUMNS and pd.api.types.is_numeric_dtype(df[c])
    ]


def _base_name(feature: str) -> str:
    return re.sub(r"_(lag7|lag30|lag365|roll7|roll30)$", "", feature)


def _suffix(feature: str) -> str:
    match = re.search(r"_(lag7|lag30|lag365|roll7|roll30)$", feature)
    return match.group(1) if match else "calendar_or_static"


def _has_suffix(feature: str, suffixes: tuple[str, ...]) -> bool:
    return any(feature.endswith(f"_{suffix}") for suffix in suffixes)


def _starts_with_any(feature: str, bases: tuple[str, ...]) -> bool:
    return any(feature == base or feature.startswith(f"{base}_") for base in bases)


def build_profiles(features: list[str], importance: pd.DataFrame | None = None) -> dict[str, list[str]]:
    positive_importance = set()
    if importance is not None and not importance.empty:
        imp = importance.groupby("Feature", as_index=False)["CompositeImportance"].max()
        positive_importance = set(imp.loc[imp["CompositeImportance"] > 0, "Feature"])

    def allowed_common(f: str) -> bool:
        if f in DROP_EXACT or any(pattern in f for pattern in DROP_PATTERNS):
            return False
        return not positive_importance or f in positive_importance or f in KEEP_ALWAYS

    core = []
    business = []
    no_revenue_like = []
    for f in features:
        if not allowed_common(f):
            continue
        is_calendar = f in KEEP_ALWAYS or f.startswith("day_") or f.startswith("week_") or f == "month"
        is_core = _starts_with_any(f, CORE_BASES) and _has_suffix(f, PREFERRED_SUFFIXES)
        is_business = _starts_with_any(f, BUSINESS_BASES) and _has_suffix(f, BUSINESS_SUFFIXES)

        if is_calendar or is_core:
            core.append(f)
        if is_calendar or is_core or is_business:
            business.append(f)
        if is_calendar or is_business or (
            _starts_with_any(f, CORE_BASES)
            and not _starts_with_any(f, ("daily_total_item_revenue", "daily_gross_revenue_before_discount", "daily_total_cogs"))
            and _has_suffix(f, PREFERRED_SUFFIXES)
        ):
            no_revenue_like.append(f)

    return {
        "core_seasonal_slim": sorted(set(core)),
        "core_plus_business": sorted(set(business)),
        "no_revenue_like": sorted(set(no_revenue_like)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit feature volume, correlation, and pruning candidates.")
    parser.add_argument("--feature-table", type=Path, default=DEFAULT_FEATURE_TABLE)
    parser.add_argument("--importance", type=Path, default=DEFAULT_IMPORTANCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--corr-threshold", type=float, default=0.95)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(args.feature_table)
    df["Date"] = pd.to_datetime(df["Date"])
    features = _feature_columns(df)

    importance = pd.DataFrame()
    if args.importance.exists():
        importance = pd.read_csv(args.importance)

    missing = df[features].isna().mean().rename("missing_rate").reset_index().rename(columns={"index": "Feature"})
    nunique = df[features].nunique(dropna=False).rename("nunique").reset_index().rename(columns={"index": "Feature"})
    corr_to_revenue = (
        df[features + ["Revenue"]]
        .corr(numeric_only=True)["Revenue"]
        .drop("Revenue")
        .rename("abs_corr_to_revenue")
        .abs()
        .reset_index()
        .rename(columns={"index": "Feature"})
    )

    audit = missing.merge(nunique, on="Feature").merge(corr_to_revenue, on="Feature", how="left")
    audit["base_feature"] = audit["Feature"].map(_base_name)
    audit["suffix"] = audit["Feature"].map(_suffix)
    if not importance.empty:
        imp = importance.groupby("Feature", as_index=False)["CompositeImportance"].max()
        audit = audit.merge(imp, on="Feature", how="left")
    else:
        audit["CompositeImportance"] = np.nan
    audit["CompositeImportance"] = audit["CompositeImportance"].fillna(0.0)

    numeric = df[features].fillna(0)
    corr = numeric.corr(numeric_only=True).abs()
    rows = []
    upper = np.triu(np.ones(corr.shape), k=1).astype(bool)
    corr_pairs = corr.where(upper).stack().sort_values(ascending=False)
    for (a, b), value in corr_pairs[corr_pairs >= args.corr_threshold].items():
        rows.append({"feature_a": a, "feature_b": b, "abs_corr": float(value), "base_a": _base_name(a), "base_b": _base_name(b)})
    corr_df = pd.DataFrame(rows)

    profiles = build_profiles(features, importance)
    profile_rows = []
    for profile, cols in profiles.items():
        profile_rows.append({"profile": profile, "feature_count": len(cols)})
        pd.Series(cols, name="Feature").to_csv(args.output_dir / f"features_keep_{profile}.csv", index=False)

    low_importance = audit[(audit["CompositeImportance"] <= 0) | (audit["nunique"] <= 1)].sort_values(
        ["CompositeImportance", "abs_corr_to_revenue"], ascending=[True, True]
    )

    audit.sort_values(["CompositeImportance", "abs_corr_to_revenue"], ascending=[False, False]).to_csv(
        args.output_dir / "feature_audit_summary.csv", index=False
    )
    corr_df.to_csv(args.output_dir / "high_correlation_pairs.csv", index=False)
    low_importance.to_csv(args.output_dir / "features_drop_low_importance.csv", index=False)
    pd.DataFrame(profile_rows).to_csv(args.output_dir / "feature_profiles_summary.csv", index=False)

    recommendation = {
        "feature_table": str(args.feature_table),
        "rows": int(len(df)),
        "date_min": str(df["Date"].min().date()),
        "date_max": str(df["Date"].max().date()),
        "numeric_feature_count": len(features),
        "high_corr_pair_count": int(len(corr_df)),
        "low_importance_or_constant_count": int(len(low_importance)),
        "profiles": {k: len(v) for k, v in profiles.items()},
    }
    (args.output_dir / "feature_audit_recommendation.json").write_text(
        json.dumps(recommendation, indent=2), encoding="utf-8"
    )
    md = [
        "# Feature Audit Recommendation",
        "",
        f"- Rows: `{recommendation['rows']}`",
        f"- Date range: `{recommendation['date_min']}` → `{recommendation['date_max']}`",
        f"- Numeric feature count: `{len(features)}`",
        f"- High-correlation pairs >= {args.corr_threshold}: `{len(corr_df)}`",
        f"- Low-importance/constant candidates: `{len(low_importance)}`",
        "",
        "## Candidate feature profiles",
    ]
    for profile, cols in profiles.items():
        md.append(f"- `{profile}`: `{len(cols)}` features")
    md.extend([
        "",
        "## Recommended next experiment",
        "",
        "Run `core_seasonal_slim` first to reduce lag/rolling duplication while keeping the strongest seasonal signals.",
        "Then compare against `core_plus_business` to see whether sparse business drivers improve public MAE.",
    ])
    (args.output_dir / "feature_pruning_recommendation.md").write_text("\n".join(md), encoding="utf-8")

    print(json.dumps(recommendation, indent=2))


if __name__ == "__main__":
    main()
