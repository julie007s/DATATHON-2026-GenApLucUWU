Ran `pylanceRunCodeSnippet` 
Completed with input: {
  "codeSnippet": "\nimport csv\nimport os\n\npath = \"/home/hlt/Documents/DATATHON-HLT/data/output/master_table.csv\"\nprint(f\"File size: {os.path.getsize(path):,} bytes ({os.path.getsize(path)/1024/1024:.1f} MB)\")\n\nwith open(path, 'r', encoding='utf-8') as f:\n    reader = csv.DictReader(f)\n    headers = reader.fieldnames\n    rows = list(reader)\n\nprint(f\"Total rows: {len(rows):,}\")\nprint(f\"Total columns: {len(headers)}\")\nprint(f\"\\nColumns ({len(headers)}):\")\nfor i, h in enumerate(headers):\n    print(f\"  [{i:02d}] {h}\")\n",
  "workingDirectory": "/home/hlt/Documents/DATATHON-HLT",
  "workspaceRoot": "file:///home/hlt/Documents/DATATHON-HLT"
}

Ran `pylanceRunCodeSnippet` 
Completed with input: {
  "codeSnippet": "\nimport csv\nfrom collections import Counter\n\npath = \"/home/hlt/Documents/DATATHON-HLT/data/output/master_table.csv\"\nwith open(path, 'r', encoding='utf-8') as f:\n    reader = csv.DictReader(f)\n    headers = reader.fieldnames\n    rows = list(reader)\n\n# Fix BOM in first header\nclean_headers = [h.lstrip('\\ufeff') for h in headers]\norder_id_col = clean_headers[0]  # after BOM strip\n\nprint(\"=== 1. BOM / ENCODING ISSUE ===\")\nprint(f\"  First column raw name: {repr(headers[0])}\")\nprint(f\"  Has BOM prefix (\\\\ufeff): {headers[0].startswith('\\\\ufeff') or headers[0][0] == '\\\\ufeff'}\")\nprint(f\"  Actual char codes of first 3 chars: {[ord(c) for c in headers[0][:3]]}\")\n\nprint(\"\\n=== 2. NULL / EMPTY VALUE COUNTS ===\")\nnull_cols = {}\nfor col in headers:\n    null_count = sum(1 for r in rows if r[col] == '' or r[col] == 'nan' or r[col] is None)\n    if null_count > 0:\n        null_cols[col] = null_count\n\nfor col, cnt in sorted(null_cols.items(), key=lambda x: -x[1]):\n    pct = cnt / len(rows) * 100\n    print(f\"  {col:<35} {cnt:>10,}  ({pct:.1f}%)\")\n\nprint(f\"\\n  Columns with no nulls: {len(headers) - len(null_cols)}/{len(headers)}\")\n",
  "workingDirectory": "/home/hlt/Documents/DATATHON-HLT",
  "workspaceRoot": "file:///home/hlt/Documents/DATATHON-HLT"
}

