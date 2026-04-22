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

def _agg_inventory(inventory: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate inventory to exactly ONE row per product_id.

    Strategy (in priority order):
      1. If a date-like column exists → keep the row with the most recent date.
         The column is auto-detected: tries 'date', 'Date', 'snapshot_date',
         'record_date', 'updated_at' in order.
      2. If no date column is found → keep the LAST row per product_id
         (as it appears in the file). This guarantees uniqueness and avoids
         the fan-out that would occur if the raw table were joined directly.

    Only the columns needed for the join are returned:
      product_id, stock_on_hand, fill_rate, sell_through_rate

    Args:
        inventory: Raw (or cleaned) inventory DataFrame.

    Returns:
        DataFrame with exactly one row per product_id.
    """
    # Candidate date column names (case-sensitive, checked in order)
    DATE_CANDIDATES = ["date", "Date", "snapshot_date", "record_date", "updated_at"]

    inv = inventory.copy()
    date_col: str | None = next(
        (c for c in DATE_CANDIDATES if c in inv.columns), None
    )

    if date_col is not None:
        inv[date_col] = pd.to_datetime(inv[date_col], errors="coerce")
        # Sort ascending so .last() gives the most recent row per product
        inv = (
            inv.sort_values(date_col)
               .groupby("product_id", sort=False)
               .last()
               .reset_index()
        )
        print(f"       (inventory deduplicated on '{date_col}': latest row per product)")
    else:
        print(
            f"  {Fore.YELLOW}⚠  inventory.csv has no recognised date column. "
            f"Using last row per product_id to ensure uniqueness.{Style.RESET_ALL}"
        )
        inv = inv.groupby("product_id", sort=False).last().reset_index()

    # Return only the columns that exist in this particular inventory file
    # Updated to include stockout_flag and stockout_days for supply chain analysis
    keep = ["product_id"] + [
        c for c in ["stock_on_hand", "fill_rate", "sell_through_rate", "stockout_flag", "stockout_days"]
        if c in inv.columns
    ]
    return inv[keep]


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
        master = _safe_merge(master, customers, on="customer_id", label="customers")
    del customers
    gc.collect()

    # ── Join geography ────────────────────────────────────────
    geography = _load(interim_dir, "geography.csv")
    if geography is not None and all(c in master.columns for c in ["city", "province"]):
        master = _safe_merge(
            master, geography, on=["city", "province"], label="geography"
        )
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
            payment_method=("payment_method", "first"),
            installments=("installments", "max"),
        ).reset_index()
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
        # Deduplicate to prevent fan-out if multiple reviews for same product in an order
        if all(c in reviews.columns for c in ["order_id", "product_id"]):
            rev_dedup = reviews.drop_duplicates(subset=["order_id", "product_id"], keep="last")
            master = _safe_merge(master, rev_dedup, on=["order_id", "product_id"], label="reviews")
            del rev_dedup
        else:
            # Fallback to order_id if product_id is missing
            rev_dedup = reviews.drop_duplicates(subset=["order_id"], keep="last")
            master = _safe_merge(master, rev_dedup, on="order_id", label="reviews (order level)")
            del rev_dedup
    del reviews
    gc.collect()

    # ── Join returns ──────────────────────────────────────────
    returns = _load(interim_dir, "returns.csv")
    if returns is not None:
        if all(c in returns.columns for c in ["order_id", "product_id"]):
            # Group by order_id and product_id to sum return quantity just in case
            ret_agg = returns.groupby(["order_id", "product_id"]).agg(
                return_quantity=("return_quantity", "sum"),
                refund_amount=("refund_amount", "sum"),
                return_reason=("return_reason", "first")
            ).reset_index()
            master = _safe_merge(master, ret_agg, on=["order_id", "product_id"], label="returns")
            del ret_agg
        else:
            # Fallback to order_id
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

    # ── Join inventory ────────────────────────────────────────
    inventory = _load(interim_dir, "inventory.csv")
    if inventory is not None and "product_id" in master.columns:
        inv_agg = _agg_inventory(inventory)
        del inventory
        gc.collect()

        master = _safe_merge(
            master, inv_agg,
            on="product_id", label="inventory (latest snapshot)"
        )
        del inv_agg
        gc.collect()
    elif inventory is not None:
        del inventory
        gc.collect()

    # ── Business Logic: Filter Canceled & Calculate Financials ────
    if "order_status" in master.columns:
        initial_count = len(master)
        master = master[master["order_status"] != "cancelled"].copy()
        if verbose:
            print(f"  ✂  Filtered out {initial_count - len(master):,} 'cancelled' orders (Net Revenue focus).")

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
    master.to_csv(save_path, index=False, encoding="utf-8-sig")

    if verbose:
        print(
            f"\n  {Fore.GREEN}✅ Master table saved → {save_path}\n"
            f"     {master.shape[0]:,} rows × {master.shape[1]} columns"
            f"{Style.RESET_ALL}"
        )

    return master
