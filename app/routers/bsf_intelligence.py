"""Integrated BSF research API; raw image bytes, no server-side file path input."""
from __future__ import annotations

import hashlib
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.bsf_decisions import FACTOR_DEFINITIONS, RULES, VERSION, evaluate_decision, factor_category
from app.services.bsf_intelligence import BsfIntelligence, decode_image
from app.core.config import BSF_API_PREFIX

router = APIRouter(prefix=BSF_API_PREFIX, tags=["Smart BSF Intelligence"])
IMAGE_BODY = {"requestBody": {"required": True, "content": {
    kind: {"schema": {"type": "string", "format": "binary"}}
    for kind in ("image/jpeg", "image/png", "image/webp")}}}


def service(request: Request) -> BsfIntelligence:
    value = getattr(request.app.state, "bsf_intelligence", None)
    if value is None:
        raise HTTPException(503, "Smart BSF belum siap; periksa /api/v1/bsf/health")
    return value


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    day: float = Field(ge=0)
    measured_weight_mg: float = Field(ge=0)


class DecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    data_mode: Literal["HISTORICAL_RESEARCH", "USER_ENTERED", "SIMULATED"]
    trajectory_id: str | None = None
    revealed: int | None = Field(default=None, ge=0)
    observations: list[Observation] = Field(default_factory=list, max_length=100)
    target_weight_mg: float | None = Field(default=None, gt=0)
    moisture_percent: float | None = Field(default=None, ge=0, le=100)
    substrate_temperature_c: float | None = None
    substrate_type: str | None = Field(default=None, max_length=120)
    image_record_id: int | None = Field(default=None, gt=0)
    batch_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def check_mode(self):
        if self.data_mode == "HISTORICAL_RESEARCH":
            if not self.trajectory_id or self.revealed is None or self.observations or self.image_record_id:
                raise ValueError("Mode penelitian memerlukan trajectory_id dan revealed; observations tidak boleh dikirim.")
        elif self.trajectory_id or self.revealed is not None:
            raise ValueError("Mode pengguna/simulasi tidak boleh memakai trajectory_id atau revealed.")
        if any(b.day <= a.day for a, b in zip(self.observations, self.observations[1:])):
            raise ValueError("Hari pengamatan harus meningkat tanpa duplikat.")
        if self.image_record_id and (self.data_mode != "USER_ENTERED" or not self.batch_id):
            raise ValueError("Kaitan foto hanya boleh untuk batch pengguna yang disebutkan secara eksplisit.")
        return self


class ForecastInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    input_provenance: Literal["USER_ENTERED_MEASURED_HISTORY", "SYNTHETIC_SCENARIO"]
    moisture_percent: float
    elapsed_days: float
    current_weight_mg: float
    previous_weight_mg: float
    recent_growth_mg_per_day: float
    forecast_horizon_days: float


class UserObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    batch_id: str = Field(min_length=1, max_length=100)
    day: float = Field(ge=0)
    measured_weight_mg: float = Field(ge=0)
    measurement_note: str | None = Field(default=None, max_length=400)


@router.get("/health")
def health(request: Request):
    ready = getattr(request.app.state, "bsf_intelligence", None) is not None
    return {"ready": ready, "status": ["RESEARCH_PROTOTYPE", "NOT_FIELD_VALIDATED"],
            "load_error": request.app.state.load_errors.get("bsf_intelligence")}


@router.get("/models")
def models(request: Request):
    return service(request).models()


@router.post("/segment", openapi_extra=IMAGE_BODY)
async def segment(request: Request, confidence: float = Query(default=0.25, ge=0.01, le=0.99)):
    svc = service(request)
    data = await request.body()
    try:
        image = decode_image(data, request.headers.get("content-type", "").split(";")[0].lower())
        result = await run_in_threadpool(svc.segment, image, confidence=confidence)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    result["image_sha256"] = hashlib.sha256(data).hexdigest()
    result["history_id"] = svc.history.add("A1_SEGMENT", "AI_PREDICTED_A1", result,
                                           model_version=result["model_version"], image_sha256=result["image_sha256"])
    return result