Ran `pylanceRunCodeSnippet` 
Completed with input: {
  "codeSnippet": "\nimport csv\nfrom collections import Counter\n\npath = \"/home/hlt/Documents/DATATHON-HLT/data/output/master_table.csv\"\nwith open(path, 'r', encoding='utf-8') as f:\n    reader = csv.DictReader(f)\n    headers = reader.fieldnames\n    rows = list(reader)\n\n# ============================================================\n# 3. DUPLICATE order_id CHECK\n# ============================================================\nprint(\"=== 3. DUPLICATE order_id ===\")\norder_ids = [r[headers[0]] for r in rows]  # headers[0] has BOM\norder_id_counts = Counter(order_ids)\ndupes = {k: v for k, v in order_id_counts.items() if v > 1}\nprint(f\"  Total rows: {len(rows):,}\")\nprint(f\"  Unique order_ids: {len(order_id_counts):,}\")\nprint(f\"  Duplicate order_ids: {len(dupes):,}\")\nif dupes:\n    top5 = sorted(dupes.items(), key=lambda x: -x[1])[:5]\n    print(f\"  Top 5 dupes: {top5}\")\n\n# ============================================================\n# 4. WRONG JOIN: primary_product_id vs actual order_items\n# ============================================================\nprint(\"\\n=== 4. PRIMARY_PRODUCT_ID / PRODUCT JOIN LOGIC ===\")\nprint(\"  Sample primary_product_id values (first 5 rows):\")\nfor r in rows[:5]:\n    print(f\"    order_id={r[headers[0]].lstrip(chr(65279))} | primary_product_id={r['primary_product_id']} | \"\n          f\"distinct_products={r['distinct_products']} | total_quantity={r['total_quantity']}\")\n\n# How many orders have distinct_products > 1?\nmulti_product = sum(1 for r in rows if r['distinct_products'] != '' and int(float(r['distinct_products'])) > 1)\nprint(f\"\\n  Orders with distinct_products > 1: {multi_product:,} ({multi_product/len(rows)*100:.1f}%)\")\nprint(f\"  => product_name, category, segment, size, color, price, cogs\")\nprint(f\"     are from only ONE product per order — losing multi-product info\")\n\n# ============================================================\n# 5. GRANULARITY ISSUE: order-level vs item-level\n# ============================================================\nprint(\"\\n=== 5. GRANULARITY COLLAPSE ===\")\n# count how many orders have total_quantity != distinct_products\nmulti_qty = sum(1 for r in rows if r['total_quantity'] != '' and r['distinct_products'] != ''\n                and r['total_quantity'] != r['distinct_products'])\nprint(f\"  Orders where total_quantity != distinct_products: {multi_qty:,}\")\nprint(f\"  => Line-level item data collapsed to order-level aggregate\")\n\n# ============================================================\n# 6. PAYMENT METHOD DUPLICATION (payment_method vs payment_method_dim)\n# ============================================================\nprint(\"\\n=== 6. DUPLICATE COLUMN: payment_method vs payment_method_dim ===\")\nmismatches = sum(1 for r in rows if r['payment_method'] != r['payment_method_dim'])\nprint(f\"  Rows where payment_method != payment_method_dim: {mismatches:,}\")\nprint(f\"  => Redundant column — both carry identical data\")\n\n# ============================================================\n# 7. zip vs zip_dim\n# ============================================================\nprint(\"\\n=== 7. DUPLICATE COLUMN: zip vs zip_dim ===\")\nzip_mismatches = sum(1 for r in rows if r['zip'] != r['zip_dim'])\nprint(f\"  Rows where zip != zip_dim: {zip_mismatches:,}\")\nprint(f\"  => Redundant column\")\n",
  "workingDirectory": "/home/hlt/Documents/DATATHON-HLT",
  "workspaceRoot": "file:///home/hlt/Documents/DATATHON-HLT"
}

