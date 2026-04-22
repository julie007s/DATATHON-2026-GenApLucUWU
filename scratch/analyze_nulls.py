import pandas as pd
import sys
import io
from pathlib import Path

# Fix encoding for Windows terminal
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

def analyze_nulls(file_path):
    print(f"Loading {file_path}...")
    df = pd.read_csv(file_path, low_memory=False)
    total_rows = len(df)
    
    null_stats = []
    for col in df.columns:
        null_count = df[col].isnull().sum()
        null_pct = (null_count / total_rows) * 100
        null_stats.append({
            "Column": col,
            "Null Count": null_count,
            "Null %": round(null_pct, 2)
        })
    
    stats_df = pd.DataFrame(null_stats).sort_values("Null %", ascending=False)
    
    print("\n--- NULL VALUE ANALYSIS REPORT ---")
    print(f"Total Rows: {total_rows:,}")
    print(stats_df.to_string(index=False))
    
    # Analyze by groups
    groups = {
        "Returns": ["total_return_qty", "total_refund_amount", "return_reason"],
        "Reviews": ["avg_rating", "review_count"],
        "Promotions": ["promo_type", "discount_value", "promo_channel", "min_order_value"],
        "Shipments": ["ship_date", "delivery_date", "shipping_fee"],
        "Geography": ["city", "province", "region", "district"]
    }
    
    print("\n--- INSIGHTS BY DATA GROUP ---")
    for group_name, cols in groups.items():
        existing_cols = [c for c in cols if c in df.columns]
        if existing_cols:
            avg_null = stats_df[stats_df["Column"].isin(existing_cols)]["Null %"].mean()
            print(f"- {group_name}: Average {avg_null:.2f}% nulls. (Expected: only a subset of orders have these events)")

if __name__ == "__main__":
    master_path = Path("data/output/master_table.csv")
    if master_path.exists():
        analyze_nulls(master_path)
    else:
        print(f"File not found: {master_path}")