@router.post("/analyze-photo", openapi_extra=IMAGE_BODY)
async def analyze_photo_endpoint(request: Request):
    from app.services.bsf_photo import analyze_photo
    svc = service(request)
    data = await request.body()
    try:
        result = await run_in_threadpool(analyze_photo, svc.models_runtime, data, request.headers.get("content-type", "").split(";")[0].lower())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    result["image_sha256"] = hashlib.sha256(data).hexdigest()
    result["history_id"] = svc.history.add("A1_A2_PHOTO", result["provenance"], result,
        model_version="a1_initial+model_a2_training_v3", preprocessing_version=result["preprocessing_version"],
        rule_version=result["pipeline_version"], image_sha256=result["image_sha256"])
    return result


@router.post("/estimate-weight", openapi_extra=IMAGE_BODY)
async def estimate_weight(request: Request, x0: int, y0: int, x1: int, y1: int, reviewed_roi: bool = False):
    svc = service(request)
    data = await request.body()
    try:
        image = decode_image(data, request.headers.get("content-type", "").split(";")[0].lower(), require_unrotated=True)
        result = await run_in_threadpool(svc.estimate_weight, image, (x0, y0, x1, y1), reviewed_roi=reviewed_roi)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    result["image_sha256"] = hashlib.sha256(data).hexdigest()
    result["history_id"] = svc.history.add("A2_WEIGHT", "AI_PREDICTED_A2", result,
                                           model_version=result["model_version"],
                                           preprocessing_version=result["preprocessing_version"], image_sha256=result["image_sha256"])
    return result


@router.get("/replay/trajectories")
def trajectories(request: Request):
    return {"trajectories": service(request).trajectory_list(), "data_mode": "HISTORICAL_RESEARCH"}


@router.get("/replay/{trajectory_id}")
def replay(trajectory_id: str, request: Request, revealed: int = Query(default=0, ge=0)):
    try:
        svc = service(request)
        result = svc.replay(trajectory_id, revealed)
        if result["forecast"] is not None:
            result["forecast"]["history_id"] = svc.history.add("B1_FORECAST", "HISTORICAL_RESEARCH",
                {"trajectory_id": trajectory_id, "revealed": revealed, "input_features": result["forecast"]["input_features"],
                 "forecast": result["forecast"]["result"], "provenance": "AI_PREDICTED_B1"},
                model_version="bsf_model_b1_estimator")
        return result
    except KeyError as exc:
        raise HTTPException(404, "Trajektori penelitian tidak ditemukan") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/overview")
def overview(request: Request, trajectory_id: str | None = None):
    svc = service(request)
    chosen = trajectory_id or next(iter(svc.trajectories))
    if chosen not in svc.trajectories:
        raise HTTPException(404, "Trajektori tidak ditemukan")
    snapshot = svc.replay(chosen, len(svc.trajectories[chosen]["observations"]))
    return {"trajectory_id": chosen, "data_mode": "HISTORICAL_RESEARCH", "source": snapshot["source"],
            "latest_measured": snapshot["observations"][-1], "trend": snapshot["observations"],
            "next_forecast": snapshot["forecast"], "image_analysis": None,
            "status": snapshot["status"], "warning": "Penelitian historis; bukan data sensor atau budidaya live."}


@router.post("/forecast")
def forecast(payload: ForecastInput, request: Request):
    svc = service(request)
    features = payload.model_dump(exclude={"input_provenance"})
    result = svc.b1.predict(features, payload.input_provenance)
    result["input_features"] = features
    result["input_verification"] = "SIMULATED" if payload.input_provenance == "SYNTHETIC_SCENARIO" else "USER_DECLARED_UNVERIFIED"
    result["history_id"] = svc.history.add("B1_FORECAST", "SIMULATED" if payload.input_provenance == "SYNTHETIC_SCENARIO" else "USER_ENTERED",
                                           result, model_version="bsf_model_b1_estimator")
    return result


