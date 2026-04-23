Read [](file:///home/hlt/Documents/DATATHON-HLT/src/merger.py#1-1), lines 1 to 100

Read [](file:///home/hlt/Documents/DATATHON-HLT/src/cleaner.py#1-1), lines 1 to 100

Read [](file:///home/hlt/Documents/DATATHON-HLT/src/validator.py#1-1), lines 1 to 100

Read [](file:///home/hlt/Documents/DATATHON-HLT/src/reporter.py#1-1), lines 1 to 80

Read [](file:///home/hlt/Documents/DATATHON-HLT/src/merger.py#100-100), lines 100 to 300

Read [](file:///home/hlt/Documents/DATATHON-HLT/src/cleaner.py#100-100), lines 100 to 200

Read [](file:///home/hlt/Documents/DATATHON-HLT/src/merger.py#300-300), lines 300 to 423

Đã đọc đủ toàn bộ code. Đây là các nguyên nhân gốc rễ:

---

## Nguyên nhân 1 — BOM trong header (cleaner.py + merger.py)

**File:** cleaner.py dòng `clean_and_save()` và merger.py cuối hàm `merge_tables()`

```python
# cleaner.py
df_clean.to_csv(out_path, index=False, encoding="utf-8-sig")   # ← utf-8-sig thêm BOM

# merger.py
master.to_csv(save_path, index=False, encoding="utf-8-sig")    # ← utf-8-sig thêm BOM
```

`utf-8-sig` ghi thêm byte `\xEF\xBB\xBF` (BOM) vào đầu file. Kết quả: cột đầu tiên trong CSV là `\ufefforder_id` thay vì `order_id`. Nên dùng `encoding="utf-8"`.

---

## Nguyên nhân 2 — Geography join bị skip hoàn toàn (merger.py)

```python
# merger.py ~dòng 265
if geography is not None and all(c in master.columns for c in ["city", "province"]):
    master = _safe_merge(master, geography, on=["city", "province"], label="geography")
```

Hai lỗi chồng nhau:
- **`province` không tồn tại** trong `geography.csv` (schema thực tế có `region` và `district`), nên điều kiện `all(...)` luôn `False` → toàn bộ khối `if` bị bỏ qua.
- Ngay cả khi sửa điều kiện, join key đúng phải là **`zip`** (FK trong đề thi), không phải `city` + `province`.

Hệ quả: `region` và `district` không bao giờ được đưa vào master table.

---

## Nguyên nhân 3 — Promotions join bị skip hoàn toàn (merger.py)

```python
# merger.py ~dòng 390
if promotions is not None and "promo_code" in master.columns:
    master = _safe_merge(master, promotions, on="promo_code", label="promotions")
```

`master` không bao giờ có cột `promo_code` — không tồn tại trong bất kỳ bảng nào. Cột FK thực tế là `promo_id` nằm trong `order_items`. Hơn nữa, `_agg_order_items()` đã aggregate order_items và **không giữ lại** `promo_id`/`promo_id_2`. Kết quả: điều kiện luôn `False`, promotions không được join.

---

## Nguyên nhân 4 — Web traffic không được join (merger.py)

Mặc dù `web_traffic.csv` được liệt kê trong `CSV_FILES` của pipeline.py và được clean/lưu vào `interim/`, trong toàn bộ hàm `merge_tables()` **không có một dòng code nào** load hoặc join `web_traffic`. Bảng này đơn giản bị quên.

---

## Nguyên nhân 5 — 2 cột trùng lặp (`_safe_merge` + join logic)

```python
# merger.py, _safe_merge()
def _safe_merge(..., suffixes: tuple[str, str] = ("", "_dim")):
```

Khi join `customers` vào `orders`, cả hai đều có cột `zip` → tạo ra `zip` (từ orders) và `zip_dim` (từ customers). Tương tự, `payment_method` xuất hiện trong cả `orders` và bảng aggregate `payments` → tạo `payment_method` và `payment_method_dim`. Suffix `_dim` được dùng máy móc mà không loại bỏ các cột trùng trước khi merge.

---

## Nguyên nhân 6 — `primary_product_id` chọn sai logic (merger.py)

```python
# merger.py, _primary_product_per_order()
.agg(lambda s: s.mode().iat[0] if len(s) > 0 else pd.NA)
```

`s.mode()` trả về các giá trị xuất hiện nhiều nhất, **sắp xếp tăng dần**. Khi mỗi sản phẩm xuất hiện đúng 1 lần trong đơn (trường hợp đa số), tất cả đều là mode → `.iat[0]` = **`min(product_id)`** — sản phẩm có ID nhỏ nhất, không có ý nghĩa kinh doanh. Nên chọn theo `max(quantity)` (sản phẩm bán nhiều nhất) hoặc `max(unit_price * quantity)` (doanh thu cao nhất).

---

## Nguyên nhân 7 — Inventory join gây data leakage (merger.py, `_agg_inventory`)

```python
# merger.py, _agg_inventory()
inv = (
    inv.sort_values(date_col)
       .groupby("product_id", sort=False)
       .last()   # ← lấy snapshot MỚI NHẤT = 2022-12-31 cho MỌI đơn hàng
       .reset_index()
)
```

Hàm chỉ giữ **1 snapshot duy nhất** (mới nhất) cho mỗi `product_id`, rồi join với tất cả orders bất kể `order_date`. Đơn hàng năm 2012 sẽ nhận `stock_on_hand` của tháng 12/2022 — đây là **dữ liệu tương lai**. Join đúng phải theo `(product_id, year, month)` để lấy snapshot của đúng tháng order xảy ra.

---

## Tóm tắt nguyên nhân ↔ vấn đề

| Vấn đề trong master_table | File | Nguyên nhân cụ thể |
|---|---|---|
| BOM `\ufeff` trong header | cleaner.py, merger.py | `encoding="utf-8-sig"` thay vì `"utf-8"` |
| Thiếu `region`, `district` | merger.py | Điều kiện check sai (`"province"` không tồn tại) + sai join key |
| Thiếu toàn bộ promotions | merger.py | Check `"promo_code"` không tồn tại thay vì `"promo_id"` |
| Thiếu toàn bộ web_traffic | merger.py | Không có code join web_traffic |
| Cột `zip_dim`, `payment_method_dim` trùng | merger.py | Suffix `_dim` áp dụng máy móc, không dedup trước |
| `primary_product_id` = min, không có nghĩa | merger.py | `mode().iat[0]` = min khi không có tie |
| Inventory leakage (2022 data cho 2012 orders) | merger.py | `_agg_inventory` chỉ lấy latest snapshot thay vì match theo tháng |