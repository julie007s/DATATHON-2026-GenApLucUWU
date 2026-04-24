# Yêu cầu cho Agent: Tách dữ liệu, setup notebook và training model dự báo chuỗi thời gian

## 1) Mục tiêu
Hãy xây dựng một notebook training cho bài toán dự báo chuỗi thời gian trên bộ dữ liệu DATATHON 2026, dựa trên schema đã được cung cấp và đặc biệt tận dụng bảng `master_table` đã được clean sẵn.

Mục tiêu của notebook:
- Tách dữ liệu train/validation/test đúng theo thời gian, tránh leakage.
- Tạo feature từ `master_table` và các bảng liên quan chỉ bằng thông tin có sẵn tại thời điểm dự báo.
- Thiết lập môi trường notebook để train model có thể tái lập được.
- Hiển thị kết quả sau train một cách rõ ràng: metric, biểu đồ, bảng so sánh, feature importance, prediction sample.

## 2) Dữ liệu đầu vào cần dùng
### Nguồn chính
- `sales.csv`: dữ liệu train cho mục tiêu dự báo theo ngày.
- `sample_submission.csv`: danh sách ngày của test cần dự báo.
- `master_table.csv`: bảng đã clean, dạng denormalized, cấp độ dòng là `order_item`.

### Lưu ý quan trọng về `master_table`
- Một dòng = một order item, không phải một order.
- `master_table` chứa dữ liệu lịch sử đến `2022-12-31`.
- Các cột như `promo_id`, `review_id` đã được fill bằng giá trị thay thế (`none`, `0`) ở những dòng thiếu.
- Cột `region` đã được uppercase.
- Không được dùng bất kỳ thông tin nào vượt quá thời điểm cần dự báo.

## 3) Quy tắc tách train / validation / test
### 3.1 Target
- Target chính: `Revenue`.
- Nếu model cần, có thể train thêm target phụ `COGS`, nhưng phải tách riêng hoặc multi-output có kiểm soát.

### 3.2 Split theo thời gian
Hãy split theo thứ tự thời gian tuyệt đối, không shuffle.

Đề xuất mặc định:
- `train`: từ `2012-07-04` đến `2021-12-31`
- `validation`: từ `2022-01-01` đến `2022-12-31`
- `test`: từ `2023-01-01` đến `2024-07-01` theo `sample_submission.csv`

Nếu cần backtest mạnh hơn, hãy thêm walk-forward validation với nhiều fold trên phần train.

### 3.3 Nguyên tắc chống leakage
- Không dùng dữ liệu tương lai để tạo feature cho quá khứ.
- Rolling / lag feature chỉ được tính trên dữ liệu trước thời điểm dự báo.
- Không lấy target của test làm feature.
- Không dùng `Revenue` hoặc `COGS` của test.
- Không dùng các thống kê tính trên toàn bộ tập nếu chúng làm lộ tương lai.

## 4) Cách tạo bảng train cho bài toán forecasting
### 4.1 Chuẩn hoá cấp độ dữ liệu
Vì `master_table` là cấp độ `order_item`, cần aggregate về cấp ngày để phù hợp với bài toán dự báo doanh thu theo ngày.

Tạo bảng feature theo `order_date` với 1 dòng / ngày.

### 4.2 Gợi ý feature từ `master_table`
Tạo các feature lịch sử theo ngày bằng cách aggregate các nhóm sau:
- Tổng số order items
- Tổng quantity
- Tổng/mean/min/max `unit_price`
- Tổng/mean/min/max `discount_amount`
- Tổng/mean `line_revenue`
- Tổng/mean `line_cogs`
- Số lượng unique `order_id`
- Số lượng unique `customer_id`
- Tỷ lệ `is_legacy`
- Phân phối theo `category`, `segment`, `size`, `region`, `payment_method`, `order_source`
- Tỷ lệ có promo, tỷ lệ có review, tỷ lệ return
- Các feature theo calendar: ngày trong tuần, tháng, quý, năm, cuối tháng, cuối quý, lễ / cuối tuần nếu có thể tạo an toàn

### 4.3 Feature temporal nên có
- Lag: `t-1`, `t-7`, `t-14`, `t-28`, `t-56`, `t-365`
- Rolling mean / rolling std: cửa sổ `7`, `14`, `28`, `56`, `365`
- Expanding mean / expanding std
- Difference feature: `y_t - y_{t-1}`, `y_t - y_{t-7}`
- Seasonal feature: tuần trong năm, tháng, day-of-week, week-of-month

