"""Fiscycle historical replay inference; no training or future target access."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

VERSION = "water-replay-v2"
TIMEZONE = "Asia/Jakarta"
TIMEZONE_ABBREVIATION = "WIB"
UTC_OFFSET = "+07:00"
TIMESTAMP_SEMANTICS = "naive local wall-clock interpreted as WIB"
WATER_ROOT = Path(__file__).resolve().parent
ROOT = WATER_ROOT.parents[2]
DATA = WATER_ROOT / "data/local.csv"
MODELS_DIR = WATER_ROOT / "models/mvp_v2"
PARAMETERS = ["ph", "temperature_c", "turbidity_ntu"]
UNITS = dict(zip(PARAMETERS, ["pH", "degC", "NTU"]))
HORIZONS = [30, 60, 120]
TOLERANCE = 90
FEATURES = PARAMETERS + [f"{p}_lag_{m}m" for m in [3, 6, 15, 30, 60] for p in PARAMETERS] + [
    f"{p}_roll{stat}_{m}m" for m in [15, 30, 60] for p in PARAMETERS for stat in ["mean", "std"]]
LIMITATIONS = ["Simulasi Data Historis; IoT tidak aktif.", "Satu kolam lokal; evaluasi retrospektif, bukan validasi independen.",
               "Timezone dikonfirmasi WIB (Asia/Jakarta, UTC+07:00); timestamp internal dipertahankan sebagai wall-clock lokal tanpa konversi.",
               "Unit NTU dikonfirmasi Product Owner; kalibrasi, konversi dan clipping sensor belum diverifikasi.",
               "DO dan TAN/amonia tidak tersedia; bukan penilaian keselamatan biologis kolam.",
               "Interval residual time series tidak memiliki jaminan coverage 90%."]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def number(value):
    if value is None or isinstance(value, bool):
        return np.nan
    s = str(value).strip()
    if not re.fullmatch(r"[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?", s):
        return np.nan
    value = float(s.replace(",", "."))
    return value if np.isfinite(value) else np.nan


def timestamp(value):
    try:
        t = pd.Timestamp(value)
        if pd.isna(t) or t.tzinfo is not None:
            return pd.NaT
        return t
    except (ValueError, TypeError):
        return pd.NaT


def load_local(path=DATA):
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    out = pd.DataFrame({"source_row_id": np.arange(len(raw)),
                        "timestamp": pd.to_datetime(raw.Waktu.str.strip(), format="%m/%d/%Y %H:%M:%S", errors="coerce")})
    for p, col in zip(PARAMETERS, ["pH", "Suhu", "Turbidity"]):
        out[p] = raw[col].map(number)
    out["source_dataset"] = "fiscycle_local_recorded"
    out["pond_id"] = "fiscycle_local_pond_unknown"
    # Keep arrival order so malformed / backwards records remain observable QA barriers.
    return out


def apply_qa(frame):
    """Causal QA: a later duplicate never changes an earlier row's status."""
    x = frame.copy().reset_index(drop=True)
    for p in PARAMETERS:
        x[p] = x[p].map(number)
    x["timestamp"] = x.timestamp.map(timestamp)
    x["gap_seconds"] = x.timestamp.diff().dt.total_seconds()
    reasons = [[] for _ in range(len(x))]
    errors = np.zeros(len(x), dtype=bool)
    stale = np.zeros(len(x), dtype=bool)

    def add(mask, reason, error=False):
        mask = np.asarray(mask, dtype=bool)
        for i in np.flatnonzero(mask):
            reasons[i].append(reason)
        if error:
            errors[mask] = True

    add(x.timestamp.isna(), "INVALID_TIMESTAMP_OR_TIMEZONE", True)
    add(x.timestamp.duplicated(keep="first") & x.timestamp.notna(), "DUPLICATE_TIMESTAMP", True)
    add(x.gap_seconds.lt(0), "OUT_OF_ORDER_TIMESTAMP", True)
    for p in PARAMETERS:
        add(x[p].isna(), f"MISSING_OR_MALFORMED_{p.upper()}", True)
    add(x.temperature_c.eq(-127), "TEMP_SENTINEL_MINUS127", True)
    add(x.temperature_c.lt(-273.15), "TEMPERATURE_BELOW_ABSOLUTE_ZERO", True)
    add(x.turbidity_ntu.lt(0), "NEGATIVE_TURBIDITY", True)
    # Plausibility policy, NOT verified sensor specifications or biological thresholds.
    add(x.ph.notna() & ~x.ph.between(0, 14), "PH_OUTSIDE_PROVISIONAL_RANGE")
    add(x.temperature_c.notna() & ~x.temperature_c.between(0, 50), "TEMP_OUTSIDE_PROVISIONAL_RANGE")
    add(x.turbidity_ntu.eq(0) | x.turbidity_ntu.ge(100), "TURBIDITY_CLIPPING_REVIEW")
    gap = x.gap_seconds.gt(600).to_numpy()
    add(gap, "GAP_GT_10_MIN")
    stale[gap] = True
    for p, jump in zip(PARAMETERS, [1., 3., 30.]):
        add(x[p].diff().abs().gt(jump) & x.gap_seconds.between(0.001, 600), f"JUMP_REVIEW_{p.upper()}")
        reset = x[p].ne(x[p].shift()) | x.gap_seconds.gt(600) | x.gap_seconds.le(0) | x[p].isna() | x.timestamp.isna()
        run = x.groupby(reset.cumsum()).cumcount() + 1
        add(run.ge(20), f"FLATLINE_20_{p.upper()}")
    x["qa_reasons"] = reasons
    x["qa_status"] = ["SENSOR_ERROR" if errors[i] else "STALE" if stale[i] else "SUSPICIOUS" if r else "VALID"
                      for i, r in enumerate(reasons)]
    return x


