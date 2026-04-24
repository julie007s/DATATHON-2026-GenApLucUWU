# Schema Dữ liệu — DATATHON 2026

> Tài liệu này được tổng hợp từ việc trích xuất trực tiếp cấu trúc các file CSV trong `data/raw/` và đối chiếu với đề thi (`DeThi.md`). Mọi thông tin về số lượng dòng, kiểu dữ liệu thực tế, giá trị nullable và danh sách giá trị categorical đều dựa trên dữ liệu thực.

---

## Tổng quan

| File | Lớp | Số dòng | Mô tả |
|------|-----|--------:|-------|
| `products.csv` | Master | 2,412 | Danh mục sản phẩm |
| `customers.csv` | Master | 121,930 | Thông tin khách hàng |
| `promotions.csv` | Master | 50 | Các chiến dịch khuyến mãi |
| `geography.csv` | Master | 39,948 | Danh sách mã bưu chính các vùng |
| `orders.csv` | Transaction | 646,945 | Thông tin đơn hàng |
| `order_items.csv` | Transaction | 714,669 | Chi tiết từng dòng sản phẩm trong đơn |
| `payments.csv` | Transaction | 646,945 | Thanh toán (quan hệ 1:1 với orders) |
| `shipments.csv` | Transaction | 566,067 | Thông tin vận chuyển |
| `returns.csv` | Transaction | 39,939 | Sản phẩm bị trả lại |
| `reviews.csv` | Transaction | 113,551 | Đánh giá sản phẩm |
| `sales.csv` | Analytical | 3,833 | Doanh thu huấn luyện |
| `sample_submission.csv` | Analytical | 548 | Mẫu file nộp bài |
| `inventory.csv` | Operational | 60,247 | Ảnh chụp tồn kho cuối tháng |
| `web_traffic.csv` | Operational | 3,652 | Lưu lượng truy cập website hàng ngày |

---

## Phạm vi thời gian

| File | Cột ngày | Từ | Đến |
|------|----------|----|-----|
| `orders.csv` | `order_date` | 2012-07-04 | 2022-12-31 |
| `sales.csv` | `Date` | 2012-07-04 | 2022-12-31 |
| `sample_submission.csv` | `Date` | 2023-01-01 | 2024-07-01 |
| `web_traffic.csv` | `date` | 2013-01-01 | 2022-12-31 |
| `inventory.csv` | `snapshot_date` | 2012-07-31 | 2022-12-31 |
| `shipments.csv` | `ship_date` | 2012-07-04 | 2022-12-29 |
| `returns.csv` | `return_date` | 2012-07-11 | 2022-12-31 |
| `reviews.csv` | `review_date` | 2012-07-10 | 2022-12-31 |
| `promotions.csv` | `start_date` | 2013-01-31 | 2022-11-18 |

---

## Bảng Master

### `products.csv` — Danh mục sản phẩm

**2,412 dòng** — 1 dòng / sản phẩm

| Cột | Kiểu thực tế | Nullable | Ghi chú |
|-----|-------------|----------|---------|
| `product_id` | int | Không | Khoá chính |
| `product_name` | str | Không | Tên sản phẩm |
| `category` | str | Không | Xem giá trị bên dưới |
| `segment` | str | Không | Xem giá trị bên dưới |
| `size` | str | Không | S / M / L / XL (mỗi loại ~603) |
| `color` | str | Không | Nhãn màu sản phẩm |
| `price` | float | Không | Giá bán lẻ; range [9.06, 40,950.00] |
| `cogs` | float | Không | Giá vốn; range [5.18, 38,902.50] |

**Ràng buộc đã kiểm chứng:** `cogs < price` — 0 vi phạm.

**Giá trị `category` (4 loại):**
| Giá trị | Số sản phẩm |
|---------|------------:|
| `Streetwear` | 1,320 |
| `Outdoor` | 743 |
| `Casual` | 201 |
| `GenZ` | 148 |

**Giá trị `segment` (8 loại):**
| Giá trị | Số sản phẩm |
|---------|------------:|
| `Activewear` | 598 |
| `Everyday` | 405 |
| `Performance` | 347 |
| `Balanced` | 306 |
| `Standard` | 262 |
| `Premium` | 177 |
| `All-weather` | 169 |
| `Trendy` | 148 |

