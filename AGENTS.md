# AGENTS.md — Fiscycle Water Quality AI MVP

> Repository: `fiscycle-model-ai/`  
> Stage: **API integration authorized — Water Quality historical replay + BSF research demo**  
> Product Owner: **Nanda** | AI Engineer: **Rasya**  
> Companion guide: `SKILL.md` at the **repository root**

## Mission

Act as a careful AI engineering assistant to Rasya. Build two **experimentally validated** Water Quality capabilities for Fiscycle, beginning with the existing datasets, not by inventing infrastructure or accuracy claims. Prioritize decisions useful to catfish-pond operators, truthful data provenance, and a reproducible result.

**Read this file and `SKILL.md` before touching the project.** Use the current implementation addendum below for filesystem placement; use the older phase sections as scientific constraints and history.

## Current implementation addendum — 5 November 2026

The earlier Phase 0 contract below is preserved as the scientific workflow history, but it no longer describes the actual filesystem or current authorization. The user has explicitly authorized a single modular FastAPI application after model evaluation. Current locations:

```text
app/                                    # one combined API entry point
.agents/skills/fiscycle-water-ai/       # Water Quality domain, data, research, models
.agents/skills/fiscycle-bsf-ai/         # BSF domain, data, research, runtime bundle
```

Keep datasets, notebooks, model artifacts, and domain validation inside their respective skill folders. Application code belongs only in root `app/`. Do not create another root `models/`, duplicate API, or mix BSF scientific claims with Water Quality. BSF HTTP outputs must remain visibly `RESEARCH_PROTOTYPE`, `NOT_FIELD_VALIDATED`, and provenance-labelled.

## Current repository contract

```text
fiscycle-model-ai/
├── AGENTS.md
├── SKILL.md
├── data/
│   ├── local.csv
│   └── eksternal/                # multiple external datasets; inspect actual contents
├── model_a_anomaly_detection.ipynb   # create when starting Model A
├── model_b_water_forecasting.ipynb   # create when starting Model B
└── models/                    # OPTIONAL: create only after validated training
```

Only `data/` is confirmed to have existed at the start. Do **not** claim the notebooks or `models/` already exist. Keep the two notebooks **separate**. Additional folders (e.g., `data/processed/`) may be created only when an actual output requires them; explain each addition. **Do not create `src/`, a separate API, a dashboard, or a package scaffold during the initial data-audit phase.**

## Locked scope

| Notebook | Goal | Mandatory baseline | Candidate ML | Permitted outcome |
|---|---|---|---|---|
| **Model A** `model_a_anomaly_detection.ipynb` | Check whether pH, temperature and turbidity readings are reliable or need inspection | Deterministic sensor QA rules | `IsolationForest` (optional experiment) | Sensor/data quality status + reasons; **not** a biological health diagnosis |
| **Model B** `model_b_water_forecasting.ipynb` | Predict pH, temperature and turbidity **30 minutes ahead**, when data permit | Persistence: last valid measurement | `HistGradientBoostingRegressor` (initial candidate; may use separate estimator per target) | Numeric forecast and qualified limitation; no unsupported safety assertion |

Do **not** add DO forecasting, TAN/ammonia estimation, fish mortality, automated aerator activation, BSF, or supply optimization under this MVP without an explicit product decision. Any operator recommendation must be **expert-reviewed rules**, clearly separated from trained ML.

## Approved sources and data rights

1. **Primary:** `data/local.csv` — local recorded Fiscycle catfish-pond measurements. Actual content must be re-inspected; don't trust prior summary counts as ground truth.
2. **External candidate:** **Udanor catfish aquaponics dataset**, found by inspecting files under `data/eksternal/`. Its exact local filenames are **unknown until inspected**. Public reference: https://doi.org/10.1016/j.dib.2022.108400
3. **All other external files:** inventory only; do **not** use in model training or claim they were used. The folder may contain approximately 10 dataset items; inspect actual counts and formats.
4. Confirm each public dataset's version, original URL, licensing/attribution, units and usage limitations before training. If unclear, mark **BLOCKED/NEEDS REVIEW** instead of assuming permission.
5. Local data may be partner-confidential. Do not upload it, commit it to a public repository, or expose it in logs without authorization. Don't modify or delete raw files.

