"""Bounded, reproducible local-only research. Run from the final MVP notebook."""
from __future__ import annotations

import importlib
import io
import json
import math
import platform
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import psutil
from sklearn.ensemble import HistGradientBoostingRegressor, IsolationForest
from xgboost import XGBRegressor
from lightgbm import LGBMRegressor
from threadpoolctl import threadpool_limits

from water_quality import (ROOT, DATA, MODELS_DIR, WATER_ROOT, VERSION, PARAMETERS, HORIZONS, FEATURES, LIMITATIONS,
                           load_local, apply_qa, feature_frame, make_targets, sha256,
                           WaterQualityEngine, HistoricalReplay)

HERE = Path(__file__).resolve().parent
RESEARCH = HERE / "research"
MODELS = MODELS_DIR
TRAIN_END = pd.Timestamp("2026-10-12")
VALID_END = pd.Timestamp("2026-10-18")
CAL_END = pd.Timestamp("2026-10-22")
EVAL_END = pd.Timestamp("2026-10-29")
PERIODS = {"train": (pd.Timestamp("2026-08-22"), TRAIN_END),
           "validation": (TRAIN_END, VALID_END), "calibration": (VALID_END, CAL_END),
           "historical_evaluation": (CAL_END, EVAL_END)}
WARMUP = pd.Timedelta(seconds=3690)  # 60 minutes + lag tolerance
EMBARGO = pd.Timedelta(seconds=7290)  # maximum horizon 120 minutes + target tolerance


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str, allow_nan=False), encoding="utf-8")


def metrics(y, pred):
    err = np.asarray(pred) - np.asarray(y)
    return {"MAE": float(abs(err).mean()), "RMSE": float(np.sqrt((err ** 2).mean())), "bias": float(err.mean())}


def improvement(base, model):
    return 100 * (base - model) / base if base else 0.


def partition(frame):
    out = {}
    for name, (start, end) in PERIODS.items():
        mask = (frame.timestamp >= start + WARMUP) & (frame.timestamp < end - EMBARGO) & (frame.target_timestamp < end)
        out[name] = frame[mask].copy()
        assert len(out[name]) > 100, (name, len(out[name]))
        assert out[name].target_timestamp.max() < end
        assert out[name].timestamp.min() - WARMUP >= start
    return out


def candidate_configs():
    return {
        "HistGradientBoosting": [dict(learning_rate=.05, max_iter=200, max_leaf_nodes=15, l2_regularization=1.),
                                  dict(learning_rate=.03, max_iter=300, max_leaf_nodes=15, l2_regularization=1.)],
        "XGBoost": [dict(n_estimators=300, max_depth=4, learning_rate=.05, min_child_weight=5, subsample=.9, colsample_bytree=.9, reg_lambda=1.),
                    dict(n_estimators=500, max_depth=3, learning_rate=.03, min_child_weight=10, subsample=.8, colsample_bytree=.9, reg_lambda=3.)],
        "LightGBM": [dict(n_estimators=300, num_leaves=31, learning_rate=.05, min_child_samples=30, subsample=.9, colsample_bytree=.9, reg_lambda=1.),
                     dict(n_estimators=500, num_leaves=15, learning_rate=.03, min_child_samples=50, subsample=.8, colsample_bytree=.9, reg_lambda=3.)]}


def estimator(name, cfg):
    if name == "HistGradientBoosting":
        return HistGradientBoostingRegressor(random_state=42, early_stopping=False, **cfg)
    if name == "XGBoost":
        return XGBRegressor(random_state=42, n_jobs=1, tree_method="hist", **cfg)
    return LGBMRegressor(random_state=42, n_jobs=1, verbosity=-1, subsample_freq=1, deterministic=True, force_col_wise=True, **cfg)


def latency(model, x, repeats=30):
    model.predict(x)
    times = []
    for _ in range(repeats):
        start = time.perf_counter()
        model.predict(x)
        times.append((time.perf_counter() - start) * 1000)
    return {"p50_ms": float(np.percentile(times, 50)), "p95_ms": float(np.percentile(times, 95)), "repeats": repeats}


