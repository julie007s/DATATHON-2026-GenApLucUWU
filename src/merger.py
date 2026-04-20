"""
============================================================
MODULE: merger.py  (Star Schema Data Merger)
============================================================
Purpose: Join all cleaned CSV tables into one master table
         using a Star Schema pattern centred on `orders`.

STAR SCHEMA:
  FACT table   : orders
  DIMENSIONS   : customers, order_items, products, payments,
                 shipments, reviews, returns, geography,
                 inventory (aggregated), promotions

JOIN STRATEGY:
  All joins are LEFT JOINs from the fact table outwards so
  that every order row is preserved even when dimension data
  is missing (nulls after join are expected and acceptable).

RAM SAFETY:
  - Every raw dimension table is deleted (del + gc.collect())
    immediately after its aggregated form is produced.
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

def _agg_order_items(order_items: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate order_items to one row per order_id.

    Returns only the aggregated summary — the original table should be
    deleted by the caller after this function returns.

    Aggregations:
      - total_quantity     : sum of quantity
      - total_item_revenue : sum of (unit_price × quantity - discount_amount)
      - distinct_products  : number of unique product_ids per order
    """
    # Work on a minimal copy — only the columns we actually need
    needed = [c for c in ["order_id", "product_id", "quantity",
                           "unit_price", "discount_amount",
                           "promo_id", "promo_id_2"]
              if c in order_items.columns]
    oi = order_items[needed].copy()

    # Create promotion flag
    oi["has_promo"] = 0
    if "promo_id" in oi.columns:
        oi.loc[oi["promo_id"].notna() & (oi["promo_id"] != ""), "has_promo"] = 1
    if "promo_id_2" in oi.columns:
        oi.loc[oi["promo_id_2"].notna() & (oi["promo_id_2"] != ""), "has_promo"] = 1

    for col in ["quantity", "unit_price", "discount_amount"]:
        if col in oi.columns:
            oi[col] = pd.to_numeric(oi[col], errors="coerce").fillna(0)

    oi["line_revenue"] = (
        oi.get("unit_price", 0) * oi.get("quantity", 0)
        - oi.get("discount_amount", 0)
    )

    agg_spec: dict = {
        "total_quantity": ("quantity", "sum"),
        "total_item_revenue": ("line_revenue", "sum"),
        "has_promo": ("has_promo", "max")
    }
    if "product_id" in oi.columns:
        agg_spec["distinct_products"] = ("product_id", "nunique")

    agg = oi.groupby("order_id").agg(**agg_spec).reset_index()
    return agg


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
    keep = ["product_id"] + [
        c for c in ["stock_on_hand", "fill_rate", "sell_through_rate"]
        if c in inv.columns
    ]
    return inv[keep]