> ⚠️ **Khác biệt so với đề thi:** Đề thi Q2 chỉ đề cập 4 segment (Premium, Performance, Activewear, Standard), nhưng thực tế có 8 segment.

---

### `customers.csv` — Khách hàng

**121,930 dòng** — 1 dòng / khách hàng

| Cột | Kiểu thực tế | Nullable | Ghi chú |
|-----|-------------|----------|---------|
| `customer_id` | int | Không | Khoá chính |
| `zip` | int | Không | FK → `geography.zip` (0 vi phạm FK) |
| `city` | str | Không | Tên thành phố |
| `signup_date` | date (str) | Không | Ngày đăng ký tài khoản |
| `gender` | str | **Không** | Female / Male / Non-binary |
| `age_group` | str | **Không** | 5 nhóm tuổi |
| `acquisition_channel` | str | **Không** | 6 kênh tiếp thị |

> ⚠️ **Khác biệt so với đề thi:** Đề thi mô tả `gender`, `age_group`, `acquisition_channel` là nullable. Tuy nhiên dữ liệu thực tế **không có giá trị null** ở cả 3 cột này.

**Giá trị `gender`:**
| Giá trị | Số khách |
|---------|--------:|
| `Female` | 59,640 |
| `Male` | 57,457 |
| `Non-binary` | 4,833 |

**Giá trị `age_group`:**
| Giá trị | Số khách |
|---------|--------:|
| `25-34` | 36,342 |
| `35-44` | 31,920 |
| `45-54` | 23,172 |
| `18-24` | 17,039 |
| `55+` | 13,457 |

**Giá trị `acquisition_channel`:**
| Giá trị | Số khách |
|---------|--------:|
| `organic_search` | 36,450 |
| `social_media` | 24,448 |
| `paid_search` | 24,285 |
| `email_campaign` | 14,674 |
| `referral` | 12,270 |
| `direct` | 9,803 |

---

### `promotions.csv` — Chương trình khuyến mãi

**50 dòng** — 1 dòng / chiến dịch

| Cột | Kiểu thực tế | Nullable | Ghi chú |
|-----|-------------|----------|---------|
| `promo_id` | str | Không | Khoá chính; format `PROMO-XXXX` |
| `promo_name` | str | Không | Tên chiến dịch kèm năm |
| `promo_type` | str | Không | `percentage` (45) / `fixed` (5) |
| `discount_value` | float | Không | Giá trị giảm |
| `start_date` | date (str) | Không | Ngày bắt đầu chiến dịch |
| `end_date` | date (str) | Không | Ngày kết thúc chiến dịch |
| `applicable_category` | str | **Có** | 40/50 dòng là null; 5 = `Streetwear`, 5 = `Outdoor` |
| `promo_channel` | str | Không | Kênh phân phối |
| `stackable_flag` | int | Không | 0 hoặc 1 |
| `min_order_value` | int | Không | Giá trị đơn tối thiểu; `0` = không yêu cầu |

> ⚠️ **Khác biệt so với đề thi:** Đề thi mô tả `min_order_value` là float và nullable. Thực tế kiểu là int và **không có null** — giá trị `0` đóng vai trò "không yêu cầu" (31 dòng = 0).

**Công thức giảm giá:**
- `percentage`: `discount_amount = quantity × unit_price × (discount_value / 100)`
- `fixed`: `discount_amount = quantity × discount_value`

**Giá trị `promo_channel`:**
`all_channels` (19), `online` (13), `email` (7), `social_media` (6), `in_store` (5)

**Giá trị `min_order_value`:**
`0` (31), `150,000` (8), `100,000` (5), `50,000` (4), `200,000` (2)

---

### `geography.csv` — Địa lý

**39,948 dòng** — 1 dòng / mã bưu chính

| Cột | Kiểu thực tế | Nullable | Ghi chú |
|-----|-------------|----------|---------|
| `zip` | int | Không | Khoá chính (mã bưu chính) |
| `city` | str | Không | Tên thành phố |
| `region` | str | Không | `East` / `Central` / `West` |
| `district` | str | Không | Tên quận/huyện |

**Giá trị `region`:**
| Giá trị | Số bản ghi |
|---------|----------:|
| `East` | 18,929 |
| `Central` | 14,512 |
| `West` | 6,507 |

