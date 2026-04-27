# Feature Audit Recommendation

- Rows: `3833`
- Date range: `2012-07-04` → `2022-12-31`
- Numeric feature count: `214`
- High-correlation pairs >= 0.95: `196`
- Low-importance/constant candidates: `7`

## Candidate feature profiles
- `core_seasonal_slim`: `42` features
- `core_plus_business`: `111` features
- `no_revenue_like`: `102` features

## Recommended next experiment

Run `core_seasonal_slim` first to reduce lag/rolling duplication while keeping the strongest seasonal signals.
Then compare against `core_plus_business` to see whether sparse business drivers improve public MAE.