Ran `pylanceRunCodeSnippet` 
Completed with input: {
  "codeSnippet": "\nimport csv\nfrom collections import Counter\n\npath = \"/home/hlt/Documents/DATATHON-HLT/data/output/master_table.csv\"\nwith open(path, 'r', encoding='utf-8') as f:\n    reader = csv.DictReader(f)\n    headers = reader.fieldnames\n    rows = list(reader)\n\n# ============================================================\n# 8. MISSING DATA: shipments for non-cancelled orders\n# ============================================================\nprint(\"=== 8. MISSING SHIPMENT DATA FOR ELIGIBLE ORDERS ===\")\n# shipped/delivered/returned should have ship_date\nshould_have_ship = ['shipped', 'delivered', 'returned']\nfor status in should_have_ship:\n    total = sum(1 for r in rows if r['order_status'] == status)\n    missing_ship = sum(1 for r in rows if r['order_status'] == status and r['ship_date'] == '')\n    print(f\"  status={status:<12} total={total:>7,}  missing_ship_date={missing_ship:>7,} ({missing_ship/total*100:.1f}%)\")\n\n# ============================================================\n# 9. NULL NULLABILITY for returns — should be expected (not all orders returned)\n# ============================================================\nprint(\"\\n=== 9. NULL PATTERN LOGIC CHECK (returns & reviews) ===\")\n# For 'returned' orders - do they have return data?\nreturned_orders = [r for r in rows if r['order_status'] == 'returned']\nreturned_no_qty = sum(1 for r in returned_orders if r['total_return_qty'] == '')\nprint(f\"  'returned' orders without total_return_qty: {returned_no_qty}/{len(returned_orders)} ({returned_no_qty/len(returned_orders)*100:.1f}%)\")\n\n# For non-returned orders - do they have return data?\nnot_returned = [r for r in rows if r['order_status'] != 'returned']\nnot_ret_has_qty = sum(1 for r in not_returned if r['total_return_qty'] != '')\nprint(f\"  Non-returned orders WITH total_return_qty: {not_ret_has_qty}/{len(not_returned)}\")\n\n# reviews - only delivered should have reviews\ndelivered_orders = [r for r in rows if r['order_status'] == 'delivered']\ndelivered_with_review = sum(1 for r in delivered_orders if r['avg_rating'] != '')\nprint(f\"  'delivered' orders WITH avg_rating: {delivered_with_review}/{len(delivered_orders)} ({delivered_with_review/len(delivered_orders)*100:.1f}%)\")\n\nnon_delivered_with_review = sum(1 for r in rows if r['order_status'] != 'delivered' and r['avg_rating'] != '')\nprint(f\"  Non-delivered orders WITH avg_rating: {non_delivered_with_review}\")\n\n# ============================================================\n# 10. INVENTORY JOIN: stock data availability\n# ============================================================\nprint(\"\\n=== 10. INVENTORY DATA (stock_on_hand, fill_rate, sell_through_rate) ===\")\nhas_stock = sum(1 for r in rows if r['stock_on_hand'] != '')\nno_stock = sum(1 for r in rows if r['stock_on_hand'] == '')\nprint(f\"  Rows WITH stock_on_hand: {has_stock:,} ({has_stock/len(rows)*100:.1f}%)\")\nprint(f\"  Rows WITHOUT stock_on_hand: {no_stock:,} ({no_stock/len(rows)*100:.1f}%)\")\n\n# Check what's the join key — probably product_id + month/year of order?\n# show a sample row with stock\nsample_stock = [r for r in rows if r['stock_on_hand'] != ''][:3]\nfor r in sample_stock:\n    print(f\"  Sample with stock: order_date={r['order_date']} primary_product_id={r['primary_product_id']} \"\n          f\"stock_on_hand={r['stock_on_hand']}\")\nsample_no_stock = [r for r in rows if r['stock_on_hand'] == ''][:3]\nfor r in sample_no_stock:\n    print(f\"  Sample without stock: order_date={r['order_date']} primary_product_id={r['primary_product_id']} \"\n          f\"stock_on_hand=NULL\")\n",
  "workingDirectory": "/home/hlt/Documents/DATATHON-HLT",
  "workspaceRoot": "file:///home/hlt/Documents/DATATHON-HLT"
}

