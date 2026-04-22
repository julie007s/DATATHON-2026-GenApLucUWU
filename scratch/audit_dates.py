import pandas as pd
from pathlib import Path

def audit_dates():
    master_path = Path("data/output/master_table.csv")
    if not master_path.exists():
        print("Master table not found.")
        return

    df = pd.read_csv(master_path, low_memory=False)
    
    # Coerce to datetime
    date_cols = ["order_date", "delivery_date", "signup_date", "ship_date"]
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    print("--- TEMPORAL AUDIT RESULTS ---")
    
    if "delivery_date" in df.columns:
        err_delivery = (df["delivery_date"] < df["order_date"]).sum()
        print(f"1. Delivery before Order: {err_delivery:,} rows (Violation!)")

    if "signup_date" in df.columns:
        err_signup = (df["order_date"] < df["signup_date"]).sum()
        print(f"2. Order before Signup:   {err_signup:,} rows (Inconsistency!)")

    if "ship_date" in df.columns:
        err_ship = (df["ship_date"] < df["order_date"]).sum()
        print(f"3. Ship before Order:     {err_ship:,} rows (Violation!)")

    # Check for extreme future dates (Look-ahead data corruption)
    now = pd.Timestamp.now()
    future_orders = (df["order_date"] > now).sum()
    print(f"4. Future Order Dates:    {future_orders:,} rows")

if __name__ == "__main__":
    audit_dates()
