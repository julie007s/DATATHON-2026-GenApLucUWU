import pandas as pd
import numpy as np
import yaml
from pathlib import Path
from src.logger import logger


RETURN_REASON_WEIGHTS = {
    "defective": 1.00,
    "wrong_item": 0.95,
    "not_as_described": 0.85,
    "wrong_size": 0.75,
    "damaged": 0.90,
    "quality_issue": 0.85,
    "late_delivery": 0.55,
    "changed_mind": 0.35,
    "no_longer_needed": 0.30,
}


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
        name = rule.get("name")

        if action == "add":
            formula = rule.get("formula", "")
            if not formula:
                logger.warning(f"  ⚠  Rule '{name}' has no formula — skipped.")
                continue

            try:
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

        elif action == "remove":
            cols_to_drop = [name] if isinstance(name, str) else list(name)
            existing = [c for c in cols_to_drop if c in df.columns]
            missing = [c for c in cols_to_drop if c not in df.columns]

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
# Daily feature helpers
# ──────────────────────────────────────────────────────────────────────────────

def _safe_ratio(numerator: pd.Series, denominator: pd.Series, fill_value: float = 0.0) -> pd.Series:
    return numerator.div(denominator.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(fill_value)


def _weighted_average(value: pd.Series, weight: pd.Series) -> float:
    value = pd.to_numeric(value, errors="coerce")
    weight = pd.to_numeric(weight, errors="coerce").fillna(0)
    valid = value.notna() & weight.notna() & (weight > 0)
    if not valid.any():
        return 0.0
    return float((value[valid] * weight[valid]).sum() / weight[valid].sum())


def _build_expanding_prior_rate(
    df: pd.DataFrame,
    key_col: str,
    date_col: str,
    numer_col: str,
    denom_col: str,
) -> pd.DataFrame:
    grouped = (
        df.groupby([date_col, key_col], dropna=False)
        .agg(_numer=(numer_col, "sum"), _denom=(denom_col, "sum"))
        .reset_index()
        .sort_values([key_col, date_col])
    )
    grouped["_prior_numer"] = grouped.groupby(key_col)["_numer"].cumsum().shift(1)
    grouped["_prior_denom"] = grouped.groupby(key_col)["_denom"].cumsum().shift(1)
    global_prior = float(grouped["_numer"].sum() / grouped["_denom"].sum()) if grouped["_denom"].sum() else 0.0
    grouped["prior_rate"] = _safe_ratio(grouped["_prior_numer"], grouped["_prior_denom"], fill_value=global_prior)
    return grouped[[date_col, key_col, "prior_rate"]]


def _build_expanding_prior_count_rate(
    df: pd.DataFrame,
    key_col: str,
    date_col: str,
    event_col: str,
) -> pd.DataFrame:
    grouped = (
        df.groupby([date_col, key_col], dropna=False)
        .agg(_numer=(event_col, "sum"), _denom=(event_col, "size"))
        .reset_index()
        .sort_values([key_col, date_col])
    )
    grouped["_prior_numer"] = grouped.groupby(key_col)["_numer"].cumsum().shift(1)
    grouped["_prior_denom"] = grouped.groupby(key_col)["_denom"].cumsum().shift(1)
    global_prior = float(grouped["_numer"].sum() / grouped["_denom"].sum()) if grouped["_denom"].sum() else 0.0
    grouped["prior_rate"] = _safe_ratio(grouped["_prior_numer"], grouped["_prior_denom"], fill_value=global_prior)
    return grouped[[date_col, key_col, "prior_rate"]]


def add_market_era_features(df: pd.DataFrame, date_col: str = "order_date") -> pd.DataFrame:
    """
    Add deterministic market regime features derived only from calendar time.

    Adds:
      - market_era: 0=Pre-Covid, 1=Covid Shock, 2=New Normal
      - covid_intensity: continuous [0, 1] regime strength
      - sample_weight: training emphasis for more relevant periods
    """
    if date_col not in df.columns:
        raise ValueError(f"{date_col} not found in DataFrame")

    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

    def calc_market_era(date):
        if pd.isna(date):
            return np.nan
        if date < pd.Timestamp("2020-02-01"):
            return 0
        if date <= pd.Timestamp("2021-09-30"):
            return 1
        return 2

    def calc_covid_intensity(date):
        if pd.isna(date):
            return np.nan
        if date < pd.Timestamp("2020-02-01"):
            return 0.0
        if date < pd.Timestamp("2021-05-01"):
            total_days = (pd.Timestamp("2021-05-01") - pd.Timestamp("2020-02-01")).days
            days = (date - pd.Timestamp("2020-02-01")).days
            return 0.7 * (days / total_days)
        if date <= pd.Timestamp("2021-09-30"):
            return 1.0

        days_passed = (date - pd.Timestamp("2021-09-30")).days
        lambda_ = np.log(1 / 0.1) / ((pd.Timestamp("2023-01-01") - pd.Timestamp("2021-09-30")).days)
        return float(np.exp(-lambda_ * days_passed))

    def assign_sample_weight(date):
        if pd.isna(date):
            return np.nan
        if date < pd.Timestamp("2020-02-01"):
            return 0.8
        if date < pd.Timestamp("2022-01-01"):
            return 0.2
        if date < pd.Timestamp("2023-01-01"):
            return 2.5
        return 1.0

    df["market_era"] = df[date_col].apply(calc_market_era).astype("float")
    df["covid_intensity"] = df[date_col].apply(calc_covid_intensity)
    df["sample_weight"] = df[date_col].apply(assign_sample_weight)
    return df


def _prepare_item_semantic_columns(df: pd.DataFrame) -> pd.DataFrame:
    item_df = df.copy()

    quantity = pd.to_numeric(item_df.get("quantity", 0), errors="coerce").fillna(0)
    unit_price = pd.to_numeric(item_df.get("unit_price", 0), errors="coerce").fillna(0)
    discount_amount = pd.to_numeric(item_df.get("discount_amount", 0), errors="coerce").fillna(0)
    price = pd.to_numeric(item_df.get("price", 0), errors="coerce").fillna(0)
    cogs = pd.to_numeric(item_df.get("cogs", 0), errors="coerce").fillna(0)
    return_qty = pd.to_numeric(item_df.get("return_quantity", 0), errors="coerce").fillna(0)

    if "line_revenue" not in item_df.columns:
        item_df["line_revenue"] = unit_price * quantity - discount_amount
    item_df["line_revenue"] = pd.to_numeric(item_df["line_revenue"], errors="coerce").fillna(0)

    item_df["daily_order_line_count"] = 1
    item_df["_discount_amount"] = discount_amount
    item_df["_gross_before_discount"] = (unit_price * quantity) + discount_amount
    item_df["_line_weight"] = (unit_price * quantity).where((unit_price * quantity) > 0, quantity.where(quantity > 0, 1))
    item_df["_margin_ratio"] = _safe_ratio(price - cogs, price, fill_value=0).clip(-1, 1)
    item_df["_returned_qty"] = return_qty.clip(lower=0)
    item_df["_return_flag"] = (item_df["_returned_qty"] > 0).astype(int)

    return_reason = item_df.get("return_reason", pd.Series(index=item_df.index, dtype="object")).astype(str).str.lower()
    item_df["_return_reason_weight"] = return_reason.map(RETURN_REASON_WEIGHTS).fillna(0.5) * item_df["_return_flag"]
    item_df["_return_weighted_qty"] = item_df["_returned_qty"] * item_df["_return_reason_weight"]
    return item_df


def _aggregate_item_level(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate additive and exposure-style metrics from the item grain to daily grain."""
    item_df = _prepare_item_semantic_columns(df)

    item_agg_spec: dict[str, str] = {
        "daily_order_line_count": "sum",
        "is_promotion": "sum",
        "delivery_days": "mean",
        "quantity": "sum",
        "line_revenue": "sum",
        "line_cogs": "sum",
        "category_return_prob": "mean",
        "stockout_flag": "mean",
        "fill_rate": "mean",
        "_discount_amount": "sum",
        "_gross_before_discount": "sum",
    }

    for col in item_df.columns:
        if col.endswith("_encoded"):
            item_agg_spec[col] = "mean"

    item_agg_spec = {k: v for k, v in item_agg_spec.items() if k in item_df.columns}
    daily_item = item_df.groupby("Date").agg(item_agg_spec).reset_index()

    daily_item = daily_item.rename(columns={
        "is_promotion": "daily_promo_line_count",
        "delivery_days": "avg_delivery_days",
        "quantity": "daily_total_quantity",
        "line_revenue": "daily_total_item_revenue",
        "line_cogs": "daily_total_cogs",
        "category_return_prob": "daily_return_risk_index",
        "stockout_flag": "daily_stockout_rate",
        "fill_rate": "daily_avg_fill_rate",
        "_discount_amount": "daily_discount_amount",
        "_gross_before_discount": "daily_gross_revenue_before_discount",
    })

    semantic_daily = (
        item_df.groupby("Date")
        .apply(
            lambda g: pd.Series({
                "daily_expected_margin_mix": _weighted_average(g["_margin_ratio"], g["_line_weight"]),
                "promo_penetration_rate": float(pd.to_numeric(g["is_promotion"], errors="coerce").fillna(0).mean()),
            })
        )
        .reset_index()
    )

    size_prior = _build_expanding_prior_rate(item_df, "size", "Date", "_returned_qty", "quantity")
    item_df = item_df.merge(size_prior, on=["Date", "size"], how="left")
    item_df = item_df.rename(columns={"prior_rate": "_size_prior_return_rate"})

    category_prior = _build_expanding_prior_rate(item_df, "category", "Date", "_return_weighted_qty", "quantity")
    item_df = item_df.merge(category_prior, on=["Date", "category"], how="left")
    item_df = item_df.rename(columns={"prior_rate": "_category_prior_reason_risk"})

    if "region" in item_df.columns:
        regional_rev = (
            item_df.groupby(["Date", "region"], dropna=False)["line_revenue"]
            .sum()
            .reset_index()
        )
        regional_totals = regional_rev.groupby("Date")["line_revenue"].transform("sum")
        regional_rev["share_sq"] = _safe_ratio(regional_rev["line_revenue"], regional_totals, fill_value=0).pow(2)
        regional_concentration = regional_rev.groupby("Date", as_index=False)["share_sq"].sum()
        regional_concentration = regional_concentration.rename(columns={"share_sq": "regional_revenue_concentration_index"})
    else:
        regional_concentration = pd.DataFrame(columns=["Date", "regional_revenue_concentration_index"])

    prior_semantics = (
        item_df.groupby("Date")
        .apply(
            lambda g: pd.Series({
                "size_mix_return_pressure": _weighted_average(g["_size_prior_return_rate"], g["quantity"]),
                "category_reason_weighted_return_risk": _weighted_average(g["_category_prior_reason_risk"], g["quantity"]),
            })
        )
        .reset_index()
    )

    daily_item = daily_item.merge(semantic_daily, on="Date", how="left")
    daily_item = daily_item.merge(prior_semantics, on="Date", how="left")
    daily_item = daily_item.merge(regional_concentration, on="Date", how="left")

    if {
        "daily_discount_amount",
        "daily_gross_revenue_before_discount",
    }.issubset(daily_item.columns):
        daily_item["daily_discount_depth"] = (
            daily_item["daily_discount_amount"]
            / daily_item["daily_gross_revenue_before_discount"].replace(0, np.nan)
        ).fillna(0).clip(0, 1)

    for col in [
        "daily_expected_margin_mix",
        "promo_penetration_rate",
        "size_mix_return_pressure",
        "category_reason_weighted_return_risk",
        "regional_revenue_concentration_index",
    ]:
        if col in daily_item.columns:
            daily_item[col] = pd.to_numeric(daily_item[col], errors="coerce").fillna(0)

    return daily_item


def _build_age_productivity_prior(order_level: pd.DataFrame) -> pd.DataFrame:
    age_daily_orders = (
        order_level.groupby(["Date", "age_group"], dropna=False)
        .agg(order_count=("order_id", "nunique"))
        .reset_index()
        .sort_values(["age_group", "Date"])
    )
    age_daily_orders["prior_orders"] = age_daily_orders.groupby("age_group")["order_count"].cumsum().shift(1)

    age_first_seen = (
        order_level.dropna(subset=["customer_id"])
        .groupby(["age_group", "customer_id"], dropna=False)["Date"]
        .min()
        .reset_index()
    )
    new_customers = (
        age_first_seen.groupby(["Date", "age_group"], dropna=False)
        .size()
        .reset_index(name="new_customers")
        .sort_values(["age_group", "Date"])
    )

    age_productivity = age_daily_orders.merge(new_customers, on=["Date", "age_group"], how="left")
    age_productivity["new_customers"] = age_productivity["new_customers"].fillna(0)
    age_productivity["prior_customers"] = age_productivity.groupby("age_group")["new_customers"].cumsum().shift(1)
    global_prior = float(age_daily_orders["order_count"].sum() / max(age_first_seen.shape[0], 1))
    age_productivity["prior_productivity"] = _safe_ratio(
        age_productivity["prior_orders"],
        age_productivity["prior_customers"],
        fill_value=global_prior,
    )
    return age_productivity[["Date", "age_group", "prior_productivity"]]


def _aggregate_order_level(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse item grain to one row per order, then aggregate correctly to daily grain."""
    order_columns = [
        "order_id", "Date", "device_type", "payment_method", "is_legacy",
        "order_status", "customer_id", "age_group", "installments",
    ]
    existing_order_cols = [c for c in order_columns if c in df.columns]
    if existing_order_cols:
        order_level = df[existing_order_cols].drop_duplicates(subset=["order_id"]).copy()
    else:
        order_level = df[["order_id", "Date"]].drop_duplicates(subset=["order_id"]).copy()

    if "line_revenue" in df.columns:
        order_rev = df.groupby("order_id", as_index=False).agg(order_revenue=("line_revenue", "sum"))
        order_level = order_level.merge(order_rev, on="order_id", how="left")
    else:
        order_level["order_revenue"] = 0.0

    if "quantity" in df.columns:
        order_qty = df.groupby("order_id", as_index=False).agg(order_quantity=("quantity", "sum"))
        order_level = order_level.merge(order_qty, on="order_id", how="left")
    else:
        order_level["order_quantity"] = 0.0

    if "is_promotion" in df.columns:
        order_promo = (
            df.groupby("order_id")["is_promotion"]
            .max()
            .reset_index(name="has_promotion_order")
        )
        order_level = order_level.merge(order_promo, on="order_id", how="left")
    else:
        order_level["has_promotion_order"] = 0

    if "delivery_days" in df.columns:
        order_delivery = (
            df.groupby("order_id")["delivery_days"]
            .mean()
            .reset_index(name="order_delivery_days")
        )
        order_level = order_level.merge(order_delivery, on="order_id", how="left")
    else:
        order_level["order_delivery_days"] = np.nan

    order_level["order_revenue"] = pd.to_numeric(order_level.get("order_revenue", 0), errors="coerce").fillna(0)
    order_level["order_quantity"] = pd.to_numeric(order_level.get("order_quantity", 0), errors="coerce").fillna(0)
    order_level["installments"] = pd.to_numeric(order_level.get("installments", 0), errors="coerce").fillna(0)
    order_level["is_mobile_order"] = (
        order_level.get("device_type", pd.Series(index=order_level.index, dtype="object"))
        .astype(str).str.lower().eq("mobile")
    ).astype(int)
    order_level["is_cod_order"] = (
        order_level.get("payment_method", pd.Series(index=order_level.index, dtype="object"))
        .astype(str).str.lower().str.contains("cod|cash", na=False)
    ).astype(int)
    order_level["is_legacy"] = pd.to_numeric(order_level.get("is_legacy", 0), errors="coerce").fillna(0).astype(int)
    order_level["is_new_customer_order"] = (1 - order_level["is_legacy"]).clip(lower=0)
    order_level["cancel_flag"] = (
        order_level.get("order_status", pd.Series(index=order_level.index, dtype="object"))
        .astype(str).str.lower().eq("cancelled")
    ).astype(int)

    payment_prior = _build_expanding_prior_count_rate(order_level, "payment_method", "Date", "cancel_flag")
    payment_prior = payment_prior.rename(columns={"prior_rate": "_payment_cancel_prior"})
    order_level = order_level.merge(payment_prior, on=["Date", "payment_method"], how="left")

    age_prior = _build_age_productivity_prior(order_level)
    age_prior = age_prior.rename(columns={"prior_productivity": "_age_productivity_prior"})
    order_level = order_level.merge(age_prior, on=["Date", "age_group"], how="left")

    order_level = order_level.sort_values(["customer_id", "Date", "order_id"])
    order_level["inter_order_gap_days"] = (
        order_level.groupby("customer_id")["Date"]
        .diff()
        .dt.days
    )
    order_level["repurchase_cadence_score"] = _safe_ratio(
        pd.Series(1.0, index=order_level.index),
        1 + order_level["inter_order_gap_days"],
        fill_value=0,
    )

    order_daily = order_level.groupby("Date").agg(
        daily_order_count=("order_id", "nunique"),
        daily_promo_order_count=("has_promotion_order", "sum"),
        daily_mobile_order_ratio=("is_mobile_order", "mean"),
        daily_cod_order_ratio=("is_cod_order", "mean"),
        legacy_order_ratio=("is_legacy", "mean"),
        legacy_order_count=("is_legacy", "sum"),
        new_customer_order_count=("is_new_customer_order", "sum"),
        legacy_revenue_total=("order_revenue", lambda s: s[order_level.loc[s.index, "is_legacy"] == 1].sum()),
        new_customer_revenue_total=("order_revenue", lambda s: s[order_level.loc[s.index, "is_legacy"] == 0].sum()),
        customer_repurchase_cadence_index=("repurchase_cadence_score", "median"),
        payment_method_cancellation_risk=("_payment_cancel_prior", "mean"),
        active_customer_demographic_mix_score=("_age_productivity_prior", "mean"),
        financing_intensity_index=("installments", "mean"),
    ).reset_index()

    for col in [
        "customer_repurchase_cadence_index",
        "payment_method_cancellation_risk",
        "active_customer_demographic_mix_score",
        "financing_intensity_index",
    ]:
        if col in order_daily.columns:
            order_daily[col] = pd.to_numeric(order_daily[col], errors="coerce").fillna(0)

    return order_daily


def _aggregate_web_traffic_features(web_traffic_path: Path) -> pd.DataFrame:
    wt = pd.read_csv(web_traffic_path, low_memory=False)
    wt["Date"] = pd.to_datetime(wt["date"], errors="coerce").dt.normalize()
    wt["sessions"] = pd.to_numeric(wt.get("sessions", 0), errors="coerce").fillna(0)
    wt["unique_visitors"] = pd.to_numeric(wt.get("unique_visitors", 0), errors="coerce").fillna(0)
    wt["page_views"] = pd.to_numeric(wt.get("page_views", 0), errors="coerce").fillna(0)
    wt["bounce_rate"] = pd.to_numeric(wt.get("bounce_rate", 0), errors="coerce").fillna(0).clip(0, 1)
    wt["avg_session_duration_sec"] = pd.to_numeric(wt.get("avg_session_duration_sec", 0), errors="coerce").fillna(0)
    wt["high_intent_component"] = wt["sessions"] * (1 - wt["bounce_rate"]) * np.log1p(wt["avg_session_duration_sec"])

    wt_daily = wt.groupby("Date").agg(
        wt_sessions=("sessions", "sum"),
        wt_unique_visitors=("unique_visitors", "sum"),
        wt_page_views=("page_views", "sum"),
        wt_bounce_rate=("bounce_rate", "mean"),
        wt_avg_session_dur=("avg_session_duration_sec", "mean"),
        _intent_sum=("high_intent_component", "sum"),
    ).reset_index()
    wt_daily["high_intent_traffic_share"] = _safe_ratio(
        wt_daily["_intent_sum"],
        wt_daily["wt_sessions"].replace(0, np.nan),
        fill_value=0,
    )
    return wt_daily.drop(columns=["_intent_sum"])


def _finalize_daily_features(daily_df: pd.DataFrame) -> pd.DataFrame:
    """Create semantically correct ratios after item-level and order-level merges."""
    daily_df = daily_df.copy()

    if {"legacy_revenue_total", "daily_total_item_revenue"}.issubset(daily_df.columns):
        daily_df["legacy_revenue_share"] = (
            daily_df["legacy_revenue_total"]
            / daily_df["daily_total_item_revenue"].replace(0, np.nan)
        ).fillna(0)

    if {"legacy_revenue_total", "legacy_order_count"}.issubset(daily_df.columns):
        daily_df["legacy_aov"] = (
            daily_df["legacy_revenue_total"]
            / daily_df["legacy_order_count"].replace(0, np.nan)
        ).fillna(0)

    if {"new_customer_revenue_total", "new_customer_order_count"}.issubset(daily_df.columns):
        daily_df["new_customer_aov"] = (
            daily_df["new_customer_revenue_total"]
            / daily_df["new_customer_order_count"].replace(0, np.nan)
        ).fillna(0)

    if {"daily_total_item_revenue", "daily_order_count"}.issubset(daily_df.columns):
        daily_df["aov"] = (
            daily_df["daily_total_item_revenue"]
            / daily_df["daily_order_count"].replace(0, np.nan)
        ).fillna(0)

    if {"daily_total_quantity", "daily_order_count"}.issubset(daily_df.columns):
        daily_df["upt"] = (
            daily_df["daily_total_quantity"]
            / daily_df["daily_order_count"].replace(0, np.nan)
        ).fillna(0)

    drop_cols = [
        "legacy_order_count",
        "new_customer_order_count",
        "legacy_revenue_total",
        "new_customer_revenue_total",
    ]
    return daily_df.drop(columns=[c for c in drop_cols if c in daily_df.columns])


def _validate_feature_table(final_df: pd.DataFrame, sales_df: pd.DataFrame | None = None) -> None:
    """Run sanity checks so semantic regressions fail loudly."""
    if "Date" not in final_df.columns:
        raise ValueError("Feature table validation failed: 'Date' column missing.")
    if final_df["Date"].isna().any():
        raise ValueError("Feature table validation failed: Date contains NaT values.")
    if final_df["Date"].duplicated().any():
        dupes = final_df.loc[final_df["Date"].duplicated(), "Date"].astype(str).tolist()[:5]
        raise ValueError(f"Feature table validation failed: duplicate Date rows found: {dupes}")
    if not final_df["Date"].is_monotonic_increasing:
        raise ValueError("Feature table validation failed: Date is not sorted ascending.")

    ratio_cols = [
        "daily_discount_depth",
        "daily_mobile_order_ratio",
        "daily_cod_order_ratio",
        "legacy_order_ratio",
        "daily_stockout_rate",
        "daily_avg_fill_rate",
        "promo_penetration_rate",
        "payment_method_cancellation_risk",
        "size_mix_return_pressure",
        "category_reason_weighted_return_risk",
        "regional_revenue_concentration_index",
    ]
    for col in ratio_cols:
        if col in final_df.columns:
            invalid = final_df[col].dropna()
            if not invalid.empty and ((invalid < 0) | (invalid > 1)).any():
                raise ValueError(f"Feature table validation failed: {col} has values outside [0, 1].")

    non_negative_cols = [
        "daily_order_count",
        "high_intent_traffic_share",
        "active_customer_demographic_mix_score",
        "customer_repurchase_cadence_index",
        "financing_intensity_index",
    ]
    for col in non_negative_cols:
        if col in final_df.columns and (final_df[col] < 0).any():
            raise ValueError(f"Feature table validation failed: {col} contains negatives.")

    if "daily_order_line_count" in final_df.columns and "daily_order_count" in final_df.columns:
        if (final_df["daily_order_line_count"] < final_df["daily_order_count"]).any():
            raise ValueError("Feature table validation failed: line counts cannot be lower than order counts.")

    if sales_df is not None and len(final_df) != len(sales_df):
        raise ValueError(
            f"Feature table validation failed: expected {len(sales_df)} sales dates, got {len(final_df)} feature rows."
        )


def _generate_lag_features(final_df: pd.DataFrame) -> pd.DataFrame:
    lag_source_cols = [
        c for c in final_df.columns
        if c not in ["Date", "Revenue", "COGS", "sample_weight"]
        and pd.api.types.is_numeric_dtype(final_df[c])
    ]

    lag_feature_frames = []
    for col in lag_source_cols:
        base = final_df[col]
        lag_feature_frames.append(pd.DataFrame({
            f"{col}_lag7": base.shift(7),
            f"{col}_lag30": base.shift(30),
            f"{col}_lag365": base.shift(365),
            f"{col}_roll7": base.shift(1).rolling(window=7, min_periods=1).mean(),
            f"{col}_roll30": base.shift(1).rolling(window=30, min_periods=1).mean(),
        }))

    if lag_feature_frames:
        final_df = pd.concat([final_df] + lag_feature_frames, axis=1)
    return final_df


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
        1. Load master_table / encoded_master (read-only)
        2. Load configs/features.yaml
        3. Apply row-level rules at item grain
        4. Build item-level daily metrics and order-level daily metrics separately
        5. Merge with sales target and operational daily signals
        6. Create deterministic calendar/regime features and lag-safe derivatives
        7. Save final table as data/output/featured_table.parquet

    Returns:
        Final featured DataFrame (daily level).
    """
    if verbose:
        logger.info("  🚀 Starting Config-Driven Feature Engineering...")

    if config_path is None:
        config_path = Path(__file__).parent.parent / "configs" / "features.yaml"

    if not master_table_path.exists():
        raise FileNotFoundError(f"Master table not found: {master_table_path}")

    if master_table_path.suffix == ".parquet":
        df = pd.read_parquet(master_table_path, engine="pyarrow")
    else:
        df = pd.read_csv(master_table_path, low_memory=False)

    if verbose:
        logger.info(f"  📂 Loaded master table: {df.shape[0]:,} rows × {df.shape[1]} columns")

    date_cols = ["order_date", "ship_date", "delivery_date"]
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    if "order_date" not in df.columns:
        raise ValueError("order_date is required for featurization but was not found.")

    rules = _load_feature_config(config_path)
    if verbose:
        logger.info(f"  📋 Loaded {len(rules)} feature rule(s) from {config_path.name}")

    if verbose:
        logger.info("  🔧 Applying row-level feature rules...")
    df = _apply_features(df, rules, scope="row")

    if "delivery_days" in df.columns:
        df.loc[df["delivery_days"] < 0, "delivery_days"] = np.nan

    df["Date"] = df["order_date"].dt.normalize()
    df = df.sort_values(["Date", "order_id"]).reset_index(drop=True)

    if verbose:
        logger.info("  🧮 Aggregating item-level daily metrics...")
    daily_item = _aggregate_item_level(df)

    if verbose:
        logger.info("  🧮 Aggregating order-level daily metrics...")
    daily_order = _aggregate_order_level(df)

    daily_df = daily_item.merge(daily_order, on="Date", how="outer")
    daily_df = _finalize_daily_features(daily_df)
    daily_df = daily_df.sort_values("Date").reset_index(drop=True)

    sales_df = None
    sales_path = raw_dir / "sales.csv"
    if sales_path.exists():
        sales_df = pd.read_csv(sales_path)
        sales_df["Date"] = pd.to_datetime(sales_df["Date"]).dt.normalize()
        final_df = sales_df.merge(daily_df, on="Date", how="left")
        final_df = final_df.sort_values("Date").reset_index(drop=True)
        fill_cols = [c for c in final_df.columns if c not in ["Date", "Revenue", "COGS"]]
        final_df[fill_cols] = final_df[fill_cols].fillna(0)
    else:
        final_df = daily_df.copy()

    web_traffic_path = raw_dir / "web_traffic.csv"
    if web_traffic_path.exists():
        wt_daily = _aggregate_web_traffic_features(web_traffic_path)
        final_df = final_df.merge(wt_daily, on="Date", how="left")
        wt_base_cols = [c for c in wt_daily.columns if c != "Date"]
        final_df[wt_base_cols] = final_df[wt_base_cols].fillna(0)
        if verbose:
            logger.info(f"  📦 Merged daily web traffic ({len(wt_daily)} days, {len(wt_base_cols)} metrics)")

    if verbose:
        logger.info("  Adding deterministic market regime features (market_era, covid_intensity, sample_weight)...")
    final_df = add_market_era_features(final_df, date_col="Date")

    if verbose:
        logger.info("  Generating lag features (seasonal & multi-resolution, lag-safe)...")
    final_df = _generate_lag_features(final_df)

    wt_base = [
        c for c in final_df.columns
        if c.startswith("wt_") and not any(s in c for s in ["_lag", "_roll"])
    ]
    if wt_base:
        final_df = final_df.drop(columns=wt_base)
        if verbose:
            logger.info(
                f"  🗑  Dropped {len(wt_base)} raw wt_ columns; lag/roll variants retained for test-period validity."
            )

    if verbose:
        logger.info("  Adding advanced calendar features...")
    final_df["day_of_year"] = final_df["Date"].dt.dayofyear
    final_df["week_of_year"] = final_df["Date"].dt.isocalendar().week.astype(int)

    holidays_fixed = ["01-01", "04-30", "05-01", "09-02", "12-25"]

    def _get_days_until_holiday(dt):
        curr_year = dt.year
        potential_dates = []
        for year in [curr_year, curr_year + 1]:
            for h in holidays_fixed:
                potential_dates.append(pd.to_datetime(f"{year}-{h}"))
        future_holidays = [h for h in potential_dates if h >= dt]
        if not future_holidays:
            return 365
        nearest = min(future_holidays)
        return (nearest - dt).days

    final_df["days_until_holiday"] = final_df["Date"].apply(_get_days_until_holiday)

    if verbose:
        logger.info("  🔧 Applying daily-level feature rules...")
    final_df = _apply_features(final_df, rules, scope="daily")
    final_df = final_df.sort_values("Date").reset_index(drop=True)

    _validate_feature_table(final_df, sales_df=sales_df)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "featured_table.parquet"
    final_df.to_parquet(output_path, index=False, engine="pyarrow")

    if verbose:
        logger.info("  ✅ Feature Engineering complete!")
        logger.info(f"  📊 Output shape: {final_df.shape[0]:,} days × {final_df.shape[1]} columns")
        logger.info(f"  📋 Columns: {list(final_df.columns)}")
        logger.info(f"  💾 Saved → {output_path}")

    return final_df


if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    run_featurization(
        master_table_path=project_root / "data/output/master_table.csv",
        raw_dir=project_root / "data/raw",
        output_dir=project_root / "data/output",
        config_path=project_root / "configs" / "features.yaml",
    )
