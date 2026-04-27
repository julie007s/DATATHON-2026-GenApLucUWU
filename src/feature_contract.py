from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd

TARGET_COLUMNS = ["Date", "Revenue", "COGS"]
NON_MODEL_COLUMNS = TARGET_COLUMNS + ["sample_weight"]
SAFE_FEATURE_PATTERNS = [
    "_lag",
    "_roll",
    "day_",
    "week_",
    "month",
    "year",
    "quarter",
    "days_until_holiday",
    "covid_intensity",
    "market_era",
    "recovery",
    "q2_peak",
    "peak_ramp",
    "post_peak",
    "cost_risk",
    "year_end_pressure",
    "december_pressure",
    "margin_risk",
    "pre_pandemic",
    "cogs_to_revenue_ratio",
]

FEATURE_PROFILE_ENV = "DATATHON_FEATURE_PROFILE"
DEFAULT_FEATURE_PROFILE = "full"
SUPPORTED_FEATURE_PROFILES = ("full", "core_seasonal_slim", "core_plus_business", "no_revenue_like")

KEEP_ALWAYS = {
    "day_of_week",
    "day_of_year",
    "week_of_year",
    "month",
    "days_until_holiday",
    "covid_intensity",
    "is_q2_peak",
    "is_pre_peak_ramp",
    "is_post_peak_decay",
    "is_august_cost_risk",
    "is_late_summer_cost_risk",
    "is_year_end_pressure",
    "is_december_pressure",
    "is_q4",
    "month_in_quarter",
    "margin_risk_month_score",
    "pre_pandemic_month_revenue_share",
    "recovery_trend_index",
    "is_recovery_regime",
    "recovery_x_q2_peak",
    "recovery_x_year_end_pressure",
    "recovery_x_august_cost_risk",
}
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


def _feature_profile_path() -> Path:
    return Path(__file__).resolve().parents[1] / "reports" / "active_feature_profile.txt"


def get_active_feature_profile(feature_profile: str | None = None) -> str:
    """Resolve feature profile from explicit arg, env var, or report marker file."""
    profile = feature_profile or os.getenv(FEATURE_PROFILE_ENV)
    profile_path = _feature_profile_path()
    if not profile and profile_path.exists():
        profile = profile_path.read_text(encoding="utf-8").strip()
    profile = profile or DEFAULT_FEATURE_PROFILE
    if profile not in SUPPORTED_FEATURE_PROFILES:
        raise ValueError(
            f"Unsupported feature profile '{profile}'. Choose one of: {', '.join(SUPPORTED_FEATURE_PROFILES)}"
        )
    return profile


def persist_active_feature_profile(feature_profile: str) -> Path:
    """Persist the profile used by scripts that cannot receive an explicit CLI option."""
    profile = get_active_feature_profile(feature_profile)
    path = _feature_profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(profile, encoding="utf-8")
    return path


def _has_suffix(feature: str, suffixes: tuple[str, ...]) -> bool:
    return any(feature.endswith(f"_{suffix}") for suffix in suffixes)


def _starts_with_any(feature: str, bases: tuple[str, ...]) -> bool:
    return any(feature == base or feature.startswith(f"{base}_") for base in bases)


def _allowed_common(feature: str) -> bool:
    return feature not in DROP_EXACT and not any(pattern in feature for pattern in DROP_PATTERNS)


def _apply_feature_profile(features: list[str], profile: str) -> list[str]:
    if profile == "full":
        return features

    selected: list[str] = []
    for feature in features:
        if not _allowed_common(feature):
            continue
        is_calendar = feature in KEEP_ALWAYS or feature.startswith("day_") or feature.startswith("week_") or feature == "month"
        is_core = _starts_with_any(feature, CORE_BASES) and _has_suffix(feature, PREFERRED_SUFFIXES)
        is_business = _starts_with_any(feature, BUSINESS_BASES) and _has_suffix(feature, BUSINESS_SUFFIXES)
        is_non_revenue_core = (
            _starts_with_any(feature, CORE_BASES)
            and not _starts_with_any(feature, ("daily_total_item_revenue", "daily_gross_revenue_before_discount", "daily_total_cogs"))
            and _has_suffix(feature, PREFERRED_SUFFIXES)
        )

        if profile == "core_seasonal_slim" and (is_calendar or is_core):
            selected.append(feature)
        elif profile == "core_plus_business" and (is_calendar or is_core or is_business):
            selected.append(feature)
        elif profile == "no_revenue_like" and (is_calendar or is_business or is_non_revenue_core):
            selected.append(feature)

    return selected


def get_model_feature_columns(df: pd.DataFrame, feature_profile: str | None = None) -> list[str]:
    """Return numeric, leakage-safe feature columns for training/inference."""
    profile = get_active_feature_profile(feature_profile)
    candidate_features = [c for c in df.columns if c not in TARGET_COLUMNS]
    numeric_features = [c for c in candidate_features if pd.api.types.is_numeric_dtype(df[c])]
    safe_features = [
        c for c in numeric_features
        if any(pattern in c for pattern in SAFE_FEATURE_PATTERNS)
    ]
    return _apply_feature_profile(safe_features, profile)


def get_recursive_base_columns(df: pd.DataFrame) -> list[str]:
    """Return base columns that have lag/rolling derivatives in the feature table."""
    cols = df.columns.tolist()
    return [
        c for c in cols
        if any(f"{c}_{suffix}" in cols for suffix in ["lag7", "lag30", "lag365", "roll7", "roll30"])
    ]
