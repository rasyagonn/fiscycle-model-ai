"""Auditable engineering explanations and matched-pair replay metrics, no biological limits."""
import math
from app.services.water_core import PARAMETERS, UNITS, decision_support

VERSION = "water_dss_engineering_v2"
RULES = [
    {"id": ident, "condition": condition, "version": VERSION,
     "evidence": "Existing water-replay-v2 deterministic inference contract",
     "approval_status": "ENGINEERING_VERIFICATION_ONLY", "biological_threshold": None}
    for ident, condition in [
        ("C01_INPUT_QA", "QA status != VALID; abstain forecasting"),
        ("C02_UNUSUAL_PATTERN", "Opt-in statistical anomaly flagged; default disabled"),
        ("C03_INTERVAL_UNAVAILABLE", "Forecast computed but residual interval unavailable"),
        ("C04_CHANGE_OUTSIDE_RESIDUAL_BAND", "Current measurement outside forecast residual band"),
        ("C05_REVIEWED_THRESHOLD", "Reviewed threshold with named reviewer and reference; disabled in default config"),
        ("C06_INSUFFICIENT_HISTORY", "No supported forecasts; request continuous valid history")]]


def enrich(result):
    import pandas as pd
    qa = result["data_quality"]
    latest = result.get("latest_sensor_timestamp")
    qa["age_seconds"] = (pd.Timestamp(result["current_timestamp"])-pd.Timestamp(latest)).total_seconds() if latest else None
    qa["freshness_limit_seconds"] = 600
    aliases = {"ph": ("PH",), "temperature_c": ("TEMP",), "turbidity_ntu": ("TURBID",)}
    shared = ("TIMESTAMP", "TIMEZONE", "GAP_", "NO_READINGS", "NO_RECENT")
    qa["parameters"] = {}
    for p in PARAMETERS:
        reasons = [r for r in qa["reasons"] if any(s in r for s in (*aliases[p], *shared))]
        error = any(s in r for r in reasons for s in ("MISSING", "MALFORMED", "MINUS127", "ABSOLUTE", "NEGATIVE", "INVALID", "DUPLICATE", "OUT_OF_ORDER"))
        stale = any(s in r for r in reasons for s in ("GAP_", "NO_READINGS", "NO_RECENT"))
        qa["parameters"][p] = {"value": result["current_readings"][p], "unit": UNITS[p],
            "status": "SENSOR_ERROR" if error else "STALE" if stale else "SUSPICIOUS" if reasons else "VALID",
            "reasons": reasons, "forecast_eligible": any(f["value"] is not None for f in result["forecasts"][p].values()),
            "note": "Forecast uses all three parameters; a different sensor or missing history can suppress it."}
    dss = result["decision_support"]
    dss["rule_version"] = VERSION
    dss["operational_assessment"] = "ABSTAIN_BIOLOGICAL_SAFETY"
    for recommendation in dss["recommendations"]:
        recommendation.update(rule_version=VERSION, requires_human_confirmation=True,
            approval_status="ENGINEERING_VERIFICATION_ONLY",
            missing_operational_evidence=["expert_reviewed_thresholds", "verified_sensor_calibration", "field_context"],
            limitations="Tidak ada diagnosis biologis, dosis kimia, atau perintah aktuator.")
    traces = []
    triggered = {i["rule_id"] for i in dss["insights"]}
    for rule in RULES:
        traces.append({**rule, "triggered": rule["id"] in triggered,
            "trigger_instances": [i for i in dss["insights"] if i["rule_id"] == rule["id"]],
            "inputs": {"data_quality": qa, "current_readings": result["current_readings"],
                       "forecasts": result["forecasts"], "anomaly": result["anomaly_detection"]},
            "provenance": result.get("source_dataset"), "timestamp": result["current_timestamp"],
            "units": UNITS, "threshold_config": "NO_EXPERT_APPROVED_THRESHOLDS"})
    dss["traces"] = traces
    result["provenance"] = "HISTORICAL_LOCAL_RECORDED_WITH_AI_PREDICTIONS"
    result["independent_validation"] = False
    return result


def replay_metrics(comparisons, predictions):
    rows = []
    for p in PARAMETERS:
        for h in (30, 60, 120):
            issued = [x for x in predictions if x["parameter"] == p and x["horizon_minutes"] == h]
            resolved = [x for x in comparisons if x["parameter"] == p and x["horizon_minutes"] == h]
            pairs = [x for x in resolved if x["status"] == "MATCHED"]
            n = len(pairs)
            errors = [x["error"] for x in pairs]
            baseline = [x["persistence_error"] for x in pairs]
            def score(values):
                return {"mae": sum(abs(v) for v in values)/n, "rmse": math.sqrt(sum(v*v for v in values)/n), "bias": sum(values)/n} if n else {"mae": None, "rmse": None, "bias": None}
            rows.append({"parameter": p, "horizon_minutes": h, "unit": UNITS[p], "matched": n,
                "issued": len(issued), "resolved": len(resolved), "pending": len(issued)-len(resolved),
                "coverage_among_resolved": n/len(resolved) if resolved else None,
                "prediction": score(errors), "persistence_same_pairs": score(baseline)})
    return {"scope": "RETROSPECTIVE_REPLAY_NOT_INDEPENDENT_VALIDATION", "rows": rows,
            "alignment_tolerance_seconds": 90, "unmatched_policy": "Exclude gaps, QA barriers and nearest-time ties; pending targets are not failures"}
