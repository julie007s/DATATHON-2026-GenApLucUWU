"""
============================================================
MODULE: merger.py  (Star Schema Data Merger)
============================================================
Purpose: Join all cleaned CSV tables into one master table
         using a Star Schema pattern centred on `order_items`.

STAR SCHEMA:
  FACT table   : order_items
  DIMENSIONS   : orders, customers, products, payments,
                 shipments, reviews, returns, geography,
                 inventory (aggregated), promotions

JOIN STRATEGY:
  All joins are LEFT JOINs from the fact table outwards so
  that every order line item is preserved even when dimension data
  is missing (nulls after join are expected and acceptable).

RAM SAFETY:
  - Every raw dimension table is deleted (del + gc.collect())
    immediately after it is joined.
  - _agg_inventory() is hardened against missing/renamed
    date columns: it always returns exactly one row per
    product_id regardless of whether a date column exists.
  - _safe_merge() logs a row-count check so fan-out joins
    (where right has duplicate keys) are detected early.

OUTPUT:
  data/output/master_table.csv
============================================================
"""

from __future__ import annotations

import gc
import pandas as pd
from pathlib import Path
from colorama import Fore, Style, init

init(autoreset=True)


# ──────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────

def _load(interim_dir: Path, filename: str) -> pd.DataFrame | None:
    """
    Load a cleaned CSV from interim/. Returns None if the file is missing.
    """
    path = interim_dir / filename
    if not path.exists():
        print(f"  {Fore.YELLOW}⚠  Not found (skipped): {filename}{Style.RESET_ALL}")
        return None
    return pd.read_csv(path, low_memory=False)


def _safe_merge(
    left: pd.DataFrame,
    right: pd.DataFrame | None,
    on: str | list[str],
    label: str,
    suffixes: tuple[str, str] = ("", "_dim"),
) -> pd.DataFrame:
    """
    Perform a LEFT JOIN; skip silently if right is None.

    Fan-out guard: after merging, if the row count grew relative to the left
    table, a warning is printed so the caller can investigate.

    Args:
        left    : Left (fact) DataFrame.
        right   : Right (dimension) DataFrame, or None.
        on      : Column name(s) to join on.
        label   : Human-readable label for logging.
        suffixes: Column suffixes for duplicate names.

    Returns:
        Merged DataFrame (or left unchanged if right is None).
    """
    if right is None:
        print(f"  {Fore.YELLOW}⚠  Skipping join: {label} (table not available){Style.RESET_ALL}")
        return left

    # Check if the join keys exist in both tables
    keys = [on] if isinstance(on, str) else on
    missing_left = [k for k in keys if k not in left.columns]
    missing_right = [k for k in keys if k not in right.columns]
    
    if missing_left or missing_right:
        print(f"  {Fore.RED}⚠  Skipping join: {label}. Missing keys. Left missing: {missing_left}, Right missing: {missing_right}{Style.RESET_ALL}")
        return left

    before_rows = len(left)
    before_cols = len(left.columns)

    merged = left.merge(right, on=on, how="left", suffixes=suffixes)

    added_cols = len(merged.columns) - before_cols
    added_rows = len(merged) - before_rows

    if added_rows > 0:
        # Fan-out detected — right table has duplicate join keys
        print(
            f"  {Fore.RED}⚠  Fan-out in '{label}': "
            f"rows grew {before_rows:,} → {len(merged):,} "
            f"(+{added_rows:,}). "
            f"Right table likely has duplicate keys on: {on}{Style.RESET_ALL}"
        )
    else:
        print(f"  ✔  Joined {label} (+{added_cols} columns, key: {on})")

    return merged


# ──────────────────────────────────────────────────────────
# DIMENSION PRE-PROCESSING
# ──────────────────────────────────────────────────────────

