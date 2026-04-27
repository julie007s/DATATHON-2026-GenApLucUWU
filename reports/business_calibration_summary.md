# Business Calibration Summary

Recommended current candidate: `submission_market_uplift_160.csv`

## Business rationale

This layer keeps the seasonal baseline intact and calibrates only the business residual. The residual represents non-seasonal business drivers such as traffic, promotion response, AOV, inventory availability, customer behavior, and market-regime effects.

| Component | Explanation |
|---|---|
| `market_uplift` | Scales only the XGBoost business residual, not the seasonal baseline. This represents post-2022 demand-regime uplift from traffic, AOV, promo response, fulfillment availability, and customer behavior signals that the historical model may understate. |
| `time_ramp` | Applies a gradual market-maturity curve across the forecast horizon. This is used when later 2023-2024 demand is expected to sit above early-horizon demand. |
| `monthly_seasonality` | Applies a bounded month-level commerce seasonality adjustment to the business residual. It keeps holiday and campaign-sensitive months slightly more responsive without changing baseline seasonality. |
| `cogs_mix` | Adjusts COGS ratio for product/margin mix. Revenue and COGS are linked, but category mix, discount depth, and fulfillment cost can shift the realized COGS-to-revenue ratio. |

## Guardrail

This is a calibrated forecast, not a new raw model. It should be presented as a market-regime adjustment for 2023-2024 demand rather than a blind leaderboard multiplier.
