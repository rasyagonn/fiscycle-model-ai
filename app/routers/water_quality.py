from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.core.config import register_domain_paths
from app.core.http import api_json
from app.schemas.water_quality import AnalyzeRequest, MAX_REPLAY_HOURS, ReplayCreateRequest
from app.services.water_quality import ReplayStore, WaterQualityService

register_domain_paths()
from app.services.water_core import (
    HORIZONS,
    PARAMETERS,
    TIMEZONE,
    TIMEZONE_ABBREVIATION,
    TIMESTAMP_SEMANTICS,
    UTC_OFFSET,
)

router = APIRouter(tags=["Water Quality"])


def require_water(request: Request) -> WaterQualityService:
    service = request.app.state.water_quality
    if service is None:
        raise HTTPException(503, "Water Quality belum siap; periksa /health untuk detail")
    return service


@router.get("/water-quality/health")
def water_health(request: Request):
    service = request.app.state.water_quality
    return {
        "ready": service is not None,
        "status": "SIAP" if service is not None else "TIDAK_SIAP",
        "load_error": request.app.state.load_errors.get("water_quality"),
        "mode": "historical_replay",
        "timezone": TIMEZONE,
        "timezone_abbreviation": TIMEZONE_ABBREVIATION,
        "utc_offset": UTC_OFFSET,
        "timestamp_semantics": TIMESTAMP_SEMANTICS,
    }


@router.get("/models", include_in_schema=False)
@router.get("/water-quality/models")
def models(request: Request):
    service = require_water(request)
    rows = []
    for entry in service.manifest["models"]:
        evaluation = entry["historical_evaluation"]
        interval = entry["interval"]
        rows.append(
            {
                "parameter": entry["parameter"],
                "horizon_minutes": entry["horizon_minutes"],
                "algorithm": entry["algorithm"],
                "model_id": entry["model_id"],
                "readiness": entry["status"],
                "historical_evaluation_mae": evaluation["MAE"],
                "target_interval_coverage": interval["target_coverage"],
                "empirical_interval_coverage": interval["empirical_coverage"],
                "interval_status": interval["status"],
                "is_trained_ml": entry["path"] is not None,
                "method_label": entry["algorithm"] if entry["path"] else "Persistence (Baseline)",
            }
        )
    return {"version": service.manifest["version"], "mode": service.manifest["mode"], "models": rows}


@router.post("/water-quality/analyze")
def analyze(payload: AnalyzeRequest, request: Request):
    result = require_water(request).analyze(payload.model_dump(exclude_none=True))
    return api_json(result)


@router.get("/replay/periods", include_in_schema=False)
@router.get("/water-quality/replay/periods")
def replay_periods(request: Request):
    store = require_water(request).replay
    return {
        "minimum_replay_origin": store.minimum.isoformat(),
        "latest_recorded_timestamp": store.maximum.isoformat(),
        "timezone": TIMEZONE,
        "timezone_abbreviation": TIMEZONE_ABBREVIATION,
        "utc_offset": UTC_OFFSET,
        "timestamp_semantics": TIMESTAMP_SEMANTICS,
        "max_period_hours": MAX_REPLAY_HOURS,
        "periods": store.periods(),
    }


@router.post("/replay/sessions", status_code=201, include_in_schema=False)
@router.post("/water-quality/replay/sessions", status_code=201)
def create_replay(payload: ReplayCreateRequest, request: Request):
    store = require_water(request).replay
    state = store.state(store.create(payload), "Sesi dibuat; tekan Mulai atau Observasi Berikutnya.")
    return api_json(state, 201)


def replay_store(request: Request) -> ReplayStore:
    return require_water(request).replay


@router.post("/replay/sessions/{session_id}/start", include_in_schema=False)
@router.post("/water-quality/replay/sessions/{session_id}/start")
def start_replay(session_id: str, request: Request):
    store = replay_store(request)
    session = store.get(session_id)
    if session.replay.index >= len(session.replay.frame):
        return store.state(session, "Periode replay telah selesai; gunakan Reset.")
    session.replay.start()
    return store.state(session, "Replay berjalan; frontend dapat meminta observasi berikutnya.")


@router.post("/replay/sessions/{session_id}/pause", include_in_schema=False)
@router.post("/water-quality/replay/sessions/{session_id}/pause")
def pause_replay(session_id: str, request: Request):
    store = replay_store(request)
    session = store.get(session_id)
    session.replay.stop()
    return store.state(session, "Replay dijeda.")


@router.post("/replay/sessions/{session_id}/next", include_in_schema=False)
@router.post("/water-quality/replay/sessions/{session_id}/next")
def next_replay(session_id: str, request: Request):
    store = replay_store(request)
    return api_json(store.step(store.get(session_id)))


@router.post("/replay/sessions/{session_id}/reset", include_in_schema=False)
@router.post("/water-quality/replay/sessions/{session_id}/reset")
def reset_replay(session_id: str, request: Request):
    store = replay_store(request)
    return store.state(store.reset(store.get(session_id)), "Replay direset ke awal periode.")


@router.get("/replay/sessions/{session_id}", include_in_schema=False)
@router.get("/water-quality/replay/sessions/{session_id}")
def get_replay(session_id: str, request: Request):
    store = replay_store(request)
    return store.state(store.get(session_id))

