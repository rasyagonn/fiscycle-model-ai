"""Engineering fixtures are synthetic; they do not establish real-world anomaly accuracy."""
import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from water_quality import (ROOT, MODELS_DIR, PARAMETERS, FEATURES, load_local, apply_qa, feature_frame,
                           make_targets, number, WaterQualityEngine, HistoricalReplay, decision_support, sha256,
                           TIMEZONE, TIMEZONE_ABBREVIATION, UTC_OFFSET, TIMESTAMP_SEMANTICS)

HERE = Path(__file__).resolve().parent


def fixture(n=100):
    k = np.arange(n)
    return pd.DataFrame({"timestamp": pd.date_range("2026-10-23", periods=n, freq="3min"),
                         "ph": 7 + .05 * np.sin(k), "temperature_c": 28 + .1 * np.cos(k),
                         "turbidity_ntu": 40 + np.sin(k), "source_row_id": k})


def payload(frame):
    return {"pond_id": "fixture", "mode": "historical_replay", "current_timestamp": frame.timestamp.iloc[-1].isoformat(),
            "readings": [{"timestamp": r.timestamp.isoformat(), **{p: float(getattr(r, p)) for p in PARAMETERS}} for r in frame.itertuples()]}


@pytest.mark.parametrize("value,expected", [("7,2", 7.2), ("7.2", 7.2), ("1.234,5", None), ("1,234.5", None), (None, None), ("inf", None)])
def test_numeric_parser(value, expected):
    assert np.isnan(number(value)) if expected is None else number(value) == expected


@pytest.mark.parametrize("column,value,reason", [("temperature_c", -127, "TEMP_SENTINEL_MINUS127"),
    ("temperature_c", -300, "TEMPERATURE_BELOW_ABSOLUTE_ZERO"), ("ph", "1,2.3", "MISSING_OR_MALFORMED_PH"),
    ("turbidity_ntu", -1, "NEGATIVE_TURBIDITY")])
def test_sensor_errors(column, value, reason):
    f = fixture().astype({column: object}); f.loc[len(f)-1, column] = value
    q = apply_qa(f)
    assert q.iloc[-1].qa_status == "SENSOR_ERROR" and reason in q.iloc[-1].qa_reasons


def test_provisional_ranges_clipping_flatline_jump():
    f = fixture(); f.loc[99, "ph"] = 15
    assert apply_qa(f).iloc[-1].qa_status == "SUSPICIOUS"
    f = fixture(); f.loc[99, "turbidity_ntu"] = 100
    assert "TURBIDITY_CLIPPING_REVIEW" in apply_qa(f).iloc[-1].qa_reasons
    f = fixture(); f.loc[:, "temperature_c"] = 28
    q = apply_qa(f)
    assert q.iloc[18].qa_status == "VALID" and "FLATLINE_20_TEMPERATURE_C" in q.iloc[19].qa_reasons
    f = fixture(); f.loc[99, "ph"] += 2
    assert "JUMP_REVIEW_PH" in apply_qa(f).iloc[-1].qa_reasons


def test_causal_duplicate_and_order_timestamp():
    f = fixture(30)
    d = pd.concat([f, f.iloc[[-1]]], ignore_index=True)
    q = apply_qa(d)
    assert q.iloc[-2].qa_status == apply_qa(f).iloc[-1].qa_status
    assert q.iloc[-1].qa_status == "SENSOR_ERROR"
    f.loc[29, "timestamp"] = f.timestamp.iloc[0]
    assert "OUT_OF_ORDER_TIMESTAMP" in apply_qa(f).iloc[-1].qa_reasons
    f["timestamp"] = f.timestamp.astype(object); f.loc[29, "timestamp"] = "bad"
    assert apply_qa(f).iloc[-1].qa_status == "SENSOR_ERROR"


def test_features_prefix_invariance_and_schema():
    f = fixture()
    a = feature_frame(apply_qa(f.iloc[:70]))
    b = feature_frame(apply_qa(f))
    pd.testing.assert_frame_equal(a[FEATURES], b.iloc[:70][FEATURES])
    assert len(FEATURES) == 36 and a.iloc[-1][FEATURES].notna().all()