def _primary_product_per_order(order_items: pd.DataFrame) -> pd.DataFrame:
    """
    Return a one-row-per-order mapping to the most common product_id.

    Used to join dimension tables (products, inventory) that are keyed on
    product_id rather than order_id.

    Args:
        order_items: Raw order_items DataFrame (must contain order_id,
                     product_id).

    Returns:
        DataFrame with columns [order_id, primary_product_id].
    """
    return (
        order_items[["order_id", "product_id"]]
        .groupby("order_id")["product_id"]
        .agg(lambda s: s.mode().iat[0] if len(s) > 0 else pd.NA)
        .reset_index()
        .rename(columns={"product_id": "primary_product_id"})
    )


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

    Join sequence (all LEFT JOINs from orders outward):
      orders
        ← customers       (customer_id)
        ← geography       (city + province)
        ← order_items_agg (order_id)          ← raw order_items freed here
        ← products        (primary_product_id)
        ← payments_agg    (order_id)           ← raw payments freed here
        ← shipments       (order_id)           ← raw shipments freed here
        ← reviews_agg     (order_id)           ← raw reviews freed here
        ← returns_agg     (order_id)           ← raw returns freed here
        ← promotions      (promo_code)         ← raw promotions freed here
        ← inventory_agg   (primary_product_id) ← raw inventory freed here

    RAM strategy:
      Each raw dimension DataFrame is deleted and garbage-collected
      immediately after its aggregated/filtered form is produced.

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
        print("  STAGE 2: DATA MERGING (Star Schema)")
        print(f"{'═' * 60}{Style.RESET_ALL}")

    # ── Load all tables ───────────────────────────────────────
    # Large tables are loaded one at a time and freed as soon as possible.
    orders = _load(interim_dir, "orders.csv")
    if orders is None:
        raise FileNotFoundError(
            "orders.csv not found in interim/. "
            "Run the validation + cleaning step first."
        )

    master = orders.copy()
    del orders
    gc.collect()

    # ── Join customers ────────────────────────────────────────
    customers = _load(interim_dir, "customers.csv")
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

    # ── Aggregate order_items → join → free raw table ────────
    order_items = _load(interim_dir, "order_items.csv")
    if order_items is not None:
        oi_agg = _agg_order_items(order_items)
        master = _safe_merge(master, oi_agg, on="order_id", label="order_items (aggregated)")
        del oi_agg
        gc.collect()

        # ── Map primary product per order (while order_items is still loaded)
        if "product_id" in order_items.columns:
            primary_product = _primary_product_per_order(order_items)
        else:
            primary_product = None

        del order_items
        gc.collect()

        # ── Join products via primary_product_id ──────────────
        products = _load(interim_dir, "products.csv")
        if products is not None and primary_product is not None:
            master = master.merge(primary_product, on="order_id", how="left")
            del primary_product
            gc.collect()

            products_renamed = products.rename(
                columns={"product_id": "primary_product_id"}
            )
            del products
            gc.collect()

            master = _safe_merge(
                master, products_renamed,
                on="primary_product_id", label="products"
            )
            del products_renamed
            gc.collect()
        else:
            del primary_product, products
            gc.collect()

    # ── Aggregate payments → join → free ─────────────────────
    payments = _load(interim_dir, "payments.csv")
    if payments is not None:
        pay_agg = payments.groupby("order_id").agg(
            total_payment =("payment_value", "sum"),
            payment_method=("payment_method", "first"),
            installments  =("installments",  "max"),
        ).reset_index()
        del payments
        gc.collect()

        master = _safe_merge(master, pay_agg, on="order_id", label="payments (aggregated)")
        del pay_agg
        gc.collect()

    # ── Join shipments → free ─────────────────────────────────
    shipments = _load(interim_dir, "shipments.csv")
    master = _safe_merge(master, shipments, on="order_id", label="shipments")
    del shipments
    gc.collect()

    # ── Aggregate reviews → join → free ──────────────────────
    reviews = _load(interim_dir, "reviews.csv")
    if reviews is not None:
        rev_agg = reviews.groupby("order_id").agg(
            avg_rating  =("rating", "mean"),
            review_count=("rating", "count"),
        ).reset_index()
        del reviews
        gc.collect()

        master = _safe_merge(master, rev_agg, on="order_id", label="reviews (aggregated)")
        del rev_agg
        gc.collect()

    # ── Aggregate returns → join → free ──────────────────────
    returns = _load(interim_dir, "returns.csv")
    if returns is not None:
        ret_agg = returns.groupby("order_id").agg(
            total_return_qty   =("return_quantity", "sum"),
            total_refund_amount=("refund_amount",   "sum"),
        ).reset_index()
        del returns
        gc.collect()

        master = _safe_merge(master, ret_agg, on="order_id", label="returns (aggregated)")
        del ret_agg
        gc.collect()

    # ── Join promotions → free ────────────────────────────────
    promotions = _load(interim_dir, "promotions.csv")
    if promotions is not None and "promo_code" in master.columns:
        master = _safe_merge(master, promotions, on="promo_code", label="promotions")
    del promotions
    gc.collect()

    # ── Aggregate inventory → join → free ─────────────────────
    inventory = _load(interim_dir, "inventory.csv")
    if inventory is not None and "primary_product_id" in master.columns:
        inv_agg = _agg_inventory(inventory)
        del inventory
        gc.collect()

        inv_agg = inv_agg.rename(columns={"product_id": "primary_product_id"})
        master = _safe_merge(
            master, inv_agg,
            on="primary_product_id", label="inventory (latest snapshot)"
        )
        del inv_agg
        gc.collect()
    elif inventory is not None:
        del inventory
        gc.collect()

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
