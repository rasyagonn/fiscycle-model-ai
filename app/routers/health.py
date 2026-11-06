from __future__ import annotations

from fastapi import APIRouter, Request
from app.core.config import WATER_QUALITY_ROOT

router = APIRouter(tags=["System"])


@router.get("/health")
def health(request: Request):
    water_ready = request.app.state.water_quality is not None
    bsf_ready = request.app.state.bsf is not None
    intelligence_ready = request.app.state.bsf_intelligence is not None
    all_ready = (water_ready or not WATER_QUALITY_ROOT.is_dir()) and bsf_ready and intelligence_ready
    any_ready = water_ready or bsf_ready or intelligence_ready
    return {
        "status": "SIAP" if all_ready else "DEGRADED" if any_ready else "TIDAK_SIAP",
        "ready": all_ready,
        "available": any_ready,
        "service": "fiscycle-model-api",
        "services": {
            "water_quality": {
                "ready": water_ready,
                "scope": "HISTORICAL_REPLAY",
                "load_error": request.app.state.load_errors.get("water_quality"),
            },
            "bsf": {
                "ready": bsf_ready,
                "scope": "RESEARCH_DEMO_ONLY",
                "model_status": "RESEARCH_PROTOTYPE",
                "validation_status": "NOT_FIELD_VALIDATED",
                "load_error": request.app.state.load_errors.get("bsf"),
            },
            "bsf_intelligence": {
                "ready": intelligence_ready,
                "scope": "RESEARCH_DEMO_ONLY",
                "model_status": "RESEARCH_PROTOTYPE",
                "validation_status": "NOT_FIELD_VALIDATED",
                "load_error": request.app.state.load_errors.get("bsf_intelligence"),
            },
        },
    }