def feature_frame(qa, allow_suspicious=False):
    """36 causal features. Actual-time lags; trailing elapsed-time rolling statistics."""
    usable = qa.qa_status.isin(["VALID", "SUSPICIOUS"] if allow_suspicious else ["VALID"])
    q = qa.copy()
    # Every rejected observation splits the history, even an outage shorter than ten minutes.
    boundary = ~usable | ~usable.shift(fill_value=False) | q.gap_seconds.gt(600) | q.gap_seconds.le(0)
    q["segment"] = boundary.cumsum()
    frames = []
    for _, g in q[usable].groupby("segment", sort=False):
        g = g.copy().reset_index(drop=True)
        f = g.copy()
        times = g.timestamp.to_numpy(dtype="datetime64[ns]").astype("int64")
        for m in [3, 6, 15, 30, 60]:
            desired = times - m * 60 * 10**9
            r = np.searchsorted(times, desired, side="left")
            left = np.clip(r - 1, 0, len(g) - 1)
            right = np.clip(r, 0, len(g) - 1)
            dl, dr = np.abs(times[left] - desired), np.abs(times[right] - desired)
            take = np.where(dl < dr, left, right)
            ambiguous = (dl == dr) & (left != right)
            ok = (~ambiguous) & (np.minimum(dl, dr) <= TOLERANCE * 10**9) & (times[take] < times)
            for p in PARAMETERS:
                f[f"{p}_lag_{m}m"] = np.where(ok, g[p].to_numpy()[take], np.nan)
        indexed = g.set_index("timestamp")[PARAMETERS]
        for m in [15, 30, 60]:
            roll = indexed.rolling(f"{m}min", min_periods=3, closed="right")
            for stat in ["mean", "std"]:
                v = getattr(roll, stat)().reset_index(drop=True)
                for p in PARAMETERS:
                    f[f"{p}_roll{stat}_{m}m"] = v[p]
        frames.append(f)
    if not frames:
        return pd.DataFrame(columns=list(dict.fromkeys([*qa.columns, "segment", *FEATURES])))
    return pd.concat(frames, ignore_index=True)


def make_targets(features, horizon):
    """Offline evaluation only; never called by inference. Reject nearest-time ties."""
    parts = []
    for _, g in features.groupby("segment", sort=False):
        g = g.copy().reset_index(drop=True)
        times = g.timestamp.to_numpy(dtype="datetime64[ns]").astype("int64")
        desired = times + horizon * 60 * 10**9
        k = np.searchsorted(times, desired)
        a, b = np.clip(k - 1, 0, len(g) - 1), np.clip(k, 0, len(g) - 1)
        da, db = abs(times[a] - desired), abs(times[b] - desired)
        take = np.where(da < db, a, b)
        ok = (np.minimum(da, db) <= TOLERANCE * 10**9) & ~((da == db) & (a != b))
        g["target_timestamp"] = g.timestamp.iloc[take].to_numpy()
        for p in PARAMETERS:
            g[f"target_{p}"] = np.where(ok, g[p].to_numpy()[take], np.nan)
        parts.append(g)
    return pd.concat(parts, ignore_index=True).dropna(subset=FEATURES + [f"target_{p}" for p in PARAMETERS])


