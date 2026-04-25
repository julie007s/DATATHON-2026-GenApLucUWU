import pandas as pd
import numpy as np
import yaml
from pathlib import Path
from colorama import Fore, Style
from src.logger import logger


# ──────────────────────────────────────────────────────────────────────────────
# Helper: Load & validate features.yaml
# ──────────────────────────────────────────────────────────────────────────────

def _load_feature_config(config_path: Path) -> list[dict]:
    """
    Loads configs/features.yaml and returns the list of feature rules.
    Each rule is a dict with keys: action, name, formula (opt), scope (opt).
    Raises FileNotFoundError if the config is missing.
    """
    if not config_path.exists():
        raise FileNotFoundError(
            f"Feature config not found: {config_path}\n"
            f"Expected at: configs/features.yaml"
        )
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    rules = raw.get("features", [])
    if not isinstance(rules, list):
        raise ValueError("features.yaml must contain a 'features:' list at the top level.")
    return rules


# ──────────────────────────────────────────────────────────────────────────────
# Helper: Apply a list of feature rules to a DataFrame
# ──────────────────────────────────────────────────────────────────────────────

def _apply_features(df: pd.DataFrame, rules: list[dict], scope: str) -> pd.DataFrame:
    """
    Applies feature engineering rules from features.yaml to `df`.

    Args:
        df     : The DataFrame to transform (mutated in-place copy).
        rules  : Full list of dicts loaded from features.yaml.
        scope  : "row" or "daily" — only rules matching this scope are applied.

    Returns:
        Transformed DataFrame.
    """
    scoped_rules = [r for r in rules if r.get("scope", "daily") == scope]

    for rule in scoped_rules:
        action = rule.get("action", "").lower()
        name   = rule.get("name")

        # ── ADD ─────────────────────────────────────────────────────────────
        if action == "add":
            formula = rule.get("formula", "")
            if not formula:
                logger.warning(f"  ⚠  Rule '{name}' has no formula — skipped.")
                continue

            try:
                # Build a safe evaluation namespace:
                #   - All current DataFrame columns as plain Series variables
                #   - pd and np for pandas/numpy expressions
                #   - No builtins to prevent code injection
                ns = {col: df[col] for col in df.columns}
                ns["pd"] = pd
                ns["np"] = np
                ns["df"] = df

                result = eval(formula, {"__builtins__": {}}, ns)  # noqa: S307
                df = df.copy()
                df[name] = result
                logger.info(f"     ✚ [{scope}] Added column '{name}' via formula: {formula}")

            except Exception as exc:
                logger.error(
                    f"  ❌ Failed to evaluate formula for '{name}' "
                    f"(scope={scope}): {formula!r}\n     Reason: {exc}"
                )

        # ── REMOVE ──────────────────────────────────────────────────────────
        elif action == "remove":
            cols_to_drop = [name] if isinstance(name, str) else list(name)
            existing     = [c for c in cols_to_drop if c in df.columns]
            missing      = [c for c in cols_to_drop if c not in df.columns]

            if missing:
                logger.warning(
                    f"  ⚠  [{scope}] remove: columns not found (skipped): {missing}"
                )
            if existing:
                df = df.drop(columns=existing)
                logger.info(f"     ✖ [{scope}] Removed columns: {existing}")

        else:
            logger.warning(f"  ⚠  Unknown action '{action}' for rule '{name}' — skipped.")

    return df