---

## Bảng Transaction

### `orders.csv` — Đơn hàng

**646,945 dòng** — 1 dòng / đơn hàng

| Cột | Kiểu thực tế | Nullable | Ghi chú |
|-----|-------------|----------|---------|
| `order_id` | int | Không | Khoá chính |
| `order_date` | date (str) | Không | 2012-07-04 → 2022-12-31 |
| `customer_id` | int | Không | FK → `customers.customer_id` |
| `zip` | int | Không | FK → `geography.zip` (0 vi phạm FK) |
| `order_status` | str | Không | Xem giá trị bên dưới |
| `payment_method` | str | Không | Xem giá trị bên dưới |
| `device_type` | str | Không | `mobile` / `desktop` / `tablet` |
| `order_source` | str | Không | Xem giá trị bên dưới |

**Giá trị `order_status`:**
| Giá trị | Số đơn |
|---------|-------:|
| `delivered` | 516,716 |
| `cancelled` | 59,462 |
| `returned` | 36,142 |
| `shipped` | 13,773 |
| `paid` | 13,577 |
| `created` | 7,275 |

**Giá trị `payment_method`:**
| Giá trị | Số đơn |
|---------|-------:|
| `credit_card` | 356,352 |
| `paypal` | 97,018 |
| `cod` | 96,681 |
| `apple_pay` | 64,763 |
| `bank_transfer` | 32,131 |

**Giá trị `order_source`:**
`organic_search` (181,495), `paid_search` (141,652), `social_media` (129,710), `email_campaign` (77,572), `referral` (64,565), `direct` (51,951)

---

### `order_items.csv` — Chi tiết đơn hàng

**714,669 dòng** — nhiều dòng / đơn hàng (tất cả 646,945 orders đều có ít nhất 1 item)

| Cột | Kiểu thực tế | Nullable | Ghi chú |
|-----|-------------|----------|---------|
| `order_id` | int | Không | FK → `orders.order_id` |
| `product_id` | int | Không | FK → `products.product_id` (0 vi phạm FK) |
| `quantity` | int | Không | Số lượng đặt mua |
| `unit_price` | float | Không | Đơn giá sau khuyến mãi |
| `discount_amount` | float | Không | Tổng tiền giảm |
| `promo_id` | str | **Có** | 276,316 non-null (38.7%); FK → `promotions.promo_id` |
| `promo_id_2` | str | **Có** | 206 non-null (0.03%); khuyến mãi thứ hai |

> ✅ **Xác nhận Q5:** 38.7% dòng có `promo_id` non-null → đáp án đúng là **C) 39%**.

---

### `payments.csv` — Thanh toán

**646,945 dòng** — quan hệ 1:1 với `orders` (đã kiểm chứng: tập `order_id` khớp hoàn toàn)

| Cột | Kiểu thực tế | Nullable | Ghi chú |
|-----|-------------|----------|---------|
| `order_id` | int | Không | FK → `orders.order_id` (quan hệ 1:1 đã xác nhận) |
| `payment_method` | str | Không | Khớp hoàn toàn với `orders.payment_method` |
| `payment_value` | float | Không | Tổng giá trị thanh toán |
| `installments` | int | Không | Số kỳ trả góp |

**Giá trị `installments`:**
| Giá trị | Số đơn |
|---------|-------:|
| `1` | 262,866 |
| `3` | 218,949 |
| `6` | 109,910 |
| `12` | 54,126 |
| `2` | 1,094 |

---

### `shipments.csv` — Vận chuyển

**566,067 dòng** — tương ứng 566,067 order_id duy nhất

| Cột | Kiểu thực tế | Nullable | Ghi chú |
|-----|-------------|----------|---------|
| `order_id` | int | Không | FK → `orders.order_id` |
| `ship_date` | date (str) | Không | Ngày gửi hàng |
| `delivery_date` | date (str) | Không | Ngày giao hàng |
| `shipping_fee` | float | Không | Phí vận chuyển (0 nếu miễn phí) |

**Đã kiểm chứng:** Tất cả shipment chỉ tồn tại cho orders có `order_status` ∈ {`delivered` (516,192), `returned` (36,113), `shipped` (13,762)}.

---

### `returns.csv` — Trả hàng

