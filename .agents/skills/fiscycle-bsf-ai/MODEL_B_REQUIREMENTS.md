# Fiscycle Smart BSF Model B — Build Requirements

## Product decision
Build a **research-only Model B1 Larval Growth Forecasting** prototype with **one main notebook**, using real public experimental data and an explicit separation between training, test replay, and synthetic demo scenarios.

**Do not prescribe a fixed directory tree.** All development stays inside the existing folder `fiscycle-bsf-ai`, which must be inspected first by the coding AI. Names and placement of generated files are decided from the actual workspace. The list below specifies **content and acceptance criteria**, not required paths.

## Files supplied
- `Impact of substrate moisture content on BSF larvae Data.xlsx` — original workbook, read-only.
- `Fiscycle_BSF_SubstrateMoisture_LongForm_400rows.csv` — research data transformed to long format for audit; must be checked against original.
- `SKILL.md` — research skill instructions; its final discovery location depends on actual coding environment and workspace.
- `PROMPT_AI_MODEL_B.md` — execution prompt.
- `README_PAKET.md` — instructions and provenance.

## Research question
Given a BSF replicate's current mean larval wet weight, recent observed history, elapsed time, and substrate moisture treatment (45/55/65/75%), **how accurately can we predict mean wet weight at the next observation (roughly one day later)?**

This question is **not**: total yield from organic waste, optimal harvest timing, or automatic sensor-based control. No local Fiscycle BSF IoT or farm data exists yet.

## Mandatory deliverables (AI determines filenames & placement)
1. **One primary notebook**: audit source workbook and derived CSV; EDA; define targets/features/horizon; create within-replicate supervised pairs; grouped splits; persistence/trend baselines; at least 2 light ML candidates; training and comparative evaluation; plots; inference function; demo exports; limitations.
2. **Historical replay data** derived exclusively from held-out real research observations, with fields identifying replicate, elapsed day, moisture treatment, observed current weight, next-step true weight, predicted weight, error, data provenance.
3. **Evaluation summary** recording actual train/development/test groups, seed, baseline and ML test MAE/RMSE, samples and units, any limitations; no fabricated metrics.
4. **Synthetic scenario demo file** with a small number of clearly tagged hypothetical input cases within the experiment's supported range. Do not mix into train/validation/test or metrics.
5. **Readable run guide** including exact commands/path discovered after inspection and Python dependencies needed.
6. **Saved lightweight estimator and metadata**, **only if justified** after evaluation; if baseline is best, report that result and avoid exporting a misleading 'better AI' model.

## Inputs & semantics
- Verify `replicate_id`, `moisture_percent`, `elapsed_days`, `larval_wet_weight_mg`, and any historical lag features in the derived dataset.
- Verify values against source workbook; document formulas/derived columns and any suspicious values.
- Treat `replicate_id` strictly as a split/group key; `moisture_percent` is a **substrate moisture treatment**, not an actual sensor time series.
- Target is `larval_wet_weight_mg` at t+1 (mg/individual). Use only t and past data for predictor features.
- Avoid future values, feature engineering across group boundaries, and target-derived leakage.

## Evaluation acceptance tests
- Source raw workbook remains untouched; processed table's 400 rows/20 groups/four treatments verified or discrepancies logged.
- Final test observations originate only from replicate groups absent from training and hyperparameter selection.
- No row-random split; CV is group-aware.
- Baseline and ML performances are reported side-by-side with MAE/RMSE units.
- Show predictions vs observations and error diagnostics by moisture treatment and age interval.
- Notebook reruns from a clean kernel, with no test data used for model choice.
- Historical replay uses held-out real measurements; synthetic demo is explicitly labeled and never counted as evidence.
- All documents disclose `NOT_FIELD_VALIDATED`; no invented field sensors, farming KPIs, deployed API, or 3–7 day accuracy claims.

## Future, explicitly out of scope
- Model A Computer Vision.
- Prediction of total harvested biomass or yield from waste input.
- Predicted optimal harvest date, optimized watering instructions, closed-loop control.
- Real-time telemetry or hardware installation at BSF facilities.
- Scaling to new substrates/sites without actual validation on those conditions.