def decision_support(result, thresholds=None):
    """Engineering verification rules; no biological risk classification."""
    insights, recommendations, trends = [], [], []
    parameter_status = {p: "INSUFFICIENT_INFORMATION" for p in PARAMETERS}

    def add(rule, parameter, text, action, basis="PROVISIONAL_ENGINEERING_RULE"):
        insights.append({"rule_id": rule, "parameter": parameter, "explanation": text, "basis": basis})
        recommendations.append({"rule_id": rule, "parameter": parameter, "action": action, "reason": text})

    quality = result["data_quality"]["status"]
    if quality != "VALID":
        add("C01_INPUT_QA", None, "Pembacaan sensor tidak valid atau belum layak dipakai untuk prediksi.",
            "Periksa sensor, kelengkapan data dan timestamp sebelum mengambil keputusan.")
        return {"status": "VERIFY_INPUT", "parameter_status": {p: quality for p in PARAMETERS},
                "insights": insights, "recommendations": recommendations, "limitations": LIMITATIONS}
    if result["anomaly_detection"].get("flag"):
        add("C02_UNUSUAL_PATTERN", None, "Pola pengukuran tidak biasa terdeteksi dan memerlukan pemeriksaan.",
            "Verifikasi pembacaan; indikasi statistik bukan bukti gangguan sensor atau bahaya air.")
    for p, horizons in result["forecasts"].items():
        for h, f in horizons.items():
            if f.get("value") is None:
                continue
            parameter_status[p] = "FORECAST_AVAILABLE_NO_SAFETY_ASSESSMENT"
            current = result["current_readings"][p]
            delta = f["value"] - current
            trends.append({"parameter": p, "horizon_minutes": int(h), "predicted_change": delta,
                           "direction": "UP" if delta > 0 else "DOWN" if delta < 0 else "UNCHANGED",
                           "meaning": "Numeric forecast trend, not biological risk"})
            if f["interval_status"] == "UNAVAILABLE":
                add("C03_INTERVAL_UNAVAILABLE", p, "Informasi belum cukup untuk memberikan rekomendasi yang andal.",
                    "Rentang prediksi belum tersedia. Verifikasi pembacaan berikutnya.")
            elif current < f["lower"] or current > f["upper"]:
                add("C04_CHANGE_OUTSIDE_RESIDUAL_BAND", p,
                    f"Parameter diperkirakan berubah pada +{h} menit; nilai kini berada di luar rentang prediksi.",
                    "Pantau tren dan verifikasi pembacaan berikutnya; bukan ambang bahaya biologis.")
            cfg = (thresholds or {}).get(p, {})
            if cfg.get("status") == "REVIEWED" and cfg.get("reference") and cfg.get("reviewer"):
                lo, hi = cfg.get("lower"), cfg.get("upper")
                vals = [f["value"]] + ([f["lower"], f["upper"]] if f["lower"] is not None else [])
                if (lo is not None and min(vals) <= lo) or (hi is not None and max(vals) >= hi):
                    add("C05_REVIEWED_THRESHOLD", p, f"Prediksi/rentang +{h} menit menyentuh atau melintasi ambang operasional yang ditinjau.",
                        "Verifikasi dengan pengukuran dan konsultasikan kondisi lapangan.", cfg["reference"])
                    parameter_status[p] = "THRESHOLD_REVIEW"
    if not any(f.get("value") is not None for hs in result["forecasts"].values() for f in hs.values()):
        add("C06_INSUFFICIENT_HISTORY", None, "Informasi belum cukup untuk memberikan rekomendasi yang andal.",
            "Kumpulkan riwayat valid yang cukup setelah gap atau pembacaan bermasalah.")
    return {"status": "MONITOR_AND_VERIFY", "parameter_status": parameter_status,
            "insights": insights, "recommendations": recommendations, "trends": trends,
            "limitations": LIMITATIONS + ["Belum ada ambang operasional yang disetujui ahli dalam konfigurasi bawaan."]}