**39,939 dòng** (tương ứng 36,062 order_id duy nhất)

| Cột | Kiểu thực tế | Nullable | Ghi chú |
|-----|-------------|----------|---------|
| `return_id` | str | Không | Khoá chính; format `RET-XXXXXX` |
| `order_id` | int | Không | FK → `orders.order_id` |
| `product_id` | int | Không | FK → `products.product_id` |
| `return_date` | date (str) | Không | Ngày khách gửi trả |
| `return_reason` | str | Không | Xem giá trị bên dưới |
| `return_quantity` | int | Không | Số lượng sản phẩm trả |
| `refund_amount` | float | Không | Số tiền hoàn lại |

**Đã kiểm chứng:** Tất cả return đều liên kết với orders có `order_status = 'returned'` (100%).

**Giá trị `return_reason`:**
| Giá trị | Số bản ghi |
|---------|----------:|
| `wrong_size` | 13,967 |
| `defective` | 8,020 |
| `not_as_described` | 7,035 |
| `changed_mind` | 6,931 |
| `late_delivery` | 3,986 |

---

### `reviews.csv` — Đánh giá

**113,551 dòng** (tương ứng 111,369 order_id duy nhất — ~17% tổng orders)

| Cột | Kiểu thực tế | Nullable | Ghi chú |
|-----|-------------|----------|---------|
| `review_id` | str | Không | Khoá chính; format `REV-XXXXXXX` |
| `order_id` | int | Không | FK → `orders.order_id` |
| `product_id` | int | Không | FK → `products.product_id` |
| `customer_id` | int | Không | FK → `customers.customer_id` |
| `review_date` | date (str) | Không | Ngày gửi đánh giá |
| `rating` | int | Không | Điểm từ 1 đến 5 |
| `review_title` | str | Không | Tiêu đề đánh giá |

> ⚠️ **Khác biệt so với đề thi:** Đề thi nói reviews ~20% orders. Thực tế 111,369 orders có review trên 646,945 tổng orders = **~17%**.

---

## Bảng Analytical

### `sales.csv` — Dữ liệu doanh thu (Train)

**3,833 dòng** — 1 dòng / ngày, từ 2012-07-04 đến 2022-12-31

| Cột | Kiểu thực tế | Nullable | Ghi chú |
|-----|-------------|----------|---------|
| `Date` | date (str) | Không | Ngày đặt hàng |
| `Revenue` | float | Không | Tổng doanh thu thuần ngày đó |
| `COGS` | float | Không | Tổng giá vốn hàng bán ngày đó |

**Ví dụ:** 2012-07-04: Revenue=5,123,547.94, COGS=3,982,991.19

---

### `sample_submission.csv` — Mẫu file nộp bài (Test)

**548 dòng** — 1 dòng / ngày, từ 2023-01-01 đến 2024-07-01

| Cột | Kiểu thực tế | Nullable | Ghi chú |
|-----|-------------|----------|---------|
| `Date` | date (str) | Không | Ngày cần dự báo |
| `Revenue` | float | Không | Giá trị placeholder (không dùng làm feature) |
| `COGS` | float | Không | Giá trị placeholder (không dùng làm feature) |

---

## Bảng Operational

### `inventory.csv` — Tồn kho

**60,247 dòng** — 1 dòng / sản phẩm / tháng

| Cột | Kiểu thực tế | Nullable | Ghi chú |
|-----|-------------|----------|---------|
| `snapshot_date` | date (str) | Không | Cuối tháng; 2012-07-31 → 2022-12-31 |
| `product_id` | int | Không | FK → `products.product_id` |
| `stock_on_hand` | int | Không | Tồn kho cuối tháng |
| `units_received` | int | Không | Nhập kho trong tháng |
| `units_sold` | int | Không | Bán ra trong tháng |
| `stockout_days` | int | Không | Số ngày hết hàng trong tháng |
| `days_of_supply` | float | Không | Số ngày tồn kho đáp ứng được |
| `fill_rate` | float | Không | Tỷ lệ đơn được đáp ứng đủ |
| `stockout_flag` | int | Không | 0/1 — tháng có hết hàng |
| `overstock_flag` | int | Không | 0/1 — tồn kho vượt mức |
| `reorder_flag` | int | Không | 0/1 — cần tái đặt hàng |
| `sell_through_rate` | float | Không | Tỷ lệ hàng đã bán / tổng sẵn có |
| `product_name` | str | Không | Tên sản phẩm (denormalized) |
| `category` | str | Không | Danh mục sản phẩm (denormalized) |
| `segment` | str | Không | Phân khúc sản phẩm (denormalized) |
| `year` | int | Không | Năm trích từ `snapshot_date` |
| `month` | int | Không | Tháng trích từ `snapshot_date` |