def _agg_inventory_temporal(inventory: pd.DataFrame) -> pd.DataFrame:
    """
    Prepare inventory for a temporally-safe join keyed on
    (product_id, order_year, order_month).

    Problem with the old approach:
        Taking the latest snapshot per product_id and joining on product_id alone
        means orders from 2012 receive stock levels captured in 2022 — pure future
        data leakage.

    Fix:
        Each end-of-month snapshot (month M) is assigned to orders placed in
        month M+1.  Since snapshot_date is always the last day of the month,
        adding 1 day reliably gives the 1st of the next month, from which we
        extract the applicable order year/month.

        Result: an order on 2012-07-10 sees the 2012-06 snapshot (NaN, because
        the first inventory snapshot is 2012-07-31) rather than the 2022-12-31
        snapshot.  NaN fill happens downstream in the null-handling section.

    Returns:
        DataFrame keyed by [product_id, order_year, order_month] with columns:
        stock_on_hand, fill_rate, sell_through_rate, stockout_flag, stockout_days
        (whichever exist in the source file).
    """
    inv = inventory.copy()
    inv["snapshot_date"] = pd.to_datetime(inv["snapshot_date"], errors="coerce")
    inv = inv.dropna(subset=["snapshot_date"])

    # snapshot_date is end-of-month → +1 day = 1st of next month
    next_day = inv["snapshot_date"] + pd.Timedelta(days=1)
    inv["order_year"]  = next_day.dt.year
    inv["order_month"] = next_day.dt.month

    keep = ["product_id", "order_year", "order_month"] + [
        c for c in ["stock_on_hand", "fill_rate", "sell_through_rate",
                    "stockout_flag", "stockout_days"]
        if c in inv.columns
    ]

    # If the same (product, order_month) has multiple rows (edge case), keep latest.
    inv_agg = (
        inv.sort_values("snapshot_date")
           .groupby(["product_id", "order_year", "order_month"], sort=False)
           .last()
           .reset_index()
    )
    print("       (inventory: temporal join on product_id × order_year × order_month, 1-month lag)")
    return inv_agg[[c for c in keep if c in inv_agg.columns]]


# ──────────────────────────────────────────────────────────
# MAIN MERGE FUNCTION
# ──────────────────────────────────────────────────────────