### 4.4 Feature exogenous
Chỉ dùng những biến có thể biết trước hoặc có thể suy ra hợp lệ tại thời điểm dự báo.
- Calendar feature: an toàn.
- Feature từ `web_traffic`, `inventory`, `promotions`, `returns`, `reviews` chỉ dùng nếu được aggregate từ lịch sử và không phụ thuộc tương lai.
- Nếu có biến không thể biết cho tương lai test, không dùng trực tiếp làm feature test.

## 5) Notebook setup
Hãy tạo notebook theo cấu trúc có thể chạy từ đầu đến cuối.

### 5.1 Môi trường đề xuất
Notebook nên import và chuẩn bị các thư viện sau:
- `pandas`, `numpy`
- `scikit-learn`
- `lightgbm`, `xgboost`, `catboost`
- `optuna` để tuning nếu cần
- `matplotlib` hoặc `plotly` để vẽ
- `joblib` để lưu model
- `warnings`, `pathlib`, `datetime`

### 5.2 Cấu hình tái lập
Trong cell đầu tiên, hãy:
- đặt `random seed`
- cố định số thread nếu cần
- khai báo đường dẫn input/output rõ ràng
- kiểm tra phiên bản thư viện nếu cần

### 5.3 Cấu trúc notebook
Notebook nên có các phần sau:
1. Config và import
2. Load dữ liệu
3. Validate schema / kiểm tra null / kiểu dữ liệu
4. Feature engineering
5. Tách train / validation / test
6. Train baseline model
7. Tuning nếu cần
8. Đánh giá trên validation
9. Dự báo test
10. Hiển thị kết quả và lưu file output

## 6) Yêu cầu train model
### 6.1 Baseline trước
Trước khi train model mạnh, hãy tạo baseline đơn giản:
- naive forecast
- moving average
- hoặc LightGBM baseline với lag features

### 6.2 Model training
Sau baseline, train ít nhất một model chính. Nếu muốn tối ưu tốt hơn, có thể so sánh:
- LightGBM
- XGBoost
- CatBoost
- ensemble weighted average

### 6.3 Validation
- Dùng time-based validation.
- Ưu tiên walk-forward validation nếu thời gian cho phép.
- Nếu chỉ làm một split, phải báo rõ train/validation period.

### 6.4 Metrics cần tính
Ít nhất phải hiển thị:
- MAE
- RMSE
- MAPE hoặc SMAPE
- Nếu có multi-step / seasonal forecast, có thể thêm RMSSE

## 7) Cách hiển thị kết quả sau training
Sau khi train, notebook phải xuất các phần sau:

### 7.1 Bảng kết quả
- Bảng metric của từng model
- Bảng so sánh train vs validation
- Bảng top feature importance nếu model hỗ trợ

### 7.2 Biểu đồ
- Actual vs Predicted trên validation
- Residual plot
- Error distribution
- Feature importance plot
- Forecast line plot cho tập test hoặc sample submission

### 7.3 File output
Lưu ra thư mục output:
- model đã train
- file prediction cho test
- file metric summary
- file notebook hoặc log nếu cần

## 8) Output mong đợi từ agent
Agent cần tạo một notebook hoặc script hoàn chỉnh có thể:
- đọc schema và `master_table`
- tạo feature theo ngày
- split dữ liệu đúng chuẩn time series
- train model
- đánh giá trên validation
- dự báo test
- in ra bảng và biểu đồ kết quả

## 9) Checklist bắt buộc
- [ ] Không shuffle dữ liệu time series
- [ ] Không dùng feature từ tương lai
- [ ] Có train/validation/test rõ ràng
- [ ] Có baseline và model chính
- [ ] Có metric đánh giá
- [ ] Có biểu đồ kết quả sau training
- [ ] Có file output prediction
- [ ] Có seed để tái lập

## 10) Ghi chú thực thi
- Nếu `master_table` quá lớn, hãy ưu tiên xử lý theo kiểu groupby / aggregate hiệu quả.
- Nếu dữ liệu có cột kiểu chuỗi ngày, hãy convert sang `datetime` ngay khi load.
- Nếu feature nào không thể tạo cho test, hãy loại bỏ trước khi train.
- Nếu có nguy cơ leakage, ưu tiên bỏ feature đó.

## 11) Kết luận
Hãy viết notebook theo hướng production-friendly, rõ ràng, dễ debug và dễ mở rộng. Mục tiêu không chỉ là train được model mà còn phải đảm bảo quy trình forecast đúng chuẩn, không leak, và có thể lặp lại trên môi trường notebook.