**Giá trị `category`:** `Streetwear` (31,020), `Outdoor` (21,050), `GenZ` (4,674), `Casual` (3,503)

**Giá trị `segment`:** `Activewear` (18,290), `Everyday` (13,598), `Performance` (7,673), `Balanced` (6,622), `Trendy` (4,674), `Premium` (3,182), `Standard` (3,127), `All-weather` (3,081)

---

### `web_traffic.csv` — Lưu lượng truy cập

**3,652 dòng** — 1 dòng / ngày / nguồn traffic (không phải mỗi ngày 1 dòng đơn)

> ⚠️ **Lưu ý:** Dữ liệu web_traffic bắt đầu từ **2013-01-01** (muộn hơn orders 6 tháng) và mỗi ngày có thể có nhiều dòng ứng với các `traffic_source` khác nhau.

| Cột | Kiểu thực tế | Nullable | Ghi chú |
|-----|-------------|----------|---------|
| `date` | date (str) | Không | 2013-01-01 → 2022-12-31 |
| `sessions` | int | Không | Tổng phiên truy cập |
| `unique_visitors` | int | Không | Lượt khách duy nhất |
| `page_views` | int | Không | Tổng lượt xem trang |
| `bounce_rate` | float | Không | Tỷ lệ thoát (0.00406 → ...) |
| `avg_session_duration_sec` | float | Không | Thời gian phiên trung bình (giây) |
| `traffic_source` | str | Không | Kênh nguồn traffic |

**Giá trị `traffic_source`:**
| Giá trị | Số dòng |
|---------|--------:|
| `organic_search` | 1,090 |
| `paid_search` | 784 |
| `social_media` | 632 |
| `email_campaign` | 505 |
| `referral` | 375 |
| `direct` | 266 |

---

## Quan hệ giữa các bảng

### Đã kiểm chứng từ dữ liệu thực tế

| Quan hệ | Cardinality | Kiểm chứng |
|---------|-------------|-----------|
| `orders` ↔ `payments` | **1:1** | ✅ Tập `order_id` khớp hoàn toàn (646,945 = 646,945) |
| `orders` ↔ `shipments` | 1:0–1 | ✅ 566,067 orders có shipment; chỉ status `delivered`/`returned`/`shipped` |
| `orders` ↔ `returns` | 1:0–nhiều | ✅ 36,062 orders có return; 100% là status `returned` |
| `orders` ↔ `reviews` | 1:0–nhiều | ✅ 111,369 orders có review (~17% tổng orders) |
| `orders` ↔ `order_items` | 1:nhiều | ✅ Tất cả 646,945 orders đều có item; 714,669 dòng tổng |
| `order_items` ↔ `promotions` | nhiều:0–1 | ✅ 38.7% dòng có `promo_id`; 0.03% có `promo_id_2` |
| `products` ↔ `inventory` | 1:nhiều | ✅ 0 vi phạm FK; 1 dòng/sản phẩm/tháng |
| `customers.zip` → `geography.zip` | nhiều:1 | ✅ 0 vi phạm FK |
| `orders.zip` → `geography.zip` | nhiều:1 | ✅ 0 vi phạm FK |
| `order_items.product_id` → `products.product_id` | nhiều:1 | ✅ 0 vi phạm FK |

### Sơ đồ quan hệ

```
geography (zip PK)
    ↑ FK zip
customers (customer_id PK) ─────────── orders (order_id PK)
                                            │
                        ┌───────────────────┼──────────────────┐
                        │                  │                   │
                    order_items        payments (1:1)      shipments
                    (order_id FK)     (order_id FK)       (order_id FK)
                        │
                    products (product_id PK)
                        │
                    inventory (product_id FK)
                        │
                    promotions (promo_id PK)
                    (FK từ order_items.promo_id)

reviews ──────── orders (order_id FK)
         └────── products (product_id FK)
         └────── customers (customer_id FK)

returns ──────── orders (order_id FK)
         └────── products (product_id FK)
```