def blocks(y, pred, base):
    return [{"block": i + 1, "rows": len(idx), **metrics(np.asarray(y)[idx], np.asarray(pred)[idx]),
             "improvement_pct": improvement(metrics(np.asarray(y)[idx], np.asarray(base)[idx])["MAE"],
                                             metrics(np.asarray(y)[idx], np.asarray(pred)[idx])["MAE"])}
            for i, idx in enumerate(np.array_split(np.arange(len(y)), 3))]


def anomaly_research(qa):
    f = feature_frame(qa, allow_suspicious=True).dropna(subset=FEATURES).copy()
    train = f[(f.timestamp < TRAIN_END) & f.qa_status.eq("VALID")]
    model = IsolationForest(n_estimators=300, contamination=.01, random_state=42, n_jobs=1).fit(train[FEATURES])
    f["if_score"] = model.decision_function(f[FEATURES])
    f["if_flag"] = f.if_score < 0
    delta_cols = []
    for p in PARAMETERS:
        col = f"{p}_delta3"
        f[col] = f[p] - f[f"{p}_lag_3m"]
        delta_cols.append(col)
    train_deltas = f.loc[train.index, delta_cols]
    center = train_deltas.median()
    scale = (train_deltas - center).abs().median() * 1.4826
    scale = scale.clip(lower=pd.Series([.01, .01, .1], index=delta_cols))
    f["stat_score"] = ((f[delta_cols] - center).abs() / scale).max(axis=1)
    f["stat_flag"] = f.stat_score > 6
    rows = []
    for name, (start, end) in PERIODS.items():
        z = f[(f.timestamp >= start + WARMUP) & (f.timestamp < end)]
        rows.append({"split": name, "rows": len(z), "if_alerts": int(z.if_flag.sum()), "if_rate": float(z.if_flag.mean()),
                     "statistical_alerts": int(z.stat_flag.sum()), "qa_suspicious": int(z.qa_status.eq("SUSPICIOUS").sum()),
                     "if_overlap_qa": int((z.if_flag & z.qa_status.eq("SUSPICIOUS")).sum()),
                     "if_incremental_unverified": int((z.if_flag & z.qa_status.eq("VALID")).sum())})
    daily = f.assign(day=f.timestamp.dt.strftime("%Y-%m-%d")).groupby("day").agg(rows=("if_flag", "size"), if_alerts=("if_flag", "sum"), statistical_alerts=("stat_flag", "sum"))
    daily.to_csv(RESEARCH / "anomaly_daily.csv")
    review = f[f.timestamp >= CAL_END].nsmallest(12, "if_score")[["source_row_id", "timestamp", "qa_status", *PARAMETERS, *delta_cols, "if_score", "if_flag", "stat_score"]]
    review.to_csv(RESEARCH / "anomaly_review.csv", index=False)
    joblib.dump(model, RESEARCH / "isolation_forest_v2.joblib", compress=3)
    result = {"status": "EXPERIMENTAL_ONLY", "application_packaged": False, "feature_schema": FEATURES,
              "train_rows": len(train), "train_end": str(train.timestamp.max()), "summary": rows,
              "qa_counts": {str(k): int(v) for k, v in qa.qa_status.value_counts().items()},
              "statistical_baseline": {"method": "train median/MAD of 3-minute deltas; max robust z > 6", "center": center.to_dict(), "scale": scale.to_dict()},
              "previous_if": "Original notebook: 0 alerts / 3297 later rows; different 12-feature/QA/split definition, not a direct superiority comparison.",
              "precision": None, "recall": None, "false_alert_rate": None,
              "decision": "No independently verified incremental value. QA operational; IF retained as research opt-in outside models/."}
    write_json(RESEARCH / "model_a_results.json", result)
    return result