def test_single_invalid_breaks_history_and_target():
    f = fixture(); f.loc[50, "temperature_c"] = -127
    features = feature_frame(apply_qa(f))
    # The first returning value is itself suspicious (jump from sentinel); the next
    # eligible value must start a new, incomplete history.
    assert not features.timestamp.eq(f.timestamp.iloc[51]).any()
    assert features.loc[features.timestamp.eq(f.timestamp.iloc[52]), FEATURES].isna().any(axis=None)
    targets = make_targets(features, 30)
    crossing = (targets.timestamp < f.timestamp.iloc[50]) & (targets.target_timestamp > f.timestamp.iloc[50])
    assert not crossing.any()


def test_target_tie_rejected():
    f = fixture(100)
    # At t=60 min the requested +30 target lies exactly halfway between 88.5 and 91.5 min.
    f.loc[29, "timestamp"] = f.timestamp.iloc[0] + pd.Timedelta(minutes=88.5)
    f.loc[30, "timestamp"] = f.timestamp.iloc[0] + pd.Timedelta(minutes=91.5)
    z = make_targets(feature_frame(apply_qa(f)), 30)
    assert not z.timestamp.eq(f.timestamp.iloc[20]).any()


@pytest.fixture(scope="module")
def engine():
    return WaterQualityEngine()


def test_future_observation_and_mixed_pond_rejected(engine):
    p = payload(fixture()); p["current_timestamp"] = p["readings"][-2]["timestamp"]
    with pytest.raises(ValueError, match="Future"): engine.infer(p)
    p = payload(fixture()); p["readings"][0]["pond_id"] = "other"
    with pytest.raises(ValueError, match="Mixed pond"): engine.infer(p)


def test_no_replay_before_calibration(engine):
    p = payload(fixture()); p["current_timestamp"] = "2026-10-20"
    with pytest.raises(ValueError, match="calibration end"): engine.infer(p)


def test_stale_sensor_error_insufficient(engine):
    p = payload(fixture()); p["current_timestamp"] = "2026-10-24T05:00:00"
    r = engine.infer(p)
    assert r["data_quality"]["status"] == "STALE"
    assert all(f["value"] is None for hs in r["forecasts"].values() for f in hs.values())
    p = payload(fixture()); p["readings"][-1]["temperature_c"] = -127
    assert engine.infer(p)["data_quality"]["status"] == "SENSOR_ERROR"
    r = engine.infer(payload(fixture(5)))
    assert r["forecasts"]["ph"]["30"]["value"] is None
    assert any(i["rule_id"] == "C06_INSUFFICIENT_HISTORY" for i in r["decision_support"]["insights"])


def test_real_output_reproducible_serializable(engine):
    p = json.loads((HERE / "research/replay_input_example.json").read_text(encoding="utf-8"))
    expected = json.loads((HERE / "research/replay_output_example.json").read_text(encoding="utf-8"))
    # Contoh lama dipertahankan sebagai bukti run sebelum timezone dikonfirmasi.
    old = "Timezone UNKNOWN; timestamp lokal dipertahankan tanpa konversi."
    new = "Timezone dikonfirmasi WIB (Asia/Jakarta, UTC+07:00); timestamp internal dipertahankan sebagai wall-clock lokal tanpa konversi."
    expected["timezone"] = TIMEZONE
    expected["timezone_abbreviation"] = TIMEZONE_ABBREVIATION
    expected["utc_offset"] = UTC_OFFSET
    expected["timestamp_semantics"] = TIMESTAMP_SEMANTICS
    expected["limitations"] = [new if value == old else value for value in expected["limitations"]]
    expected["decision_support"]["limitations"] = [new if value == old else value for value in expected["decision_support"]["limitations"]]
    actual = engine.infer(p)
    assert actual == expected
    json.dumps(actual, allow_nan=False)
    for hs in actual["forecasts"].values():
        for f in hs.values():
            assert f["value"] is not None
            if f["interval_status"] != "UNAVAILABLE": assert f["lower"] <= f["value"] <= f["upper"]