Ran `pylanceRunCodeSnippet` 
Completed with input: {
  "codeSnippet": "\nimport csv\nfrom collections import Counter\n\npath = \"/home/hlt/Documents/DATATHON-HLT/data/output/master_table.csv\"\nwith open(path, 'r', encoding='utf-8') as f:\n    reader = csv.DictReader(f)\n    headers = reader.fieldnames\n    rows = list(reader)\n\n# ============================================================\n# 11. MISSING COLUMNS — what's NOT included vs raw sources\n# ============================================================\nprint(\"=== 11. MISSING / ABSENT DATA FROM SOURCE TABLES ===\")\nprint(\"\"\"  From orders.csv: ALL columns present ✓\n  From customers.csv: zip (as zip_dim), city, signup_date, gender, age_group, acquisition_channel ✓\n  From geography.csv: MISSING region, district — critical for regional analysis!\n  From payments.csv: payment_value (total_payment) ✓, installments ✓, payment_method_dim (redundant)\n  From shipments.csv: ship_date ✓, delivery_date ✓, shipping_fee ✓\n  From returns.csv: aggregated to total_return_qty, total_refund_amount ✓\n  From reviews.csv: aggregated to avg_rating, review_count ✓\n  From inventory.csv: stock_on_hand ✓, fill_rate ✓, sell_through_rate ✓\n  From order_items.csv: total_quantity ✓, total_item_revenue ✓, distinct_products ✓, primary_product_id ✓\n  From promotions.csv: COMPLETELY MISSING — no promo_id, promo_type, discount info\n  From web_traffic.csv: COMPLETELY MISSING — no sessions, traffic_source, bounce_rate\n  From products.csv (via primary): product_name ✓, category ✓, segment ✓, size ✓, color ✓, price ✓, cogs ✓\n\"\"\")\n\n# ============================================================\n# 12. INVENTORY JOIN LOGIC CHECK — potential data leakage\n# ============================================================\nprint(\"=== 12. INVENTORY JOIN — POTENTIAL DATA LEAKAGE ===\")\n# inventory.snapshot_date = end of month. If joined on (product_id, year+month of order_date),\n# stock data at end of that month is FUTURE relative to the order date — this is leakage!\nprint(\"  inventory.csv uses snapshot_date = END of month (cuối tháng)\")\nprint(\"  If joined on order's year+month, the stock_on_hand at end-of-month\")\nprint(\"  is FUTURE data relative to orders that occurred within that month.\")\nprint(\"  => Potential data LEAKAGE for predictive modeling!\")\n\n# Verify by checking a sample\nraw_inv_path = \"/home/hlt/Documents/DATATHON-HLT/data/raw/inventory.csv\"\nwith open(raw_inv_path, 'r', encoding='utf-8') as f:\n    inv_rows = list(csv.DictReader(f))\nprint(f\"\\n  inventory snapshot_dates sample: {list({r['snapshot_date'] for r in inv_rows[:30]})[:5]}\")\nprint(f\"  All end-of-month? {all(r['snapshot_date'].endswith(('28','29','30','31')) for r in inv_rows)}\")\n\n# ============================================================\n# 13. TOTAL_ITEM_REVENUE vs TOTAL_PAYMENT discrepancy\n# ============================================================\nprint(\"\\n=== 13. total_item_revenue vs total_payment DISCREPANCY ===\")\ndiscrepancies = 0\nlarge_discrepancies = 0\nfor r in rows:\n    try:\n        item_rev = float(r['total_item_revenue'])\n        total_pay = float(r['total_payment'])\n        diff = abs(item_rev - total_pay)\n        if diff > 0.01:\n            discrepancies += 1\n        if diff > 1000:\n            large_discrepancies += 1\n    except:\n        pass\n\nprint(f\"  Rows where total_item_revenue != total_payment: {discrepancies:,} ({discrepancies/len(rows)*100:.1f}%)\")\nprint(f\"  Rows with diff > 1000: {large_discrepancies:,}\")\n# Sample discrepancy\nfor r in rows:\n    try:\n        diff = abs(float(r['total_item_revenue']) - float(r['total_payment']))\n        if diff > 1000:\n            print(f\"  Sample: order_id={r[headers[0]].lstrip(chr(65279))} item_rev={r['total_item_revenue']} total_pay={r['total_payment']} diff={diff:.2f}\")\n            break\n    except:\n        pass\n",
  "workingDirectory": "/home/hlt/Documents/DATATHON-HLT",
  "workspaceRoot": "file:///home/hlt/Documents/DATATHON-HLT"
}