---

## Sai khác giữa tài liệu đề thi và dữ liệu thực

| # | Mục | Đề thi mô tả | Thực tế dữ liệu |
|---|-----|-------------|-----------------|
| 1 | `customers.gender` | nullable | **Không có null** (0/121,930) |
| 2 | `customers.age_group` | nullable | **Không có null** (0/121,930) |
| 3 | `customers.acquisition_channel` | nullable | **Không có null** (0/121,930) |
| 4 | `promotions.min_order_value` | float, nullable | **int, không có null**; dùng `0` thay cho null |
| 5 | `orders` ↔ `reviews` | ~20% orders có review | Thực tế **~17%** (111,369/646,945) |
| 6 | `products.segment` | Đề Q2 liệt kê 4 loại | Thực tế có **8 loại** segment |
| 7 | `web_traffic` bắt đầu | Không rõ | Thực tế bắt đầu **2013-01-01** (muộn hơn orders 6 tháng) |
| 8 | `payments.installments` | Không đề cập giá trị `2` | Có 1,094 dòng với `installments = 2` |
| 9 | `order_items.promo_id` | nullable | ✅ Đúng — 61.3% null |
| 10 | `shipments` chỉ tồn tại cho shipped/delivered/returned | ✅ Đúng | Xác nhận hoàn toàn |

---

## Ghi chú sử dụng cho Forecasting

- **Train set:** `sales.csv` — 3,833 ngày từ 2012-07-04 đến 2022-12-31
- **Test set:** `sample_submission.csv` — 548 ngày từ 2023-01-01 đến 2024-07-01
- Mục tiêu dự báo: cột `Revenue` (và `COGS` nếu cần)
- Features có thể tạo từ: `orders`, `order_items`, `web_traffic`, `inventory`, `promotions`, `returns`
- **Không được dùng** `Revenue`/`COGS` từ tập test làm feature
- Cần đặt random seed để đảm bảo reproducibility

---

## Bảng Tổng hợp — `master_table.csv`

> Được tạo bởi pipeline tại `data/output/master_table.csv`. Đây là bảng join dẹt (denormalized flat table) từ tất cả các nguồn, cấp độ dòng = **order_item** (714,669 dòng, 53 cột).

**Thống kê tổng quan:**

| Chỉ số | Giá trị |
|--------|--------:|
| Tổng số dòng | 714,669 |
| Số cột | 53 |
| Unique `order_id` | 646,945 |
| Unique `product_id` | 1,598 |
| Unique `customer_id` | 90,246 |

---

### Cấu trúc cột đầy đủ

