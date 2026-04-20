import pandas as pd
import numpy as np
from pathlib import Path
from colorama import Fore, Style
from src.logger import logger

def run_featurization(
    master_table_path: Path, 
    raw_dir: Path,
    output_dir: Path, 
    verbose: bool = True
) -> pd.DataFrame:
    """
    Transforms the master table into a daily-aggregated feature set for revenue prediction.
    Strictly follows Datathon rules:
    1. Uses promo_id/promo_id_2 via 'has_promo' flag from merger.
    2. Calculates delivery_time from ship_date and delivery_date.
    3. Aggregates to Daily level to match sales.csv target.
    """
    if verbose:
        logger.info(f"  🚀 Starting Feature Engineering...")

    # 1. Load Master Table
    if not master_table_path.exists():
        raise FileNotFoundError(f"Master table not found at {master_table_path}")
    
    df = pd.read_csv(master_table_path, low_memory=False)
    
    # Ensure dates are datetime
    date_cols = ["order_date", "ship_date", "delivery_date"]
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # 2. Derive order-level features
    # Delivery time (in days)
    if "ship_date" in df.columns and "delivery_date" in df.columns:
        df["delivery_time"] = (df["delivery_date"] - df["ship_date"]).dt.days
        # Handle outliers or negative values if any
        df.loc[df["delivery_time"] < 0, "delivery_time"] = np.nan
    else:
        df["delivery_time"] = np.nan

    # 3. Aggregate to Daily Level
    df["Date"] = df["order_date"].dt.normalize()
    
    # Define aggregation logic
    agg_spec = {
        "order_id": "count",
        "has_promo": "sum",
        "delivery_time": "mean",
        "total_quantity": "sum",
        "total_item_revenue": "sum"
    }
    
    # Filter agg_spec to only columns that exist
    agg_spec = {k: v for k, v in agg_spec.items() if k in df.columns}
    
    daily_df = df.groupby("Date").agg(agg_spec).reset_index()
    
    # Rename columns for clarity
    daily_df = daily_df.rename(columns={
        "order_id": "daily_order_count",
        "has_promo": "daily_promo_order_count",
        "delivery_time": "avg_delivery_time",
        "total_quantity": "daily_total_quantity",
        "total_item_revenue": "daily_total_item_revenue"
    })

    # 4. Load Target (sales.csv)
    sales_path = raw_dir / "sales.csv"
    if sales_path.exists():
        sales_df = pd.read_csv(sales_path)
        sales_df["Date"] = pd.to_datetime(sales_df["Date"]).dt.normalize()
        
        # Merge features with target
        final_df = sales_df.merge(daily_df, on="Date", how="left")
        
        # Fill missing values for days with no orders
        fill_cols = [c for c in final_df.columns if c not in ["Date", "Revenue", "COGS"]]
        final_df[fill_cols] = final_df[fill_cols].fillna(0)
    else:
        logger.warning(f"  ⚠  sales.csv not found in {raw_dir}. Output will not include Revenue/COGS targets.")
        final_df = daily_df

    # 5. Add Temporal Features
    final_df["day_of_week"] = final_df["Date"].dt.dayofweek
    final_df["month"] = final_df["Date"].dt.month
    final_df["year"] = final_df["Date"].dt.year
    final_df["is_weekend"] = final_df["day_of_week"].isin([5, 6]).astype(int)

    # 6. Save Processed Features
    output_path = output_dir / "processed_features.csv"
    final_df.to_csv(output_path, index=False)
    
    if verbose:
        logger.info(f"  ✅ Feature Engineering complete!")
        logger.info(f"  📊 Processed features: {final_df.shape[0]} days × {final_df.shape[1]} columns")
        logger.info(f"  💾 Saved to: {output_path}")

    return final_df

if __name__ == "__main__":
    # For standalone testing
    project_root = Path(__file__).parent.parent
    run_featurization(
        project_root / "data/output/master_table.csv",
        project_root / "data/raw",
        project_root / "data/output"
    )