Ran `pylanceRunCodeSnippet` 
Completed with input: {
  "codeSnippet": "\nimport csv\n\npath = \"/home/hlt/Documents/DATATHON-HLT/data/output/master_table.csv\"\nwith open(path, 'r', encoding='utf-8') as f:\n    reader = csv.DictReader(f)\n    headers = reader.fieldnames\n    rows = list(reader)\n\n# ============================================================\n# 14. SHIPMENT MISSING 0.1% — check which statuses have null ship\n# ============================================================\nprint(\"=== 14. DETAIL: SHIPMENT NULL BREAKDOWN BY ORDER STATUS ===\")\nfrom collections import Counter\nship_null_status = Counter(r['order_status'] for r in rows if r['ship_date'] == '')\nprint(f\"  Status breakdown for rows with null ship_date: {dict(ship_null_status)}\")\n# Should be only cancelled/paid/created that have null ship_date. If shipped/delivered/returned have nulls, that's a bug.\nexpected_null_ship = {'cancelled', 'paid', 'created'}\nunexpected = {k: v for k, v in ship_null_status.items() if k not in expected_null_ship}\nprint(f\"  UNEXPECTED null ship_date (statuses that should have shipment): {unexpected}\")\n\n# ============================================================\n# 15. RETURNED ORDERS WITHOUT RETURN DATA\n# ============================================================\nprint(\"\\n=== 15. RETURNED ORDERS WITHOUT RETURN QTY (should always have) ===\")\nret_orders_no_data = [(r[headers[0]].lstrip(chr(65279)), r['order_date']) \n                      for r in rows if r['order_status'] == 'returned' and r['total_return_qty'] == '']\nprint(f\"  Count: {len(ret_orders_no_data)}\")\nprint(f\"  Sample: {ret_orders_no_data[:5]}\")\n\n# ============================================================\n# 16. NUMERIC SANITY CHECKS\n# ============================================================\nprint(\"\\n=== 16. NUMERIC SANITY CHECKS ===\")\n\n# total_quantity should be >= distinct_products\ninvalid_qty = sum(1 for r in rows \n    if r['total_quantity'] != '' and r['distinct_products'] != ''\n    and int(float(r['total_quantity'])) < int(float(r['distinct_products'])))\nprint(f\"  total_quantity < distinct_products: {invalid_qty}\")\n\n# total_return_qty > total_quantity (can't return more than ordered)\ninvalid_return = 0\nfor r in rows:\n    try:\n        if float(r['total_return_qty']) > float(r['total_quantity']):\n            invalid_return += 1\n    except:\n        pass\nprint(f\"  total_return_qty > total_quantity: {invalid_return}\")\n\n# avg_rating outside [1,5]\ninvalid_rating = sum(1 for r in rows \n    if r['avg_rating'] != ''\n    and (float(r['avg_rating']) < 1 or float(r['avg_rating']) > 5))\nprint(f\"  avg_rating outside [1,5]: {invalid_rating}\")\n\n# shipping_fee < 0\ninvalid_fee = sum(1 for r in rows if r['shipping_fee'] != '' and float(r['shipping_fee']) < 0)\nprint(f\"  shipping_fee < 0: {invalid_fee}\")\n\n# stock_on_hand < 0\ninvalid_stock = sum(1 for r in rows if r['stock_on_hand'] != '' and float(r['stock_on_hand']) < 0)\nprint(f\"  stock_on_hand < 0: {invalid_stock}\")\n\n# ============================================================\n# 17. PRIMARY PRODUCT ID SELECTION METHOD\n# ============================================================\nprint(\"\\n=== 17. HOW IS primary_product_id CHOSEN? ===\")\n# Load order_items to compare\nraw_oi_path = \"/home/hlt/Documents/DATATHON-HLT/data/raw/order_items.csv\"\nwith open(raw_oi_path, 'r', encoding='utf-8') as f:\n    oi_rows = list(csv.DictReader(f))\n\nfrom collections import defaultdict\noi_by_order = defaultdict(list)\nfor r in oi_rows:\n    oi_by_order[r['order_id']].append(r)\n\n# Check first 5 multi-product orders: is primary = min(product_id)? max qty? first?\nchecked = 0\nmethods = Counter()\nfor r in rows:\n    oid = r[headers[0]].lstrip(chr(65279))\n    if oid in oi_by_order and len(oi_by_order[oid]) > 1 and checked < 200:\n        items = oi_by_order[oid]\n        primary = r['primary_product_id']\n        # check different hypotheses\n        min_pid = min(items, key=lambda x: int(x['product_id']))['product_id']\n        max_qty = max(items, key=lambda x: int(x['quantity']))['product_id']\n        first_pid = items[0]['product_id']\n        max_price = max(items, key=lambda x: float(x['unit_price']))['product_id']\n        \n        if primary == min_pid:\n            methods['min_product_id'] += 1\n        elif primary == max_qty:\n            methods['max_quantity'] += 1\n        elif primary == first_pid:\n            methods['first_item'] += 1\n        elif primary == max_price:\n            methods['max_price'] += 1\n        else:\n            methods['other'] += 1\n        checked += 1\n\nprint(f\"  Selection method hypothesis (for {checked} multi-product orders):\")\nfor method, cnt in methods.most_common():\n    print(f\"    {method}: {cnt} ({cnt/checked*100:.0f}%)\")\n",
  "workingDirectory": "/home/hlt/Documents/DATATHON-HLT",
  "workspaceRoot": "file:///home/hlt/Documents/DATATHON-HLT"
}

Đây là toàn bộ các vấn đề tìm được:

---

## Vấn đề 1 — BOM (Byte Order Mark) trong header

Cột đầu tiên tên là `\ufefforder_id` (char code 65279 trước chữ `o`). Bất kỳ code nào dùng `row['order_id']` sẽ **không tìm thấy cột** — phải dùng `row['\ufefforder_id']`. Nguyên nhân: file được lưu dạng UTF-8 with BOM.

---

## Vấn đề 2 — 2 cột bị bỏ sót hoàn toàn từ `geography.csv`

Bảng `geography.csv` có 4 cột: `zip`, `city`, `region`, `district`. Master table chỉ có `city`. **`region` và `district` bị thiếu hoàn toàn.** `region` là cột cực kỳ quan trọng — Q7 đề thi hỏi trực tiếp về nó, và là feature tiềm năng cho forecasting theo vùng địa lý.

---

## Vấn đề 3 — 2 bảng nguồn bị bỏ qua hoàn toàn

