from __future__ import annotations

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
    "days_until_holiday",
    "covid_intensity",
    "market_era",
]


def get_model_feature_columns(df: pd.DataFrame) -> list[str]:
    """Return numeric, leakage-safe feature columns for training/inference."""
    candidate_features = [c for c in df.columns if c not in TARGET_COLUMNS]
    numeric_features = [c for c in candidate_features if pd.api.types.is_numeric_dtype(df[c])]
    return [
        c for c in numeric_features
        if any(pattern in c for pattern in SAFE_FEATURE_PATTERNS)
    ]


def get_recursive_base_columns(df: pd.DataFrame) -> list[str]:
    """Return base columns that have lag/rolling derivatives in the feature table."""
    cols = df.columns.tolist()
    return [
        c for c in cols
        if any(f"{c}_{suffix}" in cols for suffix in ["lag7", "lag30", "lag365", "roll7", "roll30"])
    ]