| Cột | Kiểu | Nullable | Nguồn gốc | Ghi chú |
|-----|------|----------|-----------|---------|
| `order_id` | int64 | Không | `orders` | FK đơn hàng |
| `product_id` | int64 | Không | `order_items` | FK sản phẩm |
| `quantity` | int64 | Không | `order_items` | Range [1, 8]; mean ≈ 4.5 |
| `unit_price` | float64 | Không | `order_items` | Range [392.6, 43,060]; mean ≈ 5,115 |
| `discount_amount` | float64 | Không | `order_items` | Range [0, 35,240]; mean ≈ 1,049 |
| `promo_id` | str | Không | `order_items` | `"none"` khi không có KM |
| `promo_id_2` | str | Không | `order_items` | `"none"` khi không có KM thứ hai |
| `order_item_id` | str | Không | Derived | Format `{order_id}_{product_id}` |
| `line_revenue` | float64 | Không | Derived | `quantity × unit_price − discount_amount`; range [389.7, 331,600]; mean ≈ 21,940 |
| `order_date` | str | Không | `orders` | 2012-07-04 → 2022-12-31 |
| `customer_id` | int64 | Không | `orders` | FK khách hàng |
| `zip` | int64 | Không | `orders` | FK mã bưu chính |
| `order_status` | str | Không | `orders` | Xem giá trị bên dưới |
| `payment_method` | str | Không | `orders` | Xem giá trị bên dưới |
| `device_type` | str | Không | `orders` | `mobile` / `desktop` / `tablet` |
| `order_source` | str | Không | `orders` | Xem giá trị bên dưới |
| `city` | str | Không | `customers` | Tên thành phố khách hàng |
| `signup_date` | str | Không | `customers` | 2012-01-20 → 2022-12-31 |
| `gender` | str | Không | `customers` | `Female` / `Male` / `Non-binary` |
| `age_group` | str | Không | `customers` | 5 nhóm tuổi |
| `acquisition_channel` | str | Không | `customers` | 6 kênh tiếp thị |
| `region` | str | Không | `geography` | `EAST` / `CENTRAL` / `WEST` (uppercase sau join) |
| `district` | str | Không | `geography` | Tên quận/huyện |
| `product_name` | str | Không | `products` | Tên sản phẩm |
| `category` | str | Không | `products` | `Streetwear` / `Outdoor` / `GenZ` / `Casual` |
| `segment` | str | Không | `products` | 8 loại (xem bên dưới) |
| `size` | str | Không | `products` | `S` / `M` / `L` / `XL` |
| `color` | str | Không | `products` | Nhãn màu sản phẩm |
| `price` | float64 | Không | `products` | Giá bán lẻ; range [440.4, 40,950]; mean ≈ 5,508 |
| `cogs` | float64 | Không | `products` | Giá vốn; range [249.3, 38,900]; mean ≈ 4,408 |
| `payment_value` | float64 | Không | `payments` | Tổng giá trị thanh toán; range [389.7, 331,600]; mean ≈ 23,940 |
| `installments` | int64 | Không | `payments` | Số kỳ trả góp: 1/2/3/6/12 |
| `ship_date` | str | **Có** | `shipments` | null cho 89,287 dòng (12.5%) — đơn chưa ship |
| `delivery_date` | str | **Có** | `shipments` | null cho 89,287 dòng (12.5%); range 2012-07-06 → 2022-12-31 |
| `shipping_fee` | float64 | Không | `shipments` | Range [0, 32]; mean ≈ 4.24 (`0` = miễn phí) |
| `review_id` | str | Không | `reviews` | `"none"` khi không có review |
| `rating` | float64 | Không | `reviews` | Range [0, 5]; mean ≈ 0.63 (`0` = không có review) |
| `review_title` | str | **Có** | `reviews` | null cho 601,116 dòng (84.1%) |
| `return_quantity` | float64 | Không | `returns` | Range [0, 11]; mean ≈ 0.15 (`0` = không trả) |
| `refund_amount` | float64 | Không | `returns` | Range [0, 160,900]; mean ≈ 714.5 (`0` = không trả) |
| `return_reason` | str | **Có** | `returns` | null cho 674,730 dòng (94.4%) |
| `promo_type` | str | **Có** | `promotions` | null cho 438,353 dòng (61.3%); `percentage` / `fixed` |
| `discount_value` | float64 | **Có** | `promotions` | null cho 438,353 dòng (61.3%); range [10, 50]; mean ≈ 17.97 |
| `promo_channel` | str | **Có** | `promotions` | null cho 438,353 dòng (61.3%); xem giá trị bên dưới |
| `min_order_value` | float64 | **Có** | `promotions` | null cho 438,353 dòng (61.3%); range [0, 200,000] |
| `stock_on_hand` | float64 | **Có** | `inventory` | null cho 19,512 dòng (2.7%); range [3, 2,657]; mean ≈ 422.6 |
| `fill_rate` | float64 | **Có** | `inventory` | null cho 19,512 dòng (2.7%); range [0.067, 1.0]; mean ≈ 0.951 |
| `sell_through_rate` | float64 | **Có** | `inventory` | null cho 19,512 dòng (2.7%); range [0.0004, 0.853]; mean ≈ 0.178 |
| `stockout_flag` | float64 | **Có** | `inventory` | null cho 19,512 dòng (2.7%); binary 0/1 |
| `stockout_days` | float64 | **Có** | `inventory` | null cho 19,512 dòng (2.7%); range [0, 28]; mean ≈ 1.46 |
| `line_cogs` | float64 | Không | Derived | `quantity × cogs`; range [346.3, 311,200]; mean ≈ 19,820 |
| `is_legacy` | int64 | Không | Derived | 1 = đơn cũ (531,554 dòng / 74.4%); 0 = đơn mới (183,115 dòng / 25.6%) |
| `category_return_prob` | float64 | Không | Derived | Xác suất trả theo category; range [0.0542, 0.0573] |

