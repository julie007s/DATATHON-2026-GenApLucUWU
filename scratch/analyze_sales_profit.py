import pandas as pd

# Load data
order_items = pd.read_csv('data/raw/order_items.csv', low_memory=False)
products = pd.read_csv('data/raw/products.csv')

# Merge
df = order_items.merge(products[['product_id', 'cogs']], on='product_id', how='left')

# Calculate Revenue and Profit
# Revenue = (unit_price * quantity) - discount_amount
# Profit = Revenue - (cogs * quantity)
df['revenue'] = (df['unit_price'] * df['quantity']) - df['discount_amount']
df['cost'] = df['cogs'] * df['quantity']
df['profit'] = df['revenue'] - df['cost']

# Check rows where profit is negative
neg_profit = df[df['profit'] < 0]

print(f"Total rows: {len(df):,}")
print(f"Rows with negative profit: {len(neg_profit):,} ({len(neg_profit)/len(df)*100:.2f}%)")

if len(neg_profit) > 0:
    print("\nSample of negative profit rows:")
    print(neg_profit[['order_id', 'product_id', 'quantity', 'unit_price', 'discount_amount', 'cogs', 'profit']].head(10))
    
    # Check if they have promo_id
    promo_neg = neg_profit['promo_id'].notna().sum()
    print(f"\nNegative profit rows with promo_id: {promo_neg:,} ({promo_neg/len(neg_profit)*100:.2f}%)")
    
    # Check if they have promo_id_2
    promo2_neg = neg_profit['promo_id_2'].notna().sum()
    print(f"Negative profit rows with promo_id_2: {promo2_neg:,} ({promo2_neg/len(neg_profit)*100:.2f}%)")

# Aggregate by promo_id
promo_stats = df.groupby('promo_id').agg(
    total_rows=('order_id', 'count'),
    neg_profit_rows=('profit', lambda x: (x < 0).sum()),
    avg_profit=('profit', 'mean'),
    min_profit=('profit', 'min')
).reset_index()

promo_stats['neg_pct'] = (promo_stats['neg_profit_rows'] / promo_stats['total_rows']) * 100
print("\nPromo stats (Top 10 by negative percentage):")
print(promo_stats.sort_values('neg_pct', ascending=False).head(10))