def run_experiment():
    RESEARCH.mkdir(exist_ok=True)
    original = WATER_ROOT
    # Preserve the original audit baseline, excluding this run's v2 outputs.
    protected = json.loads((RESEARCH / "preserved_hashes.json").read_text(encoding="utf-8"))
    assert all(sha256(ROOT / p) == digest for p, digest in protected.items()), "Original research changed before training"
    environment = {"python": platform.python_version(), **{n: importlib.import_module(n).__version__ for n in ["numpy", "pandas", "sklearn", "xgboost", "lightgbm", "joblib", "nbformat", "nbconvert"]}}
    write_json(RESEARCH / "environment.json", environment)
    qa = apply_qa(load_local())
    f = feature_frame(qa)
    audit = {"rows": len(qa), "start": str(qa.timestamp.min()), "end": str(qa.timestamp.max()),
             "raw_sha256": sha256(DATA), "qa_counts": {str(k): int(v) for k, v in qa.qa_status.value_counts().items()},
             "complete_feature_rows": int(f[FEATURES].notna().all(axis=1).sum()), "timezone": "Asia/Jakarta",
             "timezone_abbreviation": "WIB", "utc_offset": "+07:00",
             "turbidity_unit": "NTU", "unit_basis": "Product Owner confirmation in final implementation request",
             "external_training": False, "external_files_inventory_only": len(list((original / "data/eksternal").glob("*.csv")))}
    write_json(RESEARCH / "audit.json", audit)
    print("AUDIT", audit, flush=True)
    with threadpool_limits(limits=1):
        a_result = anomaly_research(qa)
        print("MODEL A", a_result["summary"], flush=True)
        return _forecast_experiment(qa, f, protected, environment, audit, a_result)