---

### Giá trị categorical trong master_table

**`order_status`:**
| Giá trị | Số dòng |
|---------|--------:|
| `delivered` | 570,887 |
| `cancelled` | 65,673 |
| `returned` | 40,034 |
| `shipped` | 15,094 |
| `paid` | 14,987 |
| `created` | 7,994 |

**`payment_method`:**
| Giá trị | Số dòng |
|---------|--------:|
| `credit_card` | 393,421 |
| `paypal` | 107,230 |
| `cod` | 106,965 |
| `apple_pay` | 71,510 |
| `bank_transfer` | 35,543 |

**`order_source`:**
| Giá trị | Số dòng |
|---------|--------:|
| `organic_search` | 200,429 |
| `paid_search` | 156,500 |
| `social_media` | 143,306 |
| `email_campaign` | 85,849 |
| `referral` | 71,256 |
| `direct` | 57,329 |

**`region`** (uppercase trong master_table, khác với `geography.csv`):
| Giá trị | Số dòng |
|---------|--------:|
| `EAST` | 321,293 |
| `CENTRAL` | 201,342 |
| `WEST` | 192,034 |

**`category`:**
| Giá trị | Số dòng |
|---------|--------:|
| `Streetwear` | 393,533 |
| `Outdoor` | 259,986 |
| `GenZ` | 37,159 |
| `Casual` | 23,991 |

**`segment`:**
| Giá trị | Số dòng |
|---------|--------:|
| `Activewear` | 230,375 |
| `Everyday` | 182,533 |
| `Balanced` | 103,333 |
| `Performance` | 96,730 |
| `Trendy` | 37,159 |
| `Premium` | 31,032 |
| `All-weather` | 22,570 |
| `Standard` | 10,937 |

**`size`:**
| Giá trị | Số dòng |
|---------|--------:|
| `XL` | 193,025 |
| `M` | 176,428 |
| `L` | 173,174 |
| `S` | 172,042 |

**`promo_type`** (61.3% null):
| Giá trị | Số dòng |
|---------|--------:|
| `percentage` | 255,366 |
| `fixed` | 20,950 |

**`promo_channel`** (61.3% null):
| Giá trị | Số dòng |
|---------|--------:|
| `all_channels` | 127,687 |
| `online` | 66,171 |
| `email` | 41,576 |
| `social_media` | 31,977 |
| `in_store` | 8,905 |

**`return_reason`** (94.4% null):
| Giá trị | Số dòng |
|---------|--------:|
| `wrong_size` | 13,968 |
| `defective` | 8,020 |
| `not_as_described` | 7,034 |
| `changed_mind` | 6,931 |
| `late_delivery` | 3,986 |

---

### Lưu ý quan trọng về master_table

1. **Cấp độ dòng là order_item**, không phải order — khi tính revenue/cogs cần dùng `line_revenue`/`line_cogs`, không phải `payment_value`.
2. **`region` bị uppercase** trong quá trình join: `EAST`/`CENTRAL`/`WEST` thay vì `East`/`Central`/`West` trong `geography.csv`.
3. **`promo_id` và `promo_id_2`** được fill bằng chuỗi `"none"` (không phải `NaN`) khi không có khuyến mãi.
4. **`review_id`** được fill bằng `"none"` khi không có review; `rating = 0` cho items không được đánh giá.
5. **`is_legacy`**: `1` = đơn hàng cũ (74.4%), `0` = đơn hàng mới (25.6%) — cột derived từ logic pipeline.
6. **`category_return_prob`**: Xác suất trả hàng theo category (range rất hẹp: 0.054–0.057), được tính theo category từ dữ liệu lịch sử.
7. **Unique `product_id` = 1,598** (thấp hơn 2,412 trong `products.csv`) — chỉ các sản phẩm thực sự được mua mới xuất hiện.
8. **Unique `customer_id` = 90,246** (thấp hơn 121,930 trong `customers.csv`) — chỉ khách hàng đã đặt hàng.
9. **`ship_date`/`delivery_date` null = 12.5%** tương ứng với đơn `cancelled`/`paid`/`created` chưa được giao.
