---
language:
- id
- en
tags:
- fiscycle
- research-prototype
- not-field-validated
---

# Fiscycle Water Quality AI — frozen MVP v2

## Purpose and architecture
Historical sensor QA and forecasting for pH, temperature and turbidity. Seven fitted estimators: HistGradientBoosting, XGBoost and LightGBM as mapped in the manifest. Two other target/horizon combinations use persistence baseline logic; they are not trained ML artifacts. Deterministic QA and DSS live in the Python AI Service, not in these estimators.

## Inputs, preprocessing and outputs
Naive local timestamps are interpreted as WIB (Asia/Jakarta). Features use only readings available at prediction time, strict QA segments, elapsed-time lags/rolling statistics and the exact 36-field order in `runtime_contract.json`. Forecasts are numeric values for +30/+60/+120 minutes. Units: pH, °C, NTU. Preserve timestamp matching tolerance and feature eligibility rules in the existing runtime.

## Saved evaluation
Retrospective local evaluation 22–28 October 2026, one pond. This period had prior exploratory exposure; it is not a new independent holdout. Local-only training for this release; Udanor was used only in separate historical transfer experiments.

|Parameter|Minutes|Selected method|MAE|Persistence MAE|MAE reduction|
|---|---:|---|---:|---:|---:|
|ph|30|HistGradientBoosting|0.105746|0.123314|14.25%|
|temperature_c|30|Persistence|0.174361|0.174361|0.00%|
|turbidity_ntu|30|HistGradientBoosting|2.220057|2.563868|13.41%|
|ph|60|XGBoost|0.113991|0.130408|12.59%|
|temperature_c|60|HistGradientBoosting|0.242302|0.282036|14.09%|
|turbidity_ntu|60|HistGradientBoosting|2.302166|2.694097|14.55%|
|ph|120|HistGradientBoosting|0.117721|0.141866|17.02%|
|temperature_c|120|LightGBM|0.360099|0.490812|26.63%|
|turbidity_ntu|120|Persistence|2.804560|2.804560|0.00%|

Evaluation pairs: 3,144 / 3,134 / 3,114 by horizon. Nominal 90% residual intervals undercover in 7/9 configurations. Interval coverage and prediction availability are separate measures.

## Intended use and limitations
Research/internal MVP historical replay. Not validated as live IoT deployment or across independent ponds. Sensor calibration remains unverified. Missing DO/TAN/ammonia remain unavailable. No fish-health certification, mortality prediction, or automatic aerator operation. Biological DSS thresholds have not been expert approved.

## Distribution
PRIVATE_ONLY. Local raw or replay sensor measurements are deliberately absent. Ownership/public model licensing requires product-owner review; no public model license is asserted. Use exact compatible Python/sklearn/XGBoost/LightGBM versions in `requirements-runtime.txt`. Load only trusted, checksum-verified joblib files.

## Version and checksums

Model version: `water-replay-v2`. Packaging: `3.0.0-rc1`. HF revision is pending upload; the local pinned registry will be populated with the actual commit SHA, never a fabricated hash or changing main. `checksums.json` covers every package file except itself.

- `models/mvp_v2/manifest.json`: `4a3d2eee1b7b7ac8c0df1d37d494a3a3f9f29cb056e30852a1884e34a11f67de`
- `models/mvp_v2/ph_120m_v2.joblib`: `9db72b34a76bedb54ba33652617a38ad194235ff43235710a77930c397e2cbcf`
- `models/mvp_v2/ph_30m_v2.joblib`: `17570b1e67726e9f3b36c8147959621d6188e57f12bebb172348de566d4cdff7`
- `models/mvp_v2/ph_60m_v2.joblib`: `8a13a40a4e9b7718ada40bc1d1c35b97bebb0cce507b3902926955a030761f7f`
- `models/mvp_v2/temperature_c_120m_v2.joblib`: `89fb90f8f640043a7287d52756316671de996c6abeedc763cf9a39f14e962c1b`
- `models/mvp_v2/temperature_c_60m_v2.joblib`: `a8efdc19f6f53c7ce87c2f58e7f41a83fda58b17151b2432d3da06787834faf2`
- `models/mvp_v2/turbidity_ntu_30m_v2.joblib`: `c81866f2a988af580a86f560e9e04064265e86f59ee68f096eb0df4cb98d88ed`
- `models/mvp_v2/turbidity_ntu_60m_v2.joblib`: `3e8ad92e5e1911bb7d556d9c995a337b2a6d72d4ee14e1da9446623c76ddb886`