class WaterQualityEngine:
    def __init__(self, models_dir=None, experimental_anomaly_path=None):
        self.models_dir = Path(models_dir or MODELS_DIR)
        self.manifest = json.loads((self.models_dir / "manifest.json").read_text(encoding="utf-8"))
        if self.manifest["feature_schema"] != FEATURES or self.manifest["version"] != VERSION:
            raise ValueError("Feature schema/version mismatch")
        self.models = {}
        for e in self.manifest["models"]:
            if e["path"]:
                path = (self.models_dir / e["path"]).resolve()
                if path.parent != self.models_dir.resolve() or sha256(path) != e["sha256"]:
                    raise ValueError("Model path/hash mismatch")
                model = joblib.load(path)
                if list(model.feature_names_in_) != FEATURES:
                    raise ValueError("Fitted model feature order mismatch")
                self.models[e["model_id"]] = model
        self.anomaly = joblib.load(experimental_anomaly_path) if experimental_anomaly_path else None

    def infer(self, payload, thresholds=None):
        # One native-thread context for the complete request, rather than one per model.
        with threadpool_limits(limits=1):
            return self._infer(payload, thresholds)

    def _infer(self, payload, thresholds=None):
        if payload.get("mode") != "historical_replay":
            raise ValueError("Only historical_replay is approved in v2")
        now = timestamp(payload.get("current_timestamp"))
        if pd.isna(now) or not payload.get("pond_id"):
            raise ValueError("Valid naive current_timestamp and pond_id required; timestamp is interpreted as WIB")
        if now < pd.Timestamp(self.manifest["minimum_replay_origin"]):
            raise ValueError("Replay before calibration end is not approved: model/calibration would use later observations")
        rows = payload.get("readings", [])
        for row in rows:
            if row.get("pond_id", payload["pond_id"]) != payload["pond_id"]:
                raise ValueError("Mixed pond history rejected")
            t = timestamp(row.get("timestamp"))
            if pd.notna(t) and t > now:
                raise ValueError("Future observation rejected")
        frame = pd.DataFrame(rows, columns=["timestamp", *PARAMETERS])
        qa = apply_qa(frame) if len(frame) else None
        status, reasons = "STALE", ["NO_READINGS"]
        latest, values = None, {p: None for p in PARAMETERS}
        if qa is not None:
            last = qa.iloc[-1]
            status, reasons = last.qa_status, list(last.qa_reasons)
            latest = None if pd.isna(last.timestamp) else last.timestamp.isoformat()
            values = {p: float(last[p]) if np.isfinite(last[p]) else None for p in PARAMETERS}
            if latest and (now - last.timestamp).total_seconds() > 600:
                status, reasons = "STALE", reasons + ["NO_RECENT_OBSERVATION"]
        result = {"pond_id": payload["pond_id"], "mode": "historical_replay", "label": "Simulasi Data Historis",
                  "current_timestamp": now.isoformat(), "latest_sensor_timestamp": latest, "timezone": TIMEZONE,
                  "timezone_abbreviation": TIMEZONE_ABBREVIATION, "utc_offset": UTC_OFFSET,
                  "timestamp_semantics": TIMESTAMP_SEMANTICS,
                  "source_dataset": "fiscycle_local_recorded", "current_readings": values,
                  "data_quality": {"status": status, "reasons": reasons},
                  "anomaly_detection": {"status": "RESEARCH_ONLY_NOT_PACKAGED", "flag": None, "score": None,
                                        "requires_investigation": False},
                  "forecasts": {p: {} for p in PARAMETERS}, "errors": [], "warnings": [], "limitations": LIMITATIONS}
        x = None
        if qa is not None and status == "VALID":
            f = feature_frame(qa)
            if len(f) and f.iloc[-1].timestamp == qa.iloc[-1].timestamp and f.iloc[-1][FEATURES].notna().all():
                x = f.iloc[[-1]][FEATURES]
        if self.anomaly is not None and qa is not None and status in ["VALID", "SUSPICIOUS"]:
            f = feature_frame(qa, allow_suspicious=True)
            if len(f) and f.iloc[-1][FEATURES].notna().all():
                score = float(self.anomaly.decision_function(f.iloc[[-1]][FEATURES])[0])
                result["anomaly_detection"] = {"status": "EXPERIMENTAL_RESEARCH_OPT_IN", "flag": score < 0,
                                                "score": score, "requires_investigation": score < 0,
                                                "meaning": "Statistical deviation; no verified fault/biological label"}
        for e in self.manifest["models"]:
            p, h = e["parameter"], e["horizon_minutes"]
            forecast = {"parameter": p, "unit": UNITS[p], "horizon_minutes": h,
                        "target_timestamp": (pd.Timestamp(latest) + pd.Timedelta(minutes=h)).isoformat() if latest else None,
                        "value": None, "lower": None, "upper": None, "target_coverage": .9,
                        "interval_status": "UNAVAILABLE", "model_version": VERSION, "model_id": e["model_id"],
                        "algorithm": e["algorithm"], "status": "INPUT_UNAVAILABLE", "readiness": e["status"],
                        "observed_empirical_coverage": e["interval"].get("empirical_coverage")}
            if x is not None:
                prediction = float(x[p].iloc[0]) if e["algorithm"] == "Persistence" else float(self.models[e["model_id"]].predict(x)[0])
                forecast["value"] = prediction
                forecast["status"] = "PERSISTENCE_FALLBACK" if e["algorithm"] == "Persistence" else "COMPUTED_ML"
                if e["interval"]["status"] != "UNAVAILABLE":
                    q = e["interval"]["radius"]
                    forecast.update(lower=prediction - q, upper=prediction + q, interval_status=e["interval"]["status"])
            result["forecasts"][p][str(h)] = forecast
        if x is None:
            result["warnings"].append("Forecast suppressed: QA or continuous valid history insufficient (about 60 minutes).")
        if latest and now != pd.Timestamp(latest):
            result["warnings"].append("Forecast origin is latest_sensor_timestamp, not replay clock.")
        result["decision_support"] = decision_support(result, thresholds)
        return result


