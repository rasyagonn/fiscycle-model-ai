---
name: fiscycle-water-quality-ai
summary: Two-notebook, local-first workflow for sensor QA/anomaly detection and 30-minute water-quality forecasting using Fiscycle local data and the Udanor catfish dataset.
description: Use when inspecting Fiscycle water-quality CSVs, creating model_a_anomaly_detection.ipynb or model_b_water_forecasting.ipynb, comparing local and Udanor data, evaluating models, or preparing model artifacts for future application integration.
---

# SKILL.md — Fiscycle Water Quality AI: Two-Notebook Workflow

**Read `AGENTS.md` first.** This guide is an executable *procedure*, not proof that any notebook, model or data product already exists. Owner: **Rasya (AI Engineer)**; product acceptance: **Nanda**.

## 0. Outcome and file layout

The project delivers **two notebooks**, not a package or API in this phase.

```text
fiscycle-model-ai/
├── AGENTS.md
├── SKILL.md
├── data/
│   ├── local.csv
│   └── eksternal/                  # inspect: only Udanor is approved for ML experiments
├── model_a_anomaly_detection.ipynb
├── model_b_water_forecasting.ipynb
└── models/                      # OPTIONAL after training passes evaluation
```

`data/processed/` may be created if the notebooks need a persisted, documented QA dataset. Keep original CSV files untouched. Do **not** generate `src/`, `api/`, `tests/`, large documentation trees, or many notebooks by default.

### Target results

| Capability | Operator question | Input | Output | What counts as progress |
|---|---|---|---|---|
| **A — Sensor QA + optional Anomaly ML** | “Is this sensor reading trustworthy?” | Timestamp, pond ID, pH, temperature, turbidity, recent history | `VALID`, `SENSOR_ERROR`, `SUSPICIOUS`, `STALE` or `INSUFFICIENT_DATA` plus reason(s) | Known invalid readings correctly flagged; any Isolation Forest incremental benefit verified |
| **B — 30-minute Forecasting** | “What might pH, temperature and turbidity be 30 minutes from now?” | Only valid, timestamped historical readings through `t` | Forecast per eligible parameter at `t+30 min` and observed coverage/limitations | Better than last-valid-value baseline on untouched local test period |

These are **data quality / parameter forecasting** capabilities, **not** whole-pond safety certification. No DO/TAN/ammonia or automatic aerator actions without new measured inputs and validated scope.

## 1. Phase 0 — Dataset inventory and readiness (do this first)

1. Inspect actual contents of `data/`; count real files. Do not infer Udanor's local filenames from its public title.
2. Read `data/local.csv` conservatively: detect delimiter, encoding, decimal/thousands conventions, original headers, data types, timestamp parsing, missing and duplicate records.
3. List and inspect `data/eksternal/` metadata; identify Udanor by actual provenance/content. **Do not train on the other candidates.** If Udanor is not present, label it *missing* and continue local-only audit.
4. For **each approved source/pond**, report row count, time span, cadence and gaps, nulls, impossible values, potential sensor clipping/flatlining, and parameter units.
5. Document the provenance and license of the exact Udanor files/version, or flag as unresolved.
6. Obtain confirmation for **local turbidity unit**, timezone, sensor calibration and changes. Unknowns are blockers for some cross-source features, not permission to guess.
7. Finish with `GO`, `CONDITIONAL GO`, or `BLOCKED` for each model and for cross-source training, explaining evidence. **STOP here** when the task is an audit only.

Prior audit notes to **verify**, not assume: local `Waktu`, `pH`, `Suhu`, `Turbidity`, `Sisa Pakan`; possible `-127°C`; mixed comma/dot number formats; irregular gaps; no local DO or TAN.

## 2. Canonical data contract — after inspecting actual schema

Work toward a consistent, source-aware table. Suggested columns (adapt to actual files):

| Column | Meaning |
|---|---|
| `source_dataset` | `fiscycle_local` / `udanor_public` |
| `source_pond_id` | Unique pond ID *within* source, never a shared unlabeled `01` |
| `source_row_id` | Original row/index/file reference |
| `timestamp` | Parsed measurement time with timezone handling documented |
| `ph` | pH, dimensionless |
| `temperature_c` | Water temperature in °C |
| `turbidity_value`, `turbidity_unit` | Do not equate unknown scale with NTU |
| `qa_status`, `qa_reasons` | Derived QA status and reason codes |
| `data_origin` | Local recorded / public recorded |

Preserve raw columns separately or alongside derived columns. Never fill absent DO/TAN with `0`. Handle malformed numbers without inventing corrected readings. Summarize field-level coverage and exclusions.

**Resampling:** if necessary, consider an agreed cadence (e.g., 3 minutes), but decide based on *observed* intervals. Aggregate only within a source + pond, preserve missingness/gap flags, and do not forward-fill across long outages. A Udanor 5-second stream and local ~3-minute stream must not be naively concatenated into an artificial continuous series.

## 3. Notebook A — `model_a_anomaly_detection.ipynb`

Use readable, numbered Markdown sections and executable cells:

1. **Objective / scope / provenance:** what is and is not being detected.
2. **Imports and reproducibility:** package versions, seeds, paths relative to repository root.
3. **Load and audit local data:** shape, schema, timestamp distribution, quality charts.
4. **Inspect Udanor separately:** select only compatible source files, document unit differences.
5. **Deterministic sensor QA:** unknown/missing, invalid timestamps, known sentinel (`-127°C`), impossible values, stale/gap conditions, suspicious flatline or clipping (not always a proven fault). Keep status **and** reason.
6. **Build review/test fixtures:** invalid examples from real logs and independently checked or manually reviewed examples; distinguish rules-derived labels from independent ground truth.
7. **Optional Isolation Forest experiment:** lag/delta/rolling features calculated within source+pond; fit without holdout leakage, review flagged anomalies with operators, compare to rules-only.
8. **Evaluation:** known-invalid test cases, reviewed anomalies, precision/recall where justified, false alarms per pond/day, confirmed incremental model findings.
9. **Decision:** rules-only vs rules+ML. If no validated ML gain, say `ML_NO_GO` without hiding it.
10. **Export only if needed:** a deterministic, documented QA result for Model B (e.g. `data/processed/local_qa.csv`), with preserved source IDs and QA version. Optional model export only if model passes review.