def test_decision_rules_and_threshold_review_gate(engine):
    r = engine.infer(payload(fixture()))
    r["anomaly_detection"]["flag"] = True
    f = r["forecasts"]["ph"]["30"]
    f.update(value=8., lower=7.8, upper=8.2, interval_status="EXPERIMENTAL_CALIBRATED")
    cfg = {"ph": {"status": "REVIEWED", "reference": "SYNTHETIC_TEST_ONLY", "reviewer": "fixture", "upper": 7.7}}
    ds = decision_support(r, cfg)
    rules = {i["rule_id"] for i in ds["insights"]}
    assert {"C02_UNUSUAL_PATTERN", "C04_CHANGE_OUTSIDE_RESIDUAL_BAND", "C05_REVIEWED_THRESHOLD"} <= rules
    cfg["ph"]["status"] = "PROVISIONAL"
    assert not any(i["rule_id"] == "C05_REVIEWED_THRESHOLD" for i in decision_support(r, cfg)["insights"])
    f.update(lower=None, upper=None, interval_status="UNAVAILABLE")
    assert any(i["rule_id"] == "C03_INTERVAL_UNAVAILABLE" for i in decision_support(r)["insights"])


def test_offline_day_requires_rewarmup(engine):
    f = fixture(40)
    resumed = fixture(40); resumed.timestamp += pd.Timedelta(days=1)
    joined = pd.concat([f, resumed], ignore_index=True)
    r = engine.infer(payload(joined.iloc[:41]))
    assert r["data_quality"]["status"] == "STALE"
    assert engine.infer(payload(joined.iloc[:50]))["forecasts"]["ph"]["30"]["value"] is None
    assert engine.infer(payload(joined))["forecasts"]["ph"]["30"]["value"] is not None


def test_replay_stop_resume_and_comparison_protocol(engine):
    frame = fixture(65)
    replay = HistoricalReplay(engine, frame)
    assert replay.next() is None
    replay.start()
    for _ in range(35): replay.next()
    replay.stop(); index = replay.index
    assert replay.next() is None and replay.index == index
    replay.start()
    while replay.next() is not None: pass
    assert replay.comparisons
    features = feature_frame(apply_qa(frame))
    for h in [30, 60, 120]:
        offline = make_targets(features, h)
        for c in replay.comparisons:
            if c["horizon_minutes"] != h or c["status"] != "MATCHED": continue
            match = offline[offline.timestamp.eq(pd.Timestamp(c["origin"]))]
            assert len(match) == 1
            assert match.iloc[0][f'target_{c["parameter"]}'] == c["actual"]
            assert c["error"] == c["prediction"] - c["actual"]


def test_splits_and_raw_artifact_integrity():
    from train_validate import partition, PERIODS, WARMUP, EMBARGO
    qa = apply_qa(load_local()); f = feature_frame(qa)
    for h in [30, 60, 120]:
        for name, z in partition(make_targets(f, h)).items():
            start, end = PERIODS[name]
            assert (z.timestamp - WARMUP >= start).all()
            assert (z.timestamp < end - EMBARGO).all()
            assert (z.target_timestamp < end).all()
    hashes = json.loads((HERE / "research/preserved_hashes.json").read_text())
    assert all(sha256(ROOT / p) == digest for p, digest in hashes.items())


def test_app_folder_only_selected_and_hashes():
    manifest = json.loads((MODELS_DIR / "manifest.json").read_text(encoding="utf-8"))
    expected = {"manifest.json"} | {e["path"] for e in manifest["models"] if e["path"]}
    assert {p.name for p in MODELS_DIR.iterdir()} == expected
    assert all(e["status"] in ["MVP_REPLAY_APPROVED", "MVP_REPLAY_BASELINE"] for e in manifest["models"])
    assert all(sha256(MODELS_DIR / e["path"]) == e["sha256"] for e in manifest["models"] if e["path"])
    assert sha256(HERE / "water_quality.py") == manifest["inference_module_sha256"]
