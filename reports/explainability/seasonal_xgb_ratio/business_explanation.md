# Business Explainability Report - `seasonal_xgb_ratio`

Báo cáo này diễn giải các tín hiệu quan trọng mà mô hình XGBoost học được theo ngôn ngữ kinh doanh.

## Cách đọc

- `gain`: feature giúp giảm lỗi nhiều trong cây quyết định.
- `xgb_contrib`: đóng góp tuyệt đối trung bình kiểu TreeSHAP native của XGBoost.
- `permutation`: mức độ lỗi tăng khi xáo trộn feature.
- PDP chỉ vẽ cho Top 10 feature để tránh chi phí tính toán quá lớn.

## Các yếu tố dẫn động chính

- **daily_promo_order_count_roll7** trong mô hình **COGS_Ratio** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.905419`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **daily_total_item_revenue_lag365** trong mô hình **Revenue_Residual** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.762071`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **daily_discount_depth_roll7** trong mô hình **COGS_Ratio** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.73831`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **promo_penetration_rate_roll7** trong mô hình **COGS_Ratio** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.697754`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **day_of_week** trong mô hình **Revenue_Residual** là tín hiệu về **hiệu ứng lịch, mùa vụ ngắn hạn và ngày đặc biệt**. Mức quan trọng tổng hợp: `0.670983`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **daily_gross_revenue_before_discount_lag365** trong mô hình **Revenue_Residual** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.605233`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **days_until_holiday** trong mô hình **Revenue_Residual** là tín hiệu về **hiệu ứng lịch, mùa vụ ngắn hạn và ngày đặc biệt**. Mức quan trọng tổng hợp: `0.54798`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **aov_lag365** trong mô hình **Revenue_Residual** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.486723`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **daily_discount_amount_roll7** trong mô hình **COGS_Ratio** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.460739`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **daily_discount_depth_lag365** trong mô hình **COGS_Ratio** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.455131`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **day_of_year** trong mô hình **Revenue_Residual** là tín hiệu về **hiệu ứng lịch, mùa vụ ngắn hạn và ngày đặc biệt**. Mức quan trọng tổng hợp: `0.402611`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **daily_order_count_lag30** trong mô hình **Revenue_Residual** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.401552`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **days_until_holiday** trong mô hình **COGS_Ratio** là tín hiệu về **hiệu ứng lịch, mùa vụ ngắn hạn và ngày đặc biệt**. Mức quan trọng tổng hợp: `0.388561`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **promo_penetration_rate_roll7** trong mô hình **Revenue_Residual** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.380369`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **legacy_order_ratio_roll30** trong mô hình **Revenue_Residual** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.379597`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **daily_expected_margin_mix_roll30** trong mô hình **Revenue_Residual** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.376695`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **size_mix_return_pressure_roll7** trong mô hình **Revenue_Residual** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.355869`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **active_customer_demographic_mix_score_roll7** trong mô hình **Revenue_Residual** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.346444`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **active_customer_demographic_mix_score_lag365** trong mô hình **Revenue_Residual** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.335805`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **daily_order_line_count_lag30** trong mô hình **Revenue_Residual** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.333298`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **daily_total_quantity_lag30** trong mô hình **Revenue_Residual** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.331826`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **covid_intensity_lag30** trong mô hình **Revenue_Residual** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.33063`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **daily_total_item_revenue_roll7** trong mô hình **Revenue_Residual** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.310396`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **new_customer_aov_roll7** trong mô hình **Revenue_Residual** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.304929`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **daily_expected_margin_mix_roll30** trong mô hình **COGS_Ratio** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.296292`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **daily_total_item_revenue_lag7** trong mô hình **Revenue_Residual** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.294385`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **new_customer_aov_lag365** trong mô hình **Revenue_Residual** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.287609`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **legacy_revenue_share_roll30** trong mô hình **Revenue_Residual** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.286095`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **daily_gross_revenue_before_discount_lag7** trong mô hình **Revenue_Residual** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.285129`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.
- **daily_return_risk_index_lag365** trong mô hình **Revenue_Residual** là tín hiệu về **nhu cầu lịch sử và tính mùa vụ**. Mức quan trọng tổng hợp: `0.281149`. Nếu feature này ổn định qua nhiều phương pháp importance, đây là ứng viên nên giữ lại trong pipeline.

## Gợi ý chọn/xóa feature

- Ưu tiên giữ feature có thứ hạng cao ở cả `gain`, `xgb_contrib` và `permutation`.
- Cân nhắc xóa feature có importance gần 0 ở tất cả phương pháp, nhất là nếu khó giải thích về mặt kinh doanh.
- Với feature tương quan cao cùng nhóm, chỉ giữ biến dễ giải thích và ổn định nhất.
- Không xóa feature chỉ vì PDP không được vẽ; PDP mặc định chỉ chạy trên Top N để tiết kiệm thời gian.