class HistoricalReplay:
    """Original observation time; no sleep/UI thread. stop/start resume the cursor."""
    def __init__(self, engine, frame, start=None, end=None, pond_id="fiscycle_local_pond_unknown"):
        self.engine, self.pond_id = engine, pond_id
        q = apply_qa(frame)
        if q.timestamp.isna().any() or (q.timestamp.diff().dt.total_seconds().dropna() < 0).any():
            raise ValueError("Replay source requires valid ordered timestamps; QA malformed inputs separately")
        # Starting a segment deliberately warms up from its first visible row.
        keep = pd.Series(True, index=frame.index)
        if start is not None:
            keep &= frame.timestamp >= pd.Timestamp(start)
        if end is not None:
            keep &= frame.timestamp <= pd.Timestamp(end)
        self.frame = frame.loc[keep].reset_index(drop=True)
        self.index, self.running = 0, False
        self.history, self.predictions, self.comparisons = [], [], []
        self.barrier_epoch = 0

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def next(self):
        if not self.running or self.index >= len(self.frame):
            return None
        row = self.frame.iloc[self.index]
        self.index += 1
        self.history.append({"timestamp": row.timestamp.isoformat(), **{p: row[p] for p in PARAMETERS}})
        output = self.engine.infer({"pond_id": self.pond_id, "mode": "historical_replay",
                                    "current_timestamp": row.timestamp.isoformat(), "readings": self.history})
        if output["data_quality"]["status"] != "VALID":
            self.barrier_epoch += 1
        # Nearest target is finalized only once the full tolerance window is visible.
        visible_qa = apply_qa(pd.DataFrame(self.history))
        for item in self.predictions:
            if item["resolved"] or row.timestamp < item["target"] + pd.Timedelta(seconds=TOLERANCE):
                continue
            item["resolved"] = True
            candidates = visible_qa[(visible_qa.timestamp - item["target"]).abs() <= pd.Timedelta(seconds=TOLERANCE)]
            distances = (candidates.timestamp - item["target"]).abs()
            nearest = candidates[distances.eq(distances.min())] if len(candidates) else candidates
            # QA barriers checked only through the target candidate, not after the target.
            valid_path = False
            if len(nearest) == 1:
                actual = nearest.iloc[0]
                between = visible_qa[(visible_qa.timestamp > item["origin"]) & (visible_qa.timestamp <= actual.timestamp)]
                valid_path = bool(between.qa_status.eq("VALID").all())
            if len(nearest) == 1 and valid_path:
                value = float(actual[item["parameter"]])
                self.comparisons.append({"origin": item["origin"].isoformat(), "target": item["target"].isoformat(),
                                         "actual_timestamp": actual.timestamp.isoformat(), "parameter": item["parameter"],
                                         "horizon_minutes": item["horizon_minutes"], "prediction": item["value"],
                                         "actual": value, "error": item["value"] - value, "status": "MATCHED"})
            else:
                self.comparisons.append({"origin": item["origin"].isoformat(), "target": item["target"].isoformat(),
                                         "parameter": item["parameter"], "horizon_minutes": item["horizon_minutes"],
                                         "status": "UNAVAILABLE_GAP_QA_OR_AMBIGUITY"})
        for p, hs in output["forecasts"].items():
            for h, f in hs.items():
                if f["value"] is not None:
                    self.predictions.append({"origin": row.timestamp, "target": pd.Timestamp(f["target_timestamp"]),
                                             "parameter": p, "horizon_minutes": int(h), "value": f["value"], "resolved": False})
        return output