def _forecast_experiment(qa, f, protected, environment, audit, a_result):
    configs = candidate_configs()
    protocol = {"version": VERSION, "seed": 42, "periods": {k: [str(a), str(b)] for k, (a, b) in PERIODS.items()},
                "feature_schema": FEATURES, "feature_version": "elapsed_time_v2_strict_qa_segments",
                "target_tolerance_seconds": 90, "warmup_seconds": 3690, "end_embargo_seconds_all_horizons": 7290,
                "configs": configs, "selection": "Validation MAE; prefer HGB within 2% of best; require >=10% gain and positive gain in >=2/3 validation blocks. Historical gate >=10% and >=2/3 blocks; otherwise persistence, never switch to another historical winner.",
                "resource_gate": "serialized size <=10 MiB and prepared-row prediction p95 <=100 ms; full pipeline measured separately",
                "interval": "ceil((n+1)*0.90)-th absolute calibration residual; >=200 rows. Empirical historical coverage <0.80 -> UNAVAILABLE without tuning; no exchangeability guarantee.",
                "replay_period": "Only inference origins after calibration ends (2026-10-22) are demonstrated/evaluated out of fitting/calibration. Earlier replay is explicitly unsupported by this package.",
                "not_independent": "All local historical data have previously been examined. This is retrospective and its gates are descriptive."}
    write_json(RESEARCH / "protocol.json", protocol)
    trials, benchmarks, block_rows, selected, entries, split_rows, chart_rows = [], [], [], [], [], [], []
    objects = {}
    for h in HORIZONS:
        d = make_targets(f, h)
        parts = partition(d)
        for name, z in parts.items():
            denominator = int(((qa.timestamp >= PERIODS[name][0] + WARMUP) & (qa.timestamp < PERIODS[name][1] - EMBARGO)).sum())
            split_rows.append({"horizon": h, "split": name, "rows": len(z), "start": str(z.timestamp.min()),
                               "end": str(z.timestamp.max()), "target_end": str(z.target_timestamp.max()),
                               "all_input_rows_in_period": denominator, "valid_forecast_coverage": len(z) / denominator})
        tr, va, ca, ev = [parts[k] for k in PERIODS]
        fit = pd.concat([tr, va]).sort_values("timestamp")
        assert fit.target_timestamp.max() < VALID_END and ca.timestamp.min() >= VALID_END + WARMUP
        for p in PARAMETERS:
            ycol = f"target_{p}"
            yv, ye = va[ycol].to_numpy(), ev[ycol].to_numpy()
            bv, be = va[p].to_numpy(), ev[p].to_numpy()
            base_v, base_e = metrics(yv, bv), metrics(ye, be)
            family_rows, fitted, val_blocks = {}, {}, {}
            for family, space in configs.items():
                scores = []
                for cid, cfg in enumerate(space):
                    start = time.perf_counter()
                    model = estimator(family, cfg).fit(tr[FEATURES], tr[ycol])
                    elapsed = time.perf_counter() - start
                    vp = model.predict(va[FEATURES])
                    vm = metrics(yv, vp)
                    scores.append((vm["MAE"], cid, cfg, vp, vm))
                    trials.append({"parameter": p, "horizon": h, "algorithm": family, "config_id": cid, **vm, "train_seconds": elapsed})
                _, cid, cfg, vp, vm = min(scores, key=lambda v: v[0])
                start = time.perf_counter()
                rss_before = psutil.Process().memory_info().rss
                final = estimator(family, cfg).fit(fit[FEATURES], fit[ycol])
                seconds = time.perf_counter() - start
                rss_delta = max(0, psutil.Process().memory_info().rss - rss_before)
                ep = final.predict(ev[FEATURES])
                em = metrics(ye, ep)
                blob = io.BytesIO(); joblib.dump(final, blob, compress=3)
                timing = latency(final, ev.iloc[[0]][FEATURES])
                vb, eb = blocks(yv, vp, bv), blocks(ye, ep, be)
                val_blocks[family] = vb
                for split, bs in [("validation", vb), ("historical_evaluation", eb)]:
                    block_rows.extend({"parameter": p, "horizon": h, "algorithm": family, "split": split, **b} for b in bs)
                r = {"parameter": p, "horizon": h, "algorithm": family, "config_id": cid,
                     "validation_MAE": vm["MAE"], "validation_RMSE": vm["RMSE"], "validation_bias": vm["bias"],
                     "validation_improvement_pct": improvement(base_v["MAE"], vm["MAE"]),
                     **em, "persistence_MAE": base_e["MAE"], "persistence_RMSE": base_e["RMSE"],
                     "improvement_pct": improvement(base_e["MAE"], em["MAE"]), "refit_seconds": seconds,
                     "serialized_bytes": len(blob.getvalue()), "rss_delta_bytes_not_peak": rss_delta,
                     "p50_ms": timing["p50_ms"], "p95_ms": timing["p95_ms"],
                     "validation_positive_blocks": sum(b["improvement_pct"] > 0 for b in vb),
                     "historical_positive_blocks": sum(b["improvement_pct"] > 0 for b in eb)}
                benchmarks.append(r); family_rows[family] = r; fitted[family] = final
            winner = min(family_rows, key=lambda k: family_rows[k]["validation_MAE"])
            if family_rows["HistGradientBoosting"]["validation_MAE"] <= family_rows[winner]["validation_MAE"] * 1.02:
                winner = "HistGradientBoosting"
            chosen = family_rows[winner]
            gates = {"validation_gain": chosen["validation_improvement_pct"] >= 10,
                     "validation_stability": chosen["validation_positive_blocks"] >= 2,
                     "historical_gain": chosen["improvement_pct"] >= 10,
                     "historical_stability": chosen["historical_positive_blocks"] >= 2,
                     "size": chosen["serialized_bytes"] <= 10 * 1024**2,
                     "latency": chosen["p95_ms"] <= 100}
            use_ml = all(gates.values())
            algorithm = winner if use_ml else "Persistence"
            cp = fitted[winner].predict(ca[FEATURES]) if use_ml else ca[p].to_numpy()
            ep = fitted[winner].predict(ev[FEATURES]) if use_ml else be
            residuals = np.sort(abs(ca[ycol].to_numpy() - cp))
            k = math.ceil((len(residuals) + 1) * .90)
            radius = float(residuals[min(k, len(residuals)) - 1])
            coverage = float((abs(ye - ep) <= radius).mean())
            interval = {"method": "chronological_split_absolute_residual", "target_coverage": .90,
                        "status": "EXPERIMENTAL_CALIBRATED" if len(ca) >= 200 and coverage >= .80 else "UNAVAILABLE",
                        "radius": radius, "empirical_coverage": coverage, "average_width": 2 * radius,
                        "calibration_rows": len(ca), "calibration_start": str(ca.timestamp.min()),
                        "calibration_target_end": str(ca.target_timestamp.max()), "evaluation_rows": len(ev),
                        "limitation": "Autocorrelation/distribution shift; 90% is a target, not a guarantee or per-prediction confidence."}
            model_id = f"{p}_{h}m_v2"
            row = {"parameter": p, "horizon": h, "algorithm": algorithm, "validation_candidate": winner,
                   **metrics(ye, ep), "persistence_MAE": base_e["MAE"],
                   "improvement_pct": improvement(base_e["MAE"], metrics(ye, ep)["MAE"]),
                   "candidate_improvement_pct": chosen["improvement_pct"], "coverage": coverage, "interval_width": 2 * radius,
                   "interval_status": interval["status"], "p50_ms": chosen["p50_ms"] if use_ml else 0.,
                   "p95_ms": chosen["p95_ms"] if use_ml else 0., "rows": len(ev),
                   "status": "MVP_REPLAY_APPROVED" if use_ml else "MVP_REPLAY_BASELINE"}
            selected.append(row)
            entry = {"model_id": model_id, "version": VERSION, "parameter": p, "horizon_minutes": h,
                     "algorithm": algorithm, "status": row["status"], "path": f"{model_id}.joblib" if use_ml else None,
                     "sha256": None, "feature_schema": FEATURES, "interval": interval,
                     "training_provenance": {"dataset": "fiscycle_local_recorded", "sha256": sha256(DATA), "rows": len(fit),
                                             "start": str(fit.timestamp.min()), "target_end": str(fit.target_timestamp.max())},
                     "validation": {"selected_candidate": winner, "MAE": chosen["validation_MAE"],
                                    "improvement_pct": chosen["validation_improvement_pct"], "gates": gates},
                     "historical_evaluation": row, "inference_latency": {"prepared_row_p50_ms": row["p50_ms"], "prepared_row_p95_ms": row["p95_ms"]},
                     "known_limitations": LIMITATIONS}
            entries.append(entry)
            if use_ml:
                objects[model_id] = fitted[winner]
            for j in range(len(ev)):
                chart_rows.append({"timestamp": ev.timestamp.iloc[j], "target_timestamp": ev.target_timestamp.iloc[j],
                                   "parameter": p, "horizon": h, "actual": ye[j], "prediction": ep[j],
                                   "lower": ep[j] - radius, "upper": ep[j] + radius, "interval_status": interval["status"]})
            print("SELECT", p, h, algorithm, "MAE", round(row["MAE"], 5), "gain", round(row["improvement_pct"], 2), "coverage", round(coverage, 3), flush=True)
    for name, rows in [("trials", trials), ("benchmarks", benchmarks), ("temporal_blocks", block_rows), ("selected_summary", selected), ("splits", split_rows)]:
        pd.DataFrame(rows).to_csv(RESEARCH / f"{name}.csv", index=False)
    MODELS.mkdir(exist_ok=True)
    expected = {"manifest.json", *[e["path"] for e in entries if e["path"]]}
    existing = {p.name for p in MODELS.iterdir()}
    if existing - expected:
        raise RuntimeError(f"Existing models directory contains unrelated files; preserved, review required: {existing - expected}")
    for e in entries:
        if e["path"]:
            joblib.dump(objects[e["model_id"]], MODELS / e["path"], compress=3)
            e["sha256"] = sha256(MODELS / e["path"])
    manifest = {"version": VERSION, "mode": "historical_replay", "feature_schema": FEATURES,
                "feature_version": "elapsed_time_v2_strict_qa_segments", "timezone": "Asia/Jakarta",
                "timezone_abbreviation": "WIB", "utc_offset": "+07:00",
                "timestamp_semantics": "naive local wall-clock interpreted as WIB", "turbidity_unit": "NTU",
                "models": entries, "source_hash": sha256(DATA), "environment": environment,
                "inference_module_sha256": sha256(HERE / "water_quality.py"),
                "minimum_replay_origin": CAL_END.isoformat(), "latest_recorded_timestamp": audit["end"],
                "anomaly": {"status": "EXPERIMENTAL_ONLY", "packaged": False},
                "selection_protocol": protocol, "limitations": LIMITATIONS}
    write_json(MODELS / "manifest.json", manifest)
    engine = WaterQualityEngine()
    example_rows = qa[(qa.timestamp >= CAL_END) & (qa.timestamp < EVAL_END)]
    example = None
    for _, segment in feature_frame(example_rows).groupby("segment"):
        if len(segment) >= 100:
            end = segment.timestamp.iloc[99]
            history = load_local()
            history = history[(history.timestamp >= end - pd.Timedelta(hours=3)) & (history.timestamp <= end)]
            payload = {"pond_id": "fiscycle_local_pond_unknown", "mode": "historical_replay", "current_timestamp": end.isoformat(),
                       "readings": [{"timestamp": r.timestamp.isoformat(), **{p: float(getattr(r, p)) for p in PARAMETERS}} for r in history.itertuples()]}
            example = engine.infer(payload)
            if example["forecasts"]["ph"]["30"]["value"] is not None:
                break
    assert example and example["forecasts"]["ph"]["30"]["value"] is not None
    write_json(RESEARCH / "replay_input_example.json", payload)
    write_json(RESEARCH / "replay_output_example.json", example)
    times = []
    for _ in range(40):
        start = time.perf_counter(); engine.infer(payload); times.append((time.perf_counter() - start) * 1000)
    e2e = {"p50_ms": float(np.percentile(times, 50)), "p95_ms": float(np.percentile(times, 95)), "repeats": 40,
           "input_rows": len(history), "scope": "cached model load; input parsing, QA, features, nine forecasts, intervals and decision support",
           "hardware": platform.processor(), "rss_process_bytes": psutil.Process().memory_info().rss}
    assert e2e["p95_ms"] < 1000, "Replay performance exceeds provisional 1-second budget"
    write_json(RESEARCH / "end_to_end_latency.json", e2e)
    replay_start = pd.Timestamp(payload["readings"][0]["timestamp"])
    replay = HistoricalReplay(engine, load_local(), start=replay_start, end=replay_start + pd.Timedelta(hours=4))
    replay.start()
    count = 0
    while replay.next() is not None:
        count += 1
    replay.stop()
    pd.DataFrame(replay.comparisons).to_csv(RESEARCH / "replay_comparisons.csv", index=False)
    write_json(RESEARCH / "replay_run.json", {"observations": count, "forecasts": len(replay.predictions), "completed_comparisons": len(replay.comparisons),
                                             "matched": sum(r["status"] == "MATCHED" for r in replay.comparisons), "start": str(replay_start)})
    chart = pd.DataFrame(chart_rows)
    chart.to_csv(RESEARCH / "historical_predictions.csv", index=False)
    plot_results(chart, selected)
    assert all(sha256(ROOT / p) == digest for p, digest in protected.items()), "Original research changed"
    print("PRESERVED", len(protected), "original files; E2E", e2e, flush=True)
    return {"audit": audit, "anomaly": a_result, "selected": selected, "latency": e2e, "manifest": manifest}


def plot_results(chart, selected):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, 3, figsize=(17, 10))
    for i, p in enumerate(PARAMETERS):
        for j, h in enumerate(HORIZONS):
            z = chart[(chart.parameter == p) & (chart.horizon == h)].iloc[:150]
            ax = axes[i, j]
            ax.plot(z.target_timestamp, z.actual, label="Observed", linewidth=.8)
            ax.plot(z.target_timestamp, z.prediction, label="Prediction", linewidth=.8)
            if z.interval_status.eq("EXPERIMENTAL_CALIBRATED").all():
                ax.fill_between(z.target_timestamp, z.lower, z.upper, alpha=.2, label="Residual interval")
            ax.set_title(f"{p} +{h}m"); ax.tick_params(axis="x", rotation=25)
    axes[0, 0].legend(fontsize=7)
    fig.suptitle("Historical retrospective evaluation; target coverage 90%, no coverage guarantee")
    fig.tight_layout(); fig.savefig(RESEARCH / "forecast_intervals.png", dpi=140); plt.close(fig)


if __name__ == "__main__":
    run_experiment()