## Data quality and harmonization invariants

- Audit local and Udanor **separately** before any combined experiments.
- Keep raw files immutable; preserve original record IDs/row IDs, timestamp, source and pond identifiers. Store any cleaned/derived output separately.
- Handle mixed decimal formats cautiously; **do not guess** ambiguous numbers. Treat temperature `-127°C` as a sensor/data error. Flag suspicious flatlines, gaps and possible clipping for review rather than asserting causes.
- Verify timezone, parameter units, pH sensor method, turbidity semantics, and equipment metadata; unknown means **UNKNOWN**, not an invented value. Udanor turbidity in NTU is not automatically equivalent to local turbidity.
- Missing DO/TAN locally remains **unavailable/null**, not `0` or a predicted observation. Never infer ammonia concentration from only pH and temperature.
- Do not confuse **historical playback** with a live feed. Label all displayed results by provenance (local recorded, public dataset, rule, ML experiment, simulated).
- If merging is justified, **concatenate compatible rows vertically** with `source_dataset` and `source_pond_id`; **never join unrelated ponds by timestamp** or create sequences across pond boundaries, source boundaries, or long gaps.

## Evaluation requirements

**Model A**
- First develop and test deterministic QA for obvious invalid values, timestamps, missingness and reasonable sensor rules.
- If testing Isolation Forest, fit only on approved training portions; use manual review / known incidents to evaluate incremental findings.
- Report confirmed true findings, false alarms per pond per day and precision/recall **only if reliable labels exist**. If the learned model adds no verified value, ship **rules only** and mark ML research-only.

**Model B**
- Build features only from data available **at or before** prediction time. Respect actual timestamps when targeting `t + 30 min`; do not assume a fixed number of rows always equals 30 minutes.
- Train/validate/test chronologically on local data; keep a genuinely untouched, later **local holdout**. Never tune on it. Split by source/pond when assessing transfer and do not leak windows across gaps or split boundaries.
- Evaluate local-only first, then eligible local+Udanor or Udanor→local adaptation **only if compatibility is verified**. Compare on the **same** local holdout.
- Report per-parameter MAE, RMSE, bias, valid forecast coverage and persistence baseline. A proposed **≥10% reduction in MAE vs persistence** is a *stretch acceptance target*, not a promised result; document every target that fails.

## Working protocol — no overbuilding

1. **Phase 0:** inspect files, audit sources, identify blockers, report readiness. **No merge, training or deployment.**
2. **Phase 1:** create **Model A notebook**; build data QA, EDA, baseline and optional anomaly ML experiment.
3. **Phase 2:** create **Model B notebook**; reuse only the **deterministic QA definition / documented QA output** from Model A, never an improperly fitted ML anomaly score; train and compare forecasts.
4. **Phase 3:** only after evaluation, export versioned fitted models/preprocessing and a concise inference contract for later app integration. **Do not build an API until requested.**

Make small reproducible changes; do not indiscriminately install packages or download large files. Prefer Python + pandas + scikit-learn + matplotlib for notebook experiments. Set seeds where applicable and record environment versions. Never print secrets or report fabricated training runs, metrics or production readiness.

## Reporting after each phase

Respond in Indonesian with: **(a)** verified findings, **(b)** actual files created/changed, **(c)** data or model metrics with split definition when available, **(d)** unresolved risks, **(e)** precise next step and GO/NO-GO rationale. Distinguish *measured*, *inferred*, and *proposed* results.

**First action:** inspect `data/local.csv` and `data/eksternal/`, locate Udanor if present, and report data readiness. Stop at Phase 0 unless the current user request authorizes proceeding.