# ──────────────────────────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────────
# Add market_era, covid_intensity, sample_weight features
# ──────────────────────────────────────────────────────────────────────────────
def add_market_era_features(df: pd.DataFrame, date_col: str = "order_date") -> pd.DataFrame:
    """
    Add market_era (0/1/2), covid_intensity (0-1), sample_weight columns to DataFrame.
    Args:
        df: DataFrame with a datetime column (default 'order_date')
        date_col: Name of the datetime column
    Returns:
        DataFrame with new columns added
    """
    if date_col not in df.columns:
        raise ValueError(f"{date_col} not found in DataFrame")
    # Ensure datetime
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors='coerce')

    def assign_market_era(date):
        if pd.isna(date):
            return np.nan
        if date < pd.Timestamp('2019-01-01'):
            return 0  # Pre-Covid
        elif date < pd.Timestamp('2022-01-01'):
            return 1  # Covid
        else:
            return 2  # New Normal

    def calc_covid_intensity(date):
        if pd.isna(date):
            return np.nan
        if date < pd.Timestamp('2019-01-01'):
            return 0.0
        elif date <= pd.Timestamp('2021-09-30'):
            total_days = (pd.Timestamp('2021-09-30') - pd.Timestamp('2019-01-01')).days
            days = (date - pd.Timestamp('2019-01-01')).days
            return min(1.0, max(0.0, days / total_days))
        else:
            days_passed = (date - pd.Timestamp('2021-09-30')).days
            lambda_ = np.log(1/0.12) / ((pd.Timestamp('2023-01-01') - pd.Timestamp('2021-09-30')).days)
            return float(np.exp(-lambda_ * days_passed))

    def assign_sample_weight(date):
        if pd.isna(date):
            return np.nan
        if date < pd.Timestamp('2019-01-01'):
            return 0.5
        elif date < pd.Timestamp('2022-01-01'):
            return 0.3
        elif date < pd.Timestamp('2023-01-01'):
            return 2.0
        else:
            return 1.0

    df['market_era'] = df[date_col].apply(assign_market_era)
    df['covid_intensity'] = df[date_col].apply(calc_covid_intensity)
    df['sample_weight'] = df[date_col].apply(assign_sample_weight)
    return df

