---
name: fiscycle-bsf-growth-forecasting
description: Research and implement Fiscycle Smart BSF Model B1 for next-observation larval wet-weight forecasting from public substrate-moisture experiments; prevent replicate leakage and distinguish true experimental data from synthetic MVP scenarios.
---

# Fiscycle Smart BSF — Model B Skill

## Purpose
Use this skill **only when developing, reviewing, or auditing Smart BSF Model B1**. The deliverable is a reproducible experiment that estimates **mean larval wet weight (mg/larva) at the next observation (~1 day)**, not future harvest kilograms. Model A Computer Vision is a separate workstream.

## Workspace autonomy (critical)
- Existing project root: **`fiscycle-bsf-ai`**.
- **Never prescribe a fixed folder tree, filename for the notebook, or location for this skill.** Inspect the real workspace first. Organize minimally **inside that root**, retaining all existing user files.
- The package contains the raw workbook, an audit-derived CSV, this skill, and project requirements. Find their actual locations dynamically.
- If another skill already exists, inspect rather than overwrite. Follow the AI coding environment's own discovery convention for skills after inspecting it.
- **Prefer one main Jupyter notebook** for the ML experiment, with optional lightweight output artifacts; don't create unnecessary architecture.

## Dataset & scientific status
- `Impact of substrate moisture content on BSF larvae Data.xlsx`: original published experimental measurements, immutable.
- `Fiscycle_BSF_SubstrateMoisture_LongForm_400rows.csv`: *derived from original* for ease of EDA; re-validate names and values from original workbook.
- Prior audit indicated 20 independent replicates, 4 substrate-moisture treatment levels (45,55,65,75%), 20 observations per replicate, about 400 observations total. These are **not** 400 independent cultivations.
- `moisture_percent` is an experimental treatment level, not a live sensor signal, and cannot be assumed to measure actual moisture fluctuation over time.
- Fiscycle has **no Smart BSF sensors or local BSF measurements** yet; these are future development plans. Treat all model outputs as **research prototype / not field validated**.

## Mandatory workflow
1. Inspect workspace and input files; review data provenance and actual schema, including the original XLSX, before changing anything.
2. Audit sheets, units, missingness, temporal order, replicate groups, derived columns, outliers, and mismatches between source and CSV.
3. Establish prediction timestamp and target: use predictors known at t to predict average wet weight at t+1 within the **same replicate**; document exact horizon and any assumptions about scheduled sampling.
4. Prepare supervised pairs with lag features only within each replicate; never `shift` across groups, leak t+1 values, or encode group IDs as predictive numbers.
5. Reserve final test **by replicate**, ideally one replicate per moisture level, and perform group-based validation for selection/tuning. Never randomly split rows from the same replicate between train and test.
6. Train persistence and short-trend baselines; compare to Ridge and a lightweight regularized tree regressor. Do not use deep learning without evidence that it is warranted by dataset volume.
7. Report MAE and RMSE in **mg per larva**, per-moisture errors, phase-of-growth errors, and cross-validation variance. Do not manufacture metrics or selectively report wins.
8. Choose the best approach based on validation and robustness; if ML cannot beat baseline, report it and preserve a baseline fallback instead of claiming AI superiority.
9. Prepare historical replay using actual held-out experimental observations and synthetic scenario rows with explicit provenance labels (the latter **not** for training or scientific evaluation).
10. Document the reproducible notebook, exact feature schema, input bounds, inference assumptions, saved model only if justified, and all limits on deployment.

## Target, features, and leakage
- Target: **mean next-observation larval wet weight** (mg/individual).
- Candidate safe features: substrate moisture treatment, elapsed days at t, wet weight at t, previous wet weight, recent weight change, and planned forecast horizon if known at inference.
- Never use post-target samples, future water additions, future survival counts, endpoint outcomes, whole-replicate summaries computed over future data, or target-derived variables computed at t+1.
- Group identifiers are for data splits and diagnostics only, **not** predictors.
- Do not infer optimal moisture, exact watering interventions, or best harvest date from observational associations or limited experiment treatment contrasts.

## Demo policy: data source always visible
- `PUBLIC_RESEARCH_HOLDOUT`: real observation series excluded from fit/model selection. Useful for historical replay and actual test errors.
- `SYNTHETIC_SCENARIO`: artificially chosen inputs for showing a future MVP interaction; **never** considered independent evidence of biological prediction performance.
- `NOT_FIELD_VALIDATED`: apply to all results generated from this research-only model.
- No artificial live telemetry, fake sensor identifiers, farm yield claims, or hidden synthetic test set.

## Model implementation boundaries
- Single primary notebook, clean top-to-bottom execution, fixed seed, versions documented, paths portable relative to actual workspace.
- Start from easy-to-explain baselines; add only models necessary for fair comparison.
- Save artifacts including metadata if model is selected; ensure inference handles out-of-range inputs responsibly.
- No Model A, harvest-yield kg prediction, automatic irrigation, local BSF sensor integration, production API, or UI build at this phase.

## Final response required from coding AI
Report: actual observed data facts; real files used; features and target; grouped split IDs; algorithms and baseline results; held-out MAE/RMSE; any failed tests; files created and their actual paths; honest scientific limitations and next steps.