**Important:** Isolation Forest detects deviations from its training distribution; it cannot by itself distinguish a real water-quality event from a sensor fault. Never directly map its anomaly flag to “fish in danger.”

## 4. Notebook B — `model_b_water_forecasting.ipynb`

1. **Objective / prediction time:** predict **30 minutes ahead** for pH, temperature °C, and turbidity *only when its unit/quality are suitable*.
2. **Load data / provenance:** load local raw and the deterministic QA artifact from Notebook A, or reproducibly re-run the same documented QA rules. **Do not use Isolation Forest labels trained on future/test data as target-filtering features.**
3. **Local time-series EDA:** seasonality, gaps, distribution and data availability for each target.
4. **Chronological split before fitting learned transforms:** earlier training block, following validation block, later **untouched local test block**. Record exact dates and number of usable sequences. Do not randomly shuffle individual timestamp rows.
5. **Feature engineering:** source+pond-specific lags, moving mean/std, rate of change, time-of-day (if appropriate), gap/coverage indicators. Features must be observable by time `t`.
6. **Target construction:** pair features at `t` with actual measurement around `t+30min` using explicit temporal matching/tolerance; drop ambiguous matches and windows crossing large gaps or split boundaries. A fixed `shift(-10)` is **not valid** unless cadence is verified regular.
7. **Baselines:** last valid reading/persistence; optionally rolling-average forecast. Document baseline metrics.
8. **Candidate supervised ML:** `HistGradientBoostingRegressor` initially; train separate targets if necessary. Tune only with training/validation data and record versions and settings.
9. **Three optional training regimes:** (i) `LOCAL_ONLY` **first**; (ii) `LOCAL_PLUS_UDANOR` only for proven compatible features/units; (iii) source pretraining/adaptation if practical. Never force a merge. Keep pond/source IDs; no cross-pond windows.
10. **Final local evaluation:** same holdout for all contenders; report MAE, RMSE, bias, valid-forecast coverage per parameter and performance around rapid changes. Compare % MAE improvement over persistence. Aim for **≥10% improvement** as a *proposed stretch target*, not a guaranteed achievement.
11. **GO/NO-GO:** deployable only for individually passing targets. If learned forecasting adds no reliable benefit, document baseline/trend instead of labeling ML as validated.
12. **Save only approved artifacts:** model, feature order, preprocessing state, units, horizon, split and metrics metadata under `models/` if needed.

### Comparing the two datasets

- **Model A:** local QA first; Udanor can be inspected as an out-of-domain challenge set. Do not conflate anomalous water readings with sensor errors.
- **Model B:** test local-only before any combination. If local turbidity scale is not comparable to Udanor NTU, **do not combine that target across datasets**; local-only turbidity forecasting remains possible.
- If a combined dataset is justified, do a **vertical concatenation after harmonization**, not a timestamp join, and prove improvement on held-out **local** data.
- Udanor may have DO, but **do not create a local DO target or claim local DO sensing.**

## 5. Quality gates and minimum evidence

| Gate | Required evidence | Action on failure |
|---|---|---|
| **Data ready** | Parsed files; units/provenance; QA summary; leakage-safe usable windows | Stop training or restrict features |
| **QA baseline works** | Known errors excluded; reason codes auditable; test fixtures pass | Fix deterministic rules first |
| **Model A adds value** | Confirmed incremental findings and sustainable false-alarm load | Ship rules-only; label ML experimental |
| **Forecast beats baseline** | Per-target MAE vs persistence on untouched local holdout | Do not claim model superiority; keep baseline |
| **Responsible output** | Recorded data labeled as historical; absent parameters shown unavailable | Block unsupported claims |
| **Reproducibility** | Notebook top-to-bottom execution and documented environment, seeds, split dates | Fix notebook before handoff |

**MVP product acceptance:** An operator can see why a measurement is rejected or needs review; if a forecasting target passes evaluation, the operator can see its 30-minute estimate and limitations. No requirement to implement UI/API in the notebooks phase.

## 6. Notebook standards and handoff

- Keep **exactly two main notebooks**; avoid creating a new notebook for each experiment.
- Ensure cells run top to bottom in a clean kernel. No reliance on hidden notebook state or machine-specific absolute paths.
- Clearly label `OBSERVED`, `RULE-BASED`, `ML EXPERIMENT`, and `NOT VALIDATED` in tables and visualizations.
- Save critical metrics, split boundaries, run configuration and exclusion counts within the notebook; if necessary save a compact CSV/JSON companion artifact.
- Provide a brief note at the end of each notebook: input files, steps executed, metrics, blockers, and reproducing instructions.
- Do not create FastAPI, Docker, cloud deployment, full MLOps, or new services unless explicitly requested after model validation.

## 7. First prompt to execute

> Inspect the current `fiscycle-model-ai` repository. Read `AGENTS.md` and this `SKILL.md`. Audit `data/local.csv` and identify the actual Udanor files under `data/eksternal/`. Report real schemas, units, timestamp coverage/gaps, QA issues, licenses, and compatibility. Do **not** merge, train, create an API, or build extra project scaffolding yet. Then recommend whether Model A or Model B can start, citing observed file evidence. Stop after the Phase 0 report.
