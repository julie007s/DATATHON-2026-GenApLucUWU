# Recovery Regime Analysis

## Regime hypothesis

- Pre-2019: stable normal-growth regime.
- 2019-2022: shock/depressed demand regime.
- 2023-2024: recovery/rebound regime.

## Estimated historical signals

- Pre period: `2012-2018`
- Shock period: `2019-2022`
- Pre-period daily mean CAGR: `3.6126%`
- Pandemic gap ratio vs 2018 daily mean: `40.5280%`

## Generated candidate groups

| Approach | What it tests |
|---|---|
| `pre_pandemic_trend_anchor` | Re-anchor forecast toward pre-shock growth trend |
| `regime_weighted_proxy` | Approximate reduced shock-period training influence |
| `recovery_curve` | Gradual 2023-2024 demand normalization curve |
| `recovery_selection` | Select a defensible candidate from recovery-aware scenarios |

## Candidate summary

| candidate                    | approach                  | submission                                  | analysis                                  |   revenue_factor_start |   revenue_factor_end |   revenue_factor_mean |   cogs_factor_mean |   revenue_mean |   cogs_mean |   profit_mean | rationale                                                                                                                                                                   |
|:-----------------------------|:--------------------------|:--------------------------------------------|:------------------------------------------|-----------------------:|---------------------:|----------------------:|-------------------:|---------------:|------------:|--------------:|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| recovery_trend_anchor_mild   | pre_pandemic_trend_anchor | submission_recovery_trend_anchor_mild.csv   | analysis_recovery_trend_anchor_mild.csv   |                  1.021 |              1.04011 |               1.03047 |               1    |    3.65613e+06 | 2.97951e+06 |        676624 | Re-anchors the validated forecast toward the stable pre-2019 growth trend. The factor is bounded and derived from historical pre-shock CAGR.                                |
| recovery_trend_anchor_base   | pre_pandemic_trend_anchor | submission_recovery_trend_anchor_base.csv   | analysis_recovery_trend_anchor_base.csv   |                  1.033 |              1.06302 |               1.04788 |               1    |    3.71833e+06 | 3.03019e+06 |        688137 | Re-anchors the validated forecast toward the stable pre-2019 growth trend. The factor is bounded and derived from historical pre-shock CAGR.                                |
| recovery_trend_anchor_strong | pre_pandemic_trend_anchor | submission_recovery_trend_anchor_strong.csv | analysis_recovery_trend_anchor_strong.csv |                  1.045 |              1.08594 |               1.06529 |               1    |    3.78053e+06 | 3.08088e+06 |        699650 | Re-anchors the validated forecast toward the stable pre-2019 growth trend. The factor is bounded and derived from historical pre-shock CAGR.                                |
| regime_weighted_core         | regime_weighted_proxy     | submission_regime_weighted_core.csv         | analysis_regime_weighted_core.csv         |                  1.036 |              1.054   |               1.045   |               1    |    3.70763e+06 | 3.02147e+06 |        686153 | Proxy for retraining with lower shock-period influence and higher normal-growth influence. It tests the expected level effect before implementing full weighted retraining. |
| regime_weighted_core_uplift  | regime_weighted_proxy     | submission_regime_weighted_core_uplift.csv  | analysis_regime_weighted_core_uplift.csv  |                  1.06  |              1.09    |               1.075   |               1.01 |    3.81452e+06 | 3.13967e+06 |        674852 | Proxy for retraining with lower shock-period influence and higher normal-growth influence. It tests the expected level effect before implementing full weighted retraining. |
| recovery_curve_mild          | recovery_curve            | submission_recovery_curve_mild.csv          | analysis_recovery_curve_mild.csv          |                  1.02  |              1.07    |               1.045   |               1    |    3.70889e+06 | 3.02249e+06 |        686394 | Applies a gradual 2023-2024 recovery path, representing demand normalization after the shock period.                                                                        |
| recovery_curve_base          | recovery_curve            | submission_recovery_curve_base.csv          | analysis_recovery_curve_base.csv          |                  1.04  |              1.11    |               1.075   |               1    |    3.81609e+06 | 3.10985e+06 |        706238 | Applies a gradual 2023-2024 recovery path, representing demand normalization after the shock period.                                                                        |
| recovery_curve_strong        | recovery_curve            | submission_recovery_curve_strong.csv        | analysis_recovery_curve_strong.csv        |                  1.06  |              1.15    |               1.105   |               1    |    3.9233e+06  | 3.19722e+06 |        726083 | Applies a gradual 2023-2024 recovery path, representing demand normalization after the shock period.                                                                        |

## Guardrail

These factors are bounded and derived from the regime hypothesis. They should be validated/stress-tested before final selection.