- **`promotions.csv`** (50 campaigns): không có bất kỳ cột nào — mất hết thông tin về `promo_id`, `promo_type`, `discount_value`, `promo_channel`, tính mùa vụ của khuyến mãi.
- **`web_traffic.csv`** (3,652 dòng): không có bất kỳ cột nào — mất `sessions`, `unique_visitors`, `bounce_rate`, `traffic_source`. Đây là **leading indicator** quan trọng cho sales forecasting.

---

## Vấn đề 4 — 2 cột trùng lặp vô nghĩa (redundant)

| Cặp | Mismatch |
|-----|---------|
| `zip` vs `zip_dim` | **0/646,945** — giống nhau 100% |
| `payment_method` vs `payment_method_dim` | **0/646,945** — giống nhau 100% |

Cả hai cặp đều copy y nguyên, không thêm thông tin gì mới, làm nặng file thêm.

---

## Vấn đề 5 — Mất thông tin đơn hàng nhiều sản phẩm (10.3% tổng orders)

**66,442 orders** có `distinct_products > 1` (nhiều sản phẩm khác nhau), nhưng các cột `product_name`, `category`, `segment`, `size`, `color`, `price`, `cogs` chỉ lấy từ **1 sản phẩm duy nhất** (`primary_product_id`). Cách chọn `primary_product_id` = `min(product_id)` — tức là sản phẩm có ID nhỏ nhất, **không có ý nghĩa kinh doanh** gì (không phải sản phẩm bán nhiều nhất, cũng không phải đắt nhất).

---

## Vấn đề 6 — Dữ liệu shipment bị null sai logic (564 dòng bị hỏng)

Theo đặc tả, `ship_date`/`delivery_date`/`shipping_fee` **phải có** cho orders có status `shipped`, `delivered`, `returned`. Thực tế:

| Status | Null ship_date |
|--------|---------------|
| `delivered` | **524 dòng** |
| `returned` | **29 dòng** |
| `shipped` | **11 dòng** |

→ 564 rows bị thiếu shipment data dù lẽ ra phải có — **lỗi join**.

---

## Vấn đề 7 — 80 đơn hàng `returned` không có dữ liệu trả hàng

80 orders có `order_status = 'returned'` nhưng `total_return_qty` và `total_refund_amount` đều null. Tất cả tập trung ở cuối tháng 12/2022 (gần edge của tập train), có thể do **return records chưa được tạo kịp** hoặc **lỗi join**.

---

## Vấn đề 8 — Potential Data Leakage từ inventory

`inventory.csv` lưu `snapshot_date` = **cuối tháng** (31/10, 30/11...). Master table join inventory theo `(product_id, year+month của order_date)`, tức là đơn hàng ngày 1/10 sẽ nhận `stock_on_hand` của ngày 31/10. Đây là **dữ liệu tương lai** so với thời điểm đặt hàng → **data leakage** nếu dùng để build predictive model.

---

## Vấn đề 9 — `total_item_revenue` ≡ `total_payment` (100% giống nhau)

0 dòng có sự khác biệt giữa `total_item_revenue` và `total_payment`. Theo logic, `total_payment` nên = `total_item_revenue` + `shipping_fee` - `refund`. Việc chúng bằng nhau có thể là: (a) shipping_fee đã bị tính vào item revenue, hoặc (b) đây là cùng một phép tính được đặt 2 tên khác nhau. Cần làm rõ logic tính toán.

---

## Tóm tắt mức độ nghiêm trọng

| # | Vấn đề | Mức độ |
|---|--------|--------|
| 1 | BOM trong header | 🔴 Nghiêm trọng — gây lỗi code |
| 2 | Thiếu `region`, `district` | 🔴 Nghiêm trọng — mất feature địa lý |
| 3 | Thiếu toàn bộ `promotions` và `web_traffic` | 🔴 Nghiêm trọng — mất 2 bảng nguồn |
| 5 | Mất thông tin multi-product (10.3% orders) | 🟠 Cao |
| 8 | Data leakage từ inventory | 🟠 Cao — ảnh hưởng model |
| 6 | 564 rows shipment null sai logic | 🟡 Trung bình |
| 7 | 80 rows returned không có return data | 🟡 Trung bình |
| 9 | `total_item_revenue` = `total_payment` bất thường | 🟡 Cần xác minh |
| 4 | 2 cặp cột trùng lặp | 🟢 Nhẹ — lãng phí bộ nhớ |