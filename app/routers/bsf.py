from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.core.http import api_json
from app.schemas.bsf import BsfNextWeightRequest
from app.services.bsf import BsfService

router = APIRouter(prefix="/bsf", tags=["BSF Research"])


def require_bsf(request: Request) -> BsfService:
    service = request.app.state.bsf
    if service is None:
        raise HTTPException(503, "Model BSF belum siap; periksa /health untuk detail")
    return service


@router.get("/health")
def bsf_health(request: Request):
    service = request.app.state.bsf
    return {
        "ready": service is not None,
        "status": "SIAP_RISET" if service is not None else "TIDAK_SIAP",
        "model_status": "RESEARCH_PROTOTYPE",
        "validation_status": "NOT_FIELD_VALIDATED",
        "load_error": request.app.state.load_errors.get("bsf"),
    }


@router.get("/models")
def bsf_models(request: Request):
    service = require_bsf(request)
    metadata = service.metadata
    return {
        "model": "BSF Model B1",
        "method": metadata["method"],
        "features": metadata["features"],
        "supported_moisture_treatments_percent": metadata["supported_moisture_treatments_percent"],
        "model_status": "RESEARCH_PROTOTYPE",
        "validation_status": "NOT_FIELD_VALIDATED",
        "target": "next-observation mean larval wet weight (mg/individual)",
    }


@router.post("/next-weight")
def next_weight(payload: BsfNextWeightRequest, request: Request):
    result = require_bsf(request).predict(payload.inference_features(), payload.input_provenance)
    status = result["input_domain_status"]
    if status in {"INVALID_INPUT", "OUT_OF_DOMAIN"}:
        return api_json(result, 422)
    if status == "MODEL_ERROR":
        return api_json(result, 500)
    return api_json(result)

