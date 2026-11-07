---
language:
- id
- en
tags:
- fiscycle
- research-prototype
- not-field-validated
---

# Fiscycle Smart BSF B1 — next-observation mean wet-weight forecasting

## Architecture and exact feature schema
Frozen HistGradientBoostingRegressor. Feature order: moisture_percent, elapsed_days, current_weight_mg, previous_weight_mg, recent_growth_mg_per_day, forecast_horizon_days. Moisture is an experimental treatment (45/55/65/75%), not Fiscycle live sensor telemetry. Inputs are mean measured wet weights per individual from the same replicate; preserve supported bounds and abstention behavior in frozen inference metadata.

## Target and horizon
Mean wet weight mg per individual at the next recorded observation; observed training horizon 0.770833–1.208333 days. Not harvest kilograms, batch biomass, or an exact universal 24-hour biological trajectory. Existing replay uses a predeclared one-day horizon and only scores time-aligned observations.

## Saved evaluation
Public experiment: 400 observations, 20 replicates, four moisture treatments. Sixteen development replicates/288 supervised pairs; four group-CV folds. Four held-out replicates (45-5,55-5,65-5,75-5), 72 pairs. HGB holdout MAE 17.244599 mg, RMSE 22.821732 mg, bias +1.825013 mg. Persistence MAE 26.910222 mg, a 35.918% MAE reduction. CV mean MAE 17.995619 mg, SD 1.306219 mg.

Residual-based interval radius 40.793272 mg (lower bound clipped to zero), holdout empirical coverage 66/72=91.6667%; no guaranteed per-prediction confidence. Subsequent diagnostics reuse the same holdout, not new independent validation.

## Intended use and limitations
RESEARCH_PROTOTYPE / NOT_FIELD_VALIDATED. No local BSF sensors or Fiscycle field observations. Development replay is IN_SAMPLE_DEVELOPMENT_REPLAY, not holdout evidence. Four hundred rows are not 400 independent experiments. Do not infer optimal moisture/harvest intervention from limited treatment contrasts. Do not automatically feed A2 predictions into this model: target protocols differ.

## Attribution and distribution
Mendeley Data v1 DOI 10.17632/k435zc736t.1, CC BY 4.0 source experiment. Historical replay is deliberately separate from model artifacts. Begin PRIVATE; public model licensing requires owner review. Frozen inference module checks compatible scikit-learn version and artifact hashes before joblib deserialization.

## Version and checksums

Model version: `bsf_model_b1`. Packaging: `3.0.0-rc1`. HF revision is pending upload; the local pinned registry will be populated with the actual commit SHA, never a fabricated hash or changing main. `checksums.json` covers every package file except itself.

- `models/bsf_model_b1_estimator.joblib`: `21c6d09b0ab9b8bcb762781262acb439f0dd61b6c28537c43995bf3ca7733af0`
- `models/bsf_model_b1_model_metadata.json`: `35e6329ced516c30c6ecd86dde9b188a7056667292088215a15697e2c00594c6`
- `models/bsf_model_b1_uncertainty.json`: `ecb385cfea9c13cd67cb289aa249fd8658f79a2162c21b88186e26e7abcd1b31`
- `models/bsf_b1_inference.py`: `87fd6c8dfaaafae329c28df55ae93b4e20585d175b9a33e6361b08502e357486`