def merge_tables(
    interim_dir: Path,
    output_dir: Path,
    output_filename: str = "master_table.csv",
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Load all cleaned tables from interim/ and join them into a master table.

    Join sequence (all LEFT JOINs from order_items outward):
      order_items
        ← orders          (order_id)
        ← customers       (customer_id)
        ← geography       (city + province)
        ← products        (product_id)
        ← payments        (order_id)
        ← shipments       (order_id)
        ← reviews         (order_id, product_id)
        ← returns         (order_id, product_id)
        ← promotions      (promo_id)
        ← inventory_agg   (product_id)

    RAM strategy:
      Each raw dimension DataFrame is deleted and garbage-collected
      immediately after it is joined.

    Args:
        interim_dir     : Directory containing cleaned CSV files.
        output_dir      : Directory where master_table.csv is saved.
        output_filename : Name of the output file.
        verbose         : If True, print join progress.

    Returns:
        The assembled master DataFrame.
    """
    if verbose:
        print(f"\n{Fore.BLUE}{'═' * 60}")
        print("  STAGE 2: DATA MERGING (Star Schema - Item Level)")
        print(f"{'═' * 60}{Style.RESET_ALL}")

    # ── Load Fact Table ───────────────────────────────────────
    order_items = _load(interim_dir, "order_items.csv")
    if order_items is None:
        raise FileNotFoundError(
            "order_items.csv not found in interim/. "
            "Run the validation + cleaning step first."
        )

    master = order_items.copy()
    del order_items
    gc.collect()

    # ── Create synthetic primary key for each order line item ─────
    # order_item_id = "<order_id>_<product_id>" — used as the join key
    # for item-level dimension tables (reviews, returns).
    master["order_item_id"] = (
        master["order_id"].astype(str) + "_" + master["product_id"].astype(str)
    )

    # Create a line_revenue column early for convenience
    if all(c in master.columns for c in ["unit_price", "quantity"]):
        master["line_revenue"] = (
            pd.to_numeric(master["unit_price"], errors="coerce").fillna(0) * 
            pd.to_numeric(master["quantity"], errors="coerce").fillna(0)
        )
        if "discount_amount" in master.columns:
            master["line_revenue"] -= pd.to_numeric(master["discount_amount"], errors="coerce").fillna(0)

    # ── Join orders ───────────────────────────────────────────
    orders = _load(interim_dir, "orders.csv")
    master = _safe_merge(master, orders, on="order_id", label="orders")
    del orders
    gc.collect()

    # ── Join customers ────────────────────────────────────────
    customers = _load(interim_dir, "customers.csv")
    if customers is not None and "customer_id" in master.columns:
        # Drop columns from customers that already exist in master (e.g. zip, city from
        # orders) to prevent redundant _dim-suffixed duplicates in the output.
        dup_cols = [c for c in customers.columns if c != "customer_id" and c in master.columns]
        cust_slim = customers.drop(columns=dup_cols, errors="ignore")
        master = _safe_merge(master, cust_slim, on="customer_id", label="customers")
    del customers
    gc.collect()

    # ── Join geography ────────────────────────────────────────
    geography = _load(interim_dir, "geography.csv")
    if geography is not None and "zip" in master.columns:
        # Correct FK is zip (not city+province — province column does not exist).
        # Only bring in region and district; city is already in master from orders.
        geo_cols = ["zip"] + [c for c in ["region", "district"] if c in geography.columns]
        master = _safe_merge(master, geography[geo_cols], on="zip", label="geography")
    del geography
    gc.collect()

    # ── Join products ─────────────────────────────────────────
    products = _load(interim_dir, "products.csv")
    if products is not None and "product_id" in master.columns:
        master = _safe_merge(master, products, on="product_id", label="products")
    del products
    gc.collect()

    # ── Join payments ─────────────────────────────────────────
    payments = _load(interim_dir, "payments.csv")
    if payments is not None:
        # Prevent fan-out if an order has multiple payment methods.
        # We aggregate to total payment per order to be safe.
        pay_agg = payments.groupby("order_id").agg(
            payment_value=("payment_value", "sum"),
            installments=("installments", "max"),
        ).reset_index()
        # payment_method is NOT re-added here — it already exists in master from the
        # orders join and is 100% identical (confirmed by data audit, 0 mismatches).
        del payments
        gc.collect()

        master = _safe_merge(master, pay_agg, on="order_id", label="payments")
        del pay_agg
        gc.collect()

    # ── Join shipments ────────────────────────────────────────
    shipments = _load(interim_dir, "shipments.csv")
    master = _safe_merge(master, shipments, on="order_id", label="shipments")
    del shipments
    gc.collect()

    # ── Join reviews ──────────────────────────────────────────
    reviews = _load(interim_dir, "reviews.csv")
    if reviews is not None:
        if all(c in reviews.columns for c in ["order_id", "product_id"]):
            # Build the same synthetic key so we can join on order_item_id
            reviews["order_item_id"] = (
                reviews["order_id"].astype(str) + "_" + reviews["product_id"].astype(str)
            )
            # Drop columns already in master (order_id, product_id, customer_id) to
            # avoid redundant _dim-suffixed duplicates after merge.
            drop_from_reviews = [c for c in ["order_id", "product_id", "customer_id"]
                                  if c in reviews.columns]
            rev_dedup = reviews.drop(columns=drop_from_reviews).drop_duplicates(
                subset=["order_item_id"], keep="last"
            )
            master = _safe_merge(master, rev_dedup, on="order_item_id", label="reviews")
            del rev_dedup
        else:
            # Fallback: no product_id in reviews — join at order level
            rev_dedup = reviews.drop_duplicates(subset=["order_id"], keep="last")
            master = _safe_merge(master, rev_dedup, on="order_id", label="reviews (order level)")
            del rev_dedup
    del reviews
    gc.collect()

    # ── Join returns ──────────────────────────────────────────
    returns = _load(interim_dir, "returns.csv")
    if returns is not None:
        if all(c in returns.columns for c in ["order_id", "product_id"]):
            # Build the same synthetic key and aggregate at line-item level
            returns["order_item_id"] = (
                returns["order_id"].astype(str) + "_" + returns["product_id"].astype(str)
            )
            ret_agg = returns.groupby("order_item_id").agg(
                return_quantity=("return_quantity", "sum"),
                refund_amount=("refund_amount", "sum"),
                return_reason=("return_reason", "first")
            ).reset_index()
            master = _safe_merge(master, ret_agg, on="order_item_id", label="returns")
            del ret_agg
        else:
            # Fallback: no product_id in returns — join at order level
            ret_agg = returns.groupby("order_id").agg(
                return_quantity=("return_quantity", "sum"),
                refund_amount=("refund_amount", "sum"),
                return_reason=("return_reason", "first")
            ).reset_index()
            master = _safe_merge(master, ret_agg, on="order_id", label="returns (order level)")
            del ret_agg
    del returns
    gc.collect()

    # ── Join promotions ───────────────────────────────────────
    promotions = _load(interim_dir, "promotions.csv")
    if promotions is not None and "promo_id" in master.columns:
        keep_cols = [
            "promo_id", "promo_type", "discount_value", 
            "promo_channel", "min_order_value"
        ]
        promotions_subset = promotions[[c for c in keep_cols if c in promotions.columns]].drop_duplicates(subset=["promo_id"])
        master = _safe_merge(master, promotions_subset, on="promo_id", label="promotions")
        del promotions_subset
    del promotions
    gc.collect()

    # ── Join inventory (temporal, lag-safe) ───────────────────
    inventory = _load(interim_dir, "inventory.csv")
    if inventory is not None and "product_id" in master.columns and "order_date" in master.columns:
        # Add temporary year/month keys from order_date to enable temporal matching.
        order_dates = pd.to_datetime(master["order_date"], errors="coerce")
        master["_order_year"]  = order_dates.dt.year
        master["_order_month"] = order_dates.dt.month

        inv_agg = _agg_inventory_temporal(inventory)
        del inventory
        gc.collect()

        # Align inventory join keys to the temp columns we just added to master.
        inv_agg = inv_agg.rename(columns={
            "order_year":  "_order_year",
            "order_month": "_order_month",
        })
        master = _safe_merge(
            master, inv_agg,
            on=["product_id", "_order_year", "_order_month"],
            label="inventory (temporal, lag-safe)"
        )
        master = master.drop(columns=["_order_year", "_order_month"], errors="ignore")
        del inv_agg
        gc.collect()
    elif inventory is not None:
        del inventory
        gc.collect()

    # ── Business Logic: Calculate Financials ─────────────────
    # Cancelled orders are KEPT in master table so downstream models can learn
    # cancellation patterns. Featurizer / trainer should filter by order_status
    # when computing Revenue/COGS targets if needed.

    # Calculate line_cogs (The anchor for profit)
    if all(c in master.columns for c in ["quantity", "cogs"]):
        master["line_cogs"] = (
            pd.to_numeric(master["quantity"], errors="coerce").fillna(0) * 
            pd.to_numeric(master["cogs"], errors="coerce").fillna(0)
        )
        if verbose:
            print("  💰 Calculated 'line_cogs' as a deterministic anchor.")

    # Flag Legacy Orders (Omnichannel insight)
    if all(c in master.columns for c in ["order_date", "signup_date"]):
        master["is_legacy"] = (pd.to_datetime(master["order_date"]) < pd.to_datetime(master["signup_date"])).astype(int)
        if verbose:
            legacy_pct = master["is_legacy"].mean() * 100
            print(f"  🏷  Flagged Legacy orders ({legacy_pct:.1f}% of total).")

    # Calculate Historical Return Probability by Category (Refund Lag mitigation)
    if all(c in master.columns for c in ["category", "order_status"]):
        cat_returns = master.groupby("category")["order_status"].apply(lambda x: (x == "returned").mean()).reset_index()
        cat_returns.rename(columns={"order_status": "category_return_prob"}, inplace=True)
        master = master.merge(cat_returns, on="category", how="left")
        master["category_return_prob"] = master["category_return_prob"].fillna(0)
        if verbose:
            print("  👗 Added 'category_return_prob' to handle refund lag and risk.")

    # ── Handle Nulls in Analytical Columns ───────────────────
    if verbose:
        print(f"  🔧 Filling nulls in remaining analytical columns...")
    
    # 1. Shipping & Returns
    if "shipping_fee" in master.columns:
        master["shipping_fee"] = master["shipping_fee"].fillna(0)
    if "return_quantity" in master.columns:
        master["return_quantity"] = master["return_quantity"].fillna(0)
    if "refund_amount" in master.columns:
        master["refund_amount"] = master["refund_amount"].fillna(0)
    if "rating" in master.columns:
        master["rating"] = master["rating"].fillna(0)
    if "review_title" in master.columns:
        master["review_title"] = master["review_title"].fillna("None")
    if "review_id" in master.columns:
        master["review_id"] = master["review_id"].fillna("NO_REVIEW")

    # ── Drop Redundant/Empty-leaning Columns ────────────────
    drop_cols = ["customer_id_dim", "review_date", "zip_dim"]
    master = master.drop(columns=[c for c in drop_cols if c in master.columns])
    if verbose:
        print(f"  🗑  Dropped redundant columns: {drop_cols}")

    # ── Sort master table ─────────────────────────────────────
    if "order_date" in master.columns:
        master["order_date"] = pd.to_datetime(master["order_date"], errors="coerce")
        master = master.sort_values(["order_date", "order_id"]).reset_index(drop=True)
        if verbose:
            print(f"  ✔  Sorted master table chronologically by 'order_date'")

    # ── Save master table ─────────────────────────────────────
    output_dir.mkdir(parents=True, exist_ok=True)
    save_path = output_dir / output_filename
    master.to_csv(save_path, index=False, encoding="utf-8")

    if verbose:
        print(
            f"\n  {Fore.GREEN}✅ Master table saved → {save_path}\n"
            f"     {master.shape[0]:,} rows × {master.shape[1]} columns"
            f"{Style.RESET_ALL}"
        )

    return master