@router.get("/factors")
def factors():
    return {"registry_version": VERSION, "factors": [{"factor_id": key, "name": name, "unit": unit, "role": role,
            "category": factor_category(key), "validation_status": "NOT_FIELD_VALIDATED" if role == "model_output" else "SOURCE_DEPENDENT",
            "approval_status": "CANDIDATE_NOT_APPROVED_FOR_OPERATIONAL_DECISION",
            "current_value": None, "availability": "CONTEXT_DEPENDENT", "reference_range": None,
            "evidence_source": None, "decision_role": "CANDIDATE",
            "relationship": "unknown"} for key, (name, unit, role) in FACTOR_DEFINITIONS.items()]}


@router.get("/rules")
def rules():
    return {"rule_version": VERSION, "rules": RULES}


@router.post("/decision-support")
def decision_support(payload: DecisionInput, request: Request):
    svc = service(request)
    context = payload.model_dump(exclude={"data_mode", "trajectory_id", "revealed", "observations", "image_record_id"}, exclude_none=True)
    observations = [item.model_dump() for item in payload.observations]
    forecast_result = None
    if payload.data_mode == "HISTORICAL_RESEARCH":
        try:
            snapshot = svc.replay(payload.trajectory_id, payload.revealed)
        except KeyError as exc:
            raise HTTPException(404, "Trajektori tidak ditemukan") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        observations = snapshot["observations"]
        context["moisture_percent"] = snapshot["moisture_percent"]
        context["batch_id"] = snapshot["trajectory_id"]
        forecast_result = snapshot["forecast"]["result"] if snapshot["forecast"] else None
    image_result = None
    if payload.image_record_id:
        found = svc.history.get(payload.image_record_id)
        if found is None or found["kind"] not in {"A1_SEGMENT", "A2_WEIGHT"}:
            raise HTTPException(404, "Hasil analisis foto tidak ditemukan")
        image_result = found["result"]
        context["image_link_verification"] = "USER_ASSERTED_NOT_VERIFIED"
    result = evaluate_decision(observations=observations, mode=payload.data_mode, context=context,
                               forecast=forecast_result, image_result=image_result)
    result["input_snapshot"] = {"observations": observations, "context": context,
                                 "image_record_id": payload.image_record_id, "forecast": forecast_result}
    result["history_id"] = svc.history.add("DSS_DECISION", "RULE_DERIVED", result,
                                           rule_version=VERSION)
    return result


@router.post("/observations", status_code=201)
def add_observation(payload: UserObservation, request: Request):
    svc = service(request)
    prior = svc.history.observations(payload.batch_id)
    if prior and payload.day <= prior[-1]["day"]:
        raise HTTPException(422, "Hari baru harus setelah pengamatan terakhir untuk batch ini")
    result = {**payload.model_dump(), "provenance": "USER_ENTERED", "status": ["UNVERIFIED_USER_ENTRY"]}
    result["history_id"] = svc.history.add("USER_OBSERVATION", "USER_ENTERED", result)
    return result


@router.get("/observations")
def observations(request: Request, batch_id: str = Query(min_length=1, max_length=100)):
    return {"batch_id": batch_id, "observations": service(request).history.observations(batch_id),
            "provenance": "USER_ENTERED"}


@router.get("/history")
def history(request: Request, limit: int = Query(default=50, ge=1, le=100), kind: str | None = None):
    return {"records": service(request).history.list(limit=limit, kind=kind)}


@router.get("/history/{record_id}")
def history_detail(record_id: int, request: Request):
    result = service(request).history.get(record_id)
    if result is None:
        raise HTTPException(404, "Riwayat tidak ditemukan")
    return result


@router.get("/recommendations/{record_id}")
def recommendation(record_id: int, request: Request):
    result = service(request).history.get(record_id)
    if result is None or result["kind"] != "DSS_DECISION":
        raise HTTPException(404, "Rekomendasi tidak ditemukan")
    return result
