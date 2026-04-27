# Model Selection Report

## Official metric

The validation selector uses the leaderboard metric confirmed by the user: average MAE across `Revenue` and `COGS`. `Profit` is not part of the selection metric.

## Backtest folds

Recovery-era folds only: 2021, 2022, and 2022-H2. COVID-heavy 2020 is excluded because it is an anomalous regime relative to the 2023 forecast target.

## Selected candidate

`seasonal_xgb_market_uplift_160_cogs102`

- Mean official MAE: `646782.202`
- Std official MAE: `70320.757`
- Max fold official MAE: `727625.800`
- Residual scale: `1.6`
- COGS mix factor: `1.02`

## Candidate ranking

| candidate                              |   mean_official_mae |   std_official_mae |   max_official_mae |   mean_revenue_mae |   mean_cogs_mae |
|:---------------------------------------|--------------------:|-------------------:|-------------------:|-------------------:|----------------:|
| seasonal_xgb_market_uplift_160_cogs102 |              646782 |            70320.8 |             727626 |             696285 |          597279 |
| seasonal_xgb_market_uplift_135         |              649926 |            77201.3 |             739064 |             687852 |          612001 |
| seasonal_xgb_market_uplift_160         |              651309 |            74311.6 |             736962 |             696285 |          606333 |
| seasonal_xgb_full                      |              654376 |            79221.3 |             745853 |             682703 |          626049 |
| seasonal_xgb_market_uplift_160_cogs098 |              657093 |            78002.8 |             747137 |             696285 |          617901 |
| seasonal_xgb_core_business             |              660481 |            42182.6 |             708707 |             706098 |          614864 |
| seasonal_xgb_core_business_uplift_135  |              662399 |            38794.7 |             704391 |             710142 |          614657 |

## Notes

Public leaderboard should be used only as a final sanity check after this validation step, not as the primary model selector.
