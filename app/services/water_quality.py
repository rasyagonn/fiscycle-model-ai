from __future__ import annotations

import json
import threading
import uuid
import hashlib
from dataclasses import dataclass
from typing import Any

import pandas as pd
from fastapi import HTTPException

from app.core.config import register_domain_paths, WATER_QUALITY_ROOT, BSF_HISTORY_DB
from app.core.security import tenant_context
from app.services.water_insights import enrich, replay_metrics
from app.services.bsf_intelligence import BsfHistory
from app.core.http import normalize_json
from app.schemas.water_quality import ReplayCreateRequest

register_domain_paths()
from app.services.water_core import (
    MODELS_DIR,
    HistoricalReplay,
    WaterQualityEngine,
    apply_qa,
    load_local,
)

MAX_SESSIONS = 8
MAX_RETURNED_OBSERVATIONS = 500
MAX_RETURNED_COMPARISONS = 500
WARMUP_HOURS = 3


@dataclass
class ReplaySession:
    session_id: str
    start: pd.Timestamp
    end: pd.Timestamp
    pond_id: str
    replay: HistoricalReplay
    visible_history_start: int
    latest_result: dict[str, Any] | None = None
    tenant_id: str = "local_demo"


class ReplayStore:
    def __init__(self, engine: WaterQualityEngine, data: pd.DataFrame, manifest: dict[str, Any]):
        self.engine = engine
        self.data = data.copy()
        if self.data.pond_id.isna().any() or self.data.pond_id.nunique() != 1:
            raise ValueError("Replay Water Quality saat ini memerlukan satu kelompok pond_id")
        self.manifest = manifest
        self.sessions: dict[str, ReplaySession] = {}
        self.lock = threading.RLock()
        self.minimum = pd.Timestamp(manifest["minimum_replay_origin"])
        self.maximum = pd.Timestamp(manifest["latest_recorded_timestamp"])

    def periods(self) -> list[dict[str, Any]]:
        qa = apply_qa(self.data)
        qa = qa[qa.timestamp.ge(self.minimum)].copy()
        usable = qa.qa_status.eq("VALID")
        boundary = (~usable) | qa.gap_seconds.gt(600) | qa.gap_seconds.le(0)
        qa["segment"] = boundary.cumsum()
        segments = qa[usable].groupby("segment").agg(
            start=("timestamp", "min"), end=("timestamp", "max"), rows=("timestamp", "size")
        )
        segments["hours"] = (segments.end - segments.start).dt.total_seconds() / 3600
        choices: list[dict[str, Any]] = []
        for row in segments[segments.hours.ge(4)].sort_values("start").itertuples():
            start = max(
                row.start + pd.Timedelta(hours=WARMUP_HOURS),
                self.minimum + pd.Timedelta(hours=WARMUP_HOURS),
            )
            while start + pd.Timedelta(hours=6) <= row.end and len(choices) < 5:
                end = min(start + pd.Timedelta(hours=12), row.end)
                count = int(self.data.timestamp.between(start, end, inclusive="both").sum())
                choices.append(
                    {
                        "id": f"period-{len(choices) + 1}",
                        "pond_id": str(self.data.pond_id.iloc[0]),
                        "start": start.isoformat(),
                        "end": end.isoformat(),
                        "observations": count,
                        "label": f"{start:%d %b %Y %H:%M} — {end:%d %b %Y %H:%M}",
                    }
                )
                start = end
        return choices

    def create(self, request: ReplayCreateRequest, session_id: str | None = None) -> ReplaySession:
        with self.lock:
            if request.pond_id not in set(self.data.pond_id):
                raise HTTPException(422, "pond_id tidak ditemukan pada rekaman lokal")
            start, end = pd.Timestamp(request.start), pd.Timestamp(request.end)
            if start < self.minimum:
                raise HTTPException(422, f"Replay hanya didukung mulai {self.minimum.isoformat()}")
            if end > self.maximum:
                raise HTTPException(422, f"Replay melebihi rekaman terakhir {self.maximum.isoformat()}")
            warmup_start = max(self.minimum, start - pd.Timedelta(hours=WARMUP_HOURS))
            selected = self.data[
                self.data.pond_id.eq(request.pond_id) &
                self.data.timestamp.between(warmup_start, end, inclusive="both")
            ].copy()
            if selected[selected.timestamp.ge(start)].empty:
                raise HTTPException(422, "Tidak ada observasi pada periode yang dipilih")
            replay = HistoricalReplay(self.engine, selected, start=warmup_start, end=end, pond_id=request.pond_id)
            replay.start()
            while replay.index < len(replay.frame) and replay.frame.timestamp.iloc[replay.index] < start:
                replay.next()
            replay.stop()
            warmup_count = len(replay.history)
            replay.predictions.clear()
            replay.comparisons.clear()
            session = ReplaySession(
                session_id or uuid.uuid4().hex,
                start,
                end,
                request.pond_id,
                replay,
                warmup_count,
            )
            session.tenant_id = tenant_context.get()
            if request.replace_session_id and request.replace_session_id != session.session_id:
                if request.replace_session_id in self.sessions and self.sessions[request.replace_session_id].tenant_id == tenant_context.get():
                    self.sessions.pop(request.replace_session_id, None)
            owned = [key for key,value in self.sessions.items() if value.tenant_id == tenant_context.get()]
            if session_id is None and len(owned) >= MAX_SESSIONS:
                self.sessions.pop(owned[0])
            elif session_id is None and len(self.sessions) >= 64:
                raise HTTPException(429,"Kapasitas sesi replay penuh")
            self.sessions[session.session_id] = session
            return session

    def get(self, session_id: str) -> ReplaySession:
        try:
            session = self.sessions[session_id]
            if session.tenant_id != tenant_context.get():
                raise KeyError(session_id)
            return session
        except KeyError as exc:
            raise HTTPException(404, "Sesi replay tidak ditemukan atau sudah kedaluwarsa") from exc

    def state(self, session: ReplaySession, message: str | None = None) -> dict[str, Any]:
        replay = session.replay
        processed = max(0, replay.index - session.visible_history_start)
        total = max(0, len(replay.frame) - session.visible_history_start)
        finished = replay.index >= len(replay.frame)
        observations = replay.history[session.visible_history_start :]
        return normalize_json(
            {
                "session_id": session.session_id,
                "status": "SELESAI" if finished else "BERJALAN" if replay.running else "DIJEDA",
                "running": replay.running and not finished,
                "finished": finished,
                "selected_period": {"start": session.start.isoformat(), "end": session.end.isoformat()},
                "warmup": {
                    "observations": session.visible_history_start,
                    "visible_in_chart": False,
                    "purpose": "Konteks fitur sebelum awal replay; bukan observasi periode yang ditampilkan.",
                },
                "processed_observations": processed,
                "total_observations": total,
                "current_replay_timestamp": (
                    session.latest_result.get("current_timestamp") if session.latest_result else None
                ),
                "latest_result": session.latest_result,
                "observations": observations[-MAX_RETURNED_OBSERVATIONS:],
                "observations_truncated": len(observations) > MAX_RETURNED_OBSERVATIONS,
                "completed_comparisons": replay.comparisons[-MAX_RETURNED_COMPARISONS:],
                "metrics": replay_metrics(replay.comparisons, replay.predictions),
                "comparisons_truncated": len(replay.comparisons) > MAX_RETURNED_COMPARISONS,
                "message": message,
            }
        )

    def step(self, session: ReplaySession) -> dict[str, Any]:
        with self.lock:
            replay = session.replay
            if replay.index >= len(replay.frame):
                replay.stop()
                return self.state(session, "Periode replay telah selesai")
            was_running = replay.running
            if not was_running:
                replay.start()
            session.latest_result = enrich(replay.next())
            if not was_running or replay.index >= len(replay.frame):
                replay.stop()
            return self.state(session)

    def reset(self, session: ReplaySession) -> ReplaySession:
        payload = ReplayCreateRequest(
            start=session.start.isoformat(), end=session.end.isoformat(), pond_id=session.pond_id
        )
        return self.create(payload, session_id=session.session_id)