def run_featurization(
    master_table_path: Path,
    raw_dir: Path,
    output_dir: Path,
    config_path: Path | None = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Config-driven feature engineering pipeline.

    Flow:
        1. Load master_table.csv  (READ-ONLY — never modified)
        2. Load configs/features.yaml
        3. Apply  scope='row'   rules  →  per-order-row transformations
        4. Aggregate to daily level
        5. Apply  scope='daily' rules  →  post-aggregation transformations
        6. Save final table as  data/output/featured_table.parquet

    Args:
        master_table_path : Path to the merged master_table.csv.
        raw_dir           : Path to data/raw/ (for loading sales.csv target).
        output_dir        : Path to data/output/ (for writing featured_table.parquet).
        config_path       : Optional override for features.yaml path.
                            Defaults to <project_root>/configs/features.yaml.
        verbose           : Whether to emit detailed log messages.

    Returns:
        Final featured DataFrame (daily level).
    """
    if verbose:
        logger.info("  🚀 Starting Config-Driven Feature Engineering...")

    # ── Resolve config path ──────────────────────────────────────────────────
    if config_path is None:
        # Walk up from src/ to project root, then into configs/
        config_path = Path(__file__).parent.parent / "configs" / "features.yaml"

    # ── 1. Load master table (read-only) ────────────────────────────────────
    if not master_table_path.exists():
        raise FileNotFoundError(f"Master table not found: {master_table_path}")

    if master_table_path.suffix == '.parquet':
        df = pd.read_parquet(master_table_path, engine="pyarrow")
    else:
        df = pd.read_csv(master_table_path, low_memory=False)

    if verbose:
        logger.info(
            f"  📂 Loaded master table: "
            f"{df.shape[0]:,} rows × {df.shape[1]} columns"
        )

    # Coerce date columns to datetime
    date_cols = ["order_date", "ship_date", "delivery_date"]
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # ── 2. Load feature config ───────────────────────────────────────────────
    rules = _load_feature_config(config_path)
    if verbose:
        logger.info(f"  📋 Loaded {len(rules)} feature rule(s) from {config_path.name}")

    # ── 3. Apply ROW-LEVEL rules (before aggregation) ───────────────────────
    if verbose:
        logger.info("  🔧 Applying row-level feature rules...")
    df = _apply_features(df, rules, scope="row")

    # Clamp negative delivery_days if the column was created
    if "delivery_days" in df.columns:
        df.loc[df["delivery_days"] < 0, "delivery_days"] = np.nan

    # ── 4. Daily aggregation ─────────────────────────────────────────────────
    df["Date"] = df["order_date"].dt.normalize()
    df = df.sort_values("Date").reset_index(drop=True)  # Sort before groupby (critical for Lag)

    # ── Pre-groupby: create boolean helper columns for ratio features ─────────
    # Device type: mobile ratio
    if "device_type" in df.columns:
        df["_is_mobile"] = (df["device_type"].astype(str).str.lower() == "mobile").astype(int)
    # Payment method: COD ratio
    if "payment_method" in df.columns:
        df["_is_cod"] = (df["payment_method"].astype(str).str.lower().str.contains("cod|cash", na=False)).astype(int)
    # Discount numerator: discount_amount * quantity (for discount depth)
    if "discount_amount" in df.columns and "quantity" in df.columns:
        df["_discount_total"] = (
            pd.to_numeric(df["discount_amount"], errors="coerce").fillna(0)
        )
    # Discount denominator: price * quantity (gross revenue before discount)
    if "unit_price" in df.columns and "quantity" in df.columns:
        df["_gross_revenue"] = (
            pd.to_numeric(df["unit_price"], errors="coerce").fillna(0) *
            pd.to_numeric(df["quantity"], errors="coerce").fillna(0)
        )

    # Dynamic aggregation spec
    base_agg: dict = {
        "order_id":             "count",
        "is_promotion":         "sum",
        "delivery_days":        "mean",
        "quantity":             "sum",
        "line_revenue":         "sum",
        "line_cogs":            "sum",      # Deterministic Anchor
        "is_legacy":            "sum",      # For Legacy Intensity
        "category_return_prob": "mean",     # Weighted risk
        # Group 1: Inventory Signals
        "stockout_flag":        "mean",     # daily_stockout_rate (proportion)
        "fill_rate":            "mean",     # daily_avg_fill_rate
        # Group 2: Discount depth helpers
        "_discount_total":      "sum",
        "_gross_revenue":       "sum",
        # Group 3: Device & Payment ratio helpers
        "_is_mobile":           "sum",
        "_is_cod":              "sum",
    }

    # Automatically aggregate any target-encoded columns
    for col in df.columns:
        if col.endswith("_encoded"):
            base_agg[col] = "mean"

    agg_spec = {k: v for k, v in base_agg.items() if k in df.columns}

    daily_df = df.groupby("Date").agg(agg_spec).reset_index()

    # Rename aggregated columns for clarity
    rename_map = {
        "order_id":             "daily_order_count",
        "is_promotion":         "daily_promo_order_count",
        "delivery_days":        "avg_delivery_days",
        "quantity":             "daily_total_quantity",
        "line_revenue":         "daily_total_item_revenue",
        "line_cogs":            "daily_total_cogs",
        "category_return_prob": "daily_return_risk_index",
        "stockout_flag":        "daily_stockout_rate",
        "fill_rate":            "daily_avg_fill_rate",
    }
    daily_df = daily_df.rename(columns={k: v for k, v in rename_map.items() if k in daily_df.columns})

    # --- FEATURE: Legacy Intensity ---
    if "is_legacy" in daily_df.columns:
        daily_df["legacy_intensity"] = daily_df["is_legacy"] / daily_df["daily_order_count"]
        daily_df.drop(columns=["is_legacy"], inplace=True)

    # --- GROUP 2: Discount Depth (daily_discount_depth) ---
    # = Sum(discount_amount) / Sum(unit_price * quantity) — proportion of revenue given away
    if "_discount_total" in daily_df.columns and "_gross_revenue" in daily_df.columns:
        daily_df["daily_discount_depth"] = (
            daily_df["_discount_total"] / daily_df["_gross_revenue"].replace(0, np.nan)
        ).fillna(0).clip(0, 1)
        daily_df.drop(columns=["_discount_total", "_gross_revenue"], inplace=True)

    # --- GROUP 3: Device & Payment Ratios ---
    if "_is_mobile" in daily_df.columns:
        daily_df["daily_mobile_ratio"] = (
            daily_df["_is_mobile"] / daily_df["daily_order_count"].replace(0, np.nan)
        ).fillna(0)
        daily_df.drop(columns=["_is_mobile"], inplace=True)
    if "_is_cod" in daily_df.columns:
        daily_df["daily_cod_ratio"] = (
            daily_df["_is_cod"] / daily_df["daily_order_count"].replace(0, np.nan)
        ).fillna(0)
        daily_df.drop(columns=["_is_cod"], inplace=True)

    # --- GROUP 4: AOV & UPT (must be computed AFTER groupby) ---
    # AOV = Revenue / orders  |  UPT = Units / orders
    # XGBoost cannot learn divisions on its own — pre-computing is critical.
    if "daily_total_item_revenue" in daily_df.columns:
        daily_df["aov"] = (
            daily_df["daily_total_item_revenue"] / daily_df["daily_order_count"].replace(0, np.nan)
        ).fillna(0)
    if "daily_total_quantity" in daily_df.columns:
        daily_df["upt"] = (
            daily_df["daily_total_quantity"] / daily_df["daily_order_count"].replace(0, np.nan)
        ).fillna(0)

    # ── 5. Merge with target (sales.csv) ────────────────────────────────────
    sales_path = raw_dir / "sales.csv"
    if sales_path.exists():
        sales_df = pd.read_csv(sales_path)
        sales_df["Date"] = pd.to_datetime(sales_df["Date"]).dt.normalize()
        final_df = sales_df.merge(daily_df, on="Date", how="left")
        final_df = final_df.sort_values("Date").reset_index(drop=True)

        # Fill missing values for days with no orders
        fill_cols = [c for c in final_df.columns if c not in ["Date", "Revenue", "COGS"]]
        final_df[fill_cols] = final_df[fill_cols].fillna(0)
    else:
        final_df = daily_df
    # ── 5b. Merge web traffic (daily, aggregated) ──────────────────────────────
    web_traffic_path = raw_dir / "web_traffic.csv"
    if web_traffic_path.exists():
        wt = pd.read_csv(web_traffic_path, low_memory=False)
        wt["Date"] = pd.to_datetime(wt["date"], errors="coerce").dt.normalize()
        wt_daily = wt.groupby("Date").agg(
            wt_sessions         =("sessions",                "sum"),
            wt_unique_visitors  =("unique_visitors",         "sum"),
            wt_page_views       =("page_views",              "sum"),
            wt_bounce_rate      =("bounce_rate",             "mean"),
            wt_avg_session_dur  =("avg_session_duration_sec","mean"),
        ).reset_index()
        final_df = final_df.merge(wt_daily, on="Date", how="left")
        wt_base_cols = [c for c in wt_daily.columns if c != "Date"]
        final_df[wt_base_cols] = final_df[wt_base_cols].fillna(0)
        if verbose:
            logger.info(
                f"  📦 Merged daily web traffic "
                f"({len(wt_daily)} days, {len(wt_base_cols)} metrics)"
            )

    # ── 5c. COVID / Market-Era Features ─────────────────────────────────────
    # market_era (0=Pre-Covid, 1=Covid, 2=New Normal)
    # covid_intensity (0-1 continuous signal)
    # sample_weight (used by trainer to up-weight recent data)
    if verbose:
        logger.info("  Adding COVID & Market-Era features (market_era, covid_intensity, sample_weight)...")
    final_df = add_market_era_features(final_df, date_col="Date")

    # ── 5d. Generate LAG features (non-leaky) ────────────────────────────────
    if verbose:
        logger.info("  Generating lag features (Seasonal & Multi-resolution)...")

    # Only lag numeric features that aren't target variables
    lag_source_cols = [
        c for c in final_df.columns
        if c not in ["Date", "Revenue", "COGS"]
        and pd.api.types.is_numeric_dtype(final_df[c])
    ]

    for col in lag_source_cols:
        final_df[f"{col}_lag7"]   = final_df[col].shift(7)
        final_df[f"{col}_lag30"]  = final_df[col].shift(30)
        final_df[f"{col}_lag365"] = final_df[col].shift(365)
        
        final_df[f"{col}_roll7"]  = final_df[col].shift(1).rolling(window=7, min_periods=1).mean()
        final_df[f"{col}_roll30"] = final_df[col].shift(1).rolling(window=30, min_periods=1).mean()
        final_df[f"{col}_roll90"] = final_df[col].shift(1).rolling(window=90, min_periods=1).mean()
    # Drop raw wt_ columns — they are 0 for all test-period dates (web_traffic ends 2022).
    # Their lag/rolling variants (wt_*_lag*, wt_*_roll*) remain as valid features.
    wt_base = [
        c for c in final_df.columns
        if c.startswith("wt_") and not any(s in c for s in ["_lag", "_roll"])
    ]
    if wt_base:
        final_df = final_df.drop(columns=wt_base)
        if verbose:
            logger.info(
                f"  🗑  Dropped {len(wt_base)} raw wt_ columns; "
                f"lag/roll variants retained for test-period validity."
            )
    # ── 5d. Advanced Calendar Features & LUNAR TET WINDOW ───────────────────
    if verbose:
        logger.info("  Adding Advanced Calendar & Lunar Tet Window...")

    final_df["day_of_year"]  = final_df["Date"].dt.dayofyear
    final_df["week_of_year"] = final_df["Date"].dt.isocalendar().week.astype(int)
    
    # Fixed holidays countdown
    holidays_fixed = ["01-01", "04-30", "05-01", "09-02", "12-25"]
    
    def _get_days_until_holiday(dt):
        curr_year = dt.year
        potential_dates = []
        for year in [curr_year, curr_year + 1]:
            for h in holidays_fixed:
                potential_dates.append(pd.to_datetime(f"{year}-{h}"))
        
        # Find the nearest future holiday
        future_holidays = [h for h in potential_dates if h >= dt]
        if not future_holidays:
            return 365 # Fallback
        nearest = min(future_holidays)
        return (nearest - dt).days

    final_df["days_until_holiday"] = final_df["Date"].apply(_get_days_until_holiday)

    if verbose:
        logger.info(f"     Added multi-resolution lag features and calendar windows.")

    # ── 6. Apply DAILY-LEVEL rules (after aggregation + lags) ────────────────
    if verbose:
        logger.info("  🔧 Applying daily-level feature rules...")
    final_df = _apply_features(final_df, rules, scope="daily")

    # ── 7. Save as Parquet ───────────────────────────────────────────────────
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "featured_table.parquet"
    final_df.to_parquet(output_path, index=False, engine="pyarrow")

    if verbose:
        logger.info("  ✅ Feature Engineering complete!")
        logger.info(
            f"  📊 Output shape: "
            f"{final_df.shape[0]:,} days × {final_df.shape[1]} columns"
        )
        logger.info(f"  📋 Columns: {list(final_df.columns)}")
        logger.info(f"  💾 Saved → {output_path}")

    return final_df


# ──────────────────────────────────────────────────────────────────────────────
# Standalone run
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    run_featurization(
        master_table_path=project_root / "data/output/master_table.csv",
        raw_dir=project_root / "data/raw",
        output_dir=project_root / "data/output",
        config_path=project_root / "configs/features.yaml",
    )