class WaterQualityService:
    def __init__(self) -> None:
        from app.core.artifacts import verify_domain
        verify_domain("water")
        manifest_path = MODELS_DIR / "manifest.json"
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.engine = WaterQualityEngine()
        seed = WATER_QUALITY_ROOT / "replay/water_replay_v1.csv"
        if seed.exists():
            meta = json.loads(seed.with_suffix(".metadata.json").read_text(encoding="utf-8"))
            if hashlib.sha256(seed.read_bytes()).hexdigest() != meta["sha256"] or meta["version"] != "water_replay_v1":
                raise ValueError("Water replay seed checksum/version mismatch")
            data = pd.read_csv(seed, parse_dates=["timestamp"])
            data["timestamp"] = pd.to_datetime(data["timestamp"], errors="raise")
            if data.timestamp.isna().any() or data.timestamp.duplicated().any() or not data.timestamp.is_monotonic_increasing:
                raise ValueError("Water replay timestamps invalid")
            if len(data) != meta["rows"] or set(data.source_dataset) != {"fiscycle_local_recorded"} or set(data.timezone) != {"Asia/Jakarta"}:
                raise ValueError("Water replay provenance/schema mismatch")
        else:
            if WATER_QUALITY_ROOT.name == "water_assets":
                raise FileNotFoundError("Packaged Water replay seed missing")
            data = load_local()
        self.replay = ReplayStore(self.engine, data, self.manifest)
        self.history = BsfHistory(BSF_HISTORY_DB.with_name("water_history.sqlite3"))

    def analyze(self, payload):
        result = enrich(self.engine.infer(payload))
        result["input_verification"] = "CALLER_DECLARED_HISTORICAL_UNVERIFIED"
        result["provenance"] = "USER_SUPPLIED_HISTORICAL_CLAIM_WITH_AI_PREDICTIONS"
        result["source_dataset"] = "caller_declared_fiscycle_local_recorded"
        for trace in result["decision_support"]["traces"]:
            trace["provenance"] = result["provenance"]
        result["history_id"] = self.history.add("WATER_ANALYSIS", result["provenance"], normalize_json(result), model_version=self.manifest["version"], rule_version=result["decision_support"]["rule_version"])
        return result

    def close(self) -> None:
        self.replay.sessions.clear()

