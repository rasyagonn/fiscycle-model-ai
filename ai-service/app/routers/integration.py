"""Integrated demonstration adapters; model code remains route-independent."""
import copy
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import BSF_ROOT, REPOSITORY_ROOT
from app.core.http import api_json, normalize_json
from app.routers.water_quality import require_water, replay_store
from app.routers.bsf_intelligence import service as require_bsf
from app.services.water_core import decision_support
from app.services.water_insights import RULES, VERSION, enrich
from app.services.bsf_photo import PHOTO_RULES, VERSION as PHOTO_VERSION

router = APIRouter(tags=["Integrated Intelligence"])


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    history_id: int = Field(gt=0)
    input_state: Literal["UNCHANGED", "STALE", "SENSOR_ERROR"]


@router.get("/water-quality/rules")
def water_rules():
    return {"version":VERSION,"rules":RULES,"expert_reviewed_biological_thresholds":[],
            "factors":["ph", "temperature_c", "turbidity_ntu", "timestamp", "qa_status", "history_coverage", "residual_interval", "forecast_horizon"]}


@router.get("/water-quality/history")
def water_history(request: Request, limit: int = Query(default=30,ge=1,le=100)):
    return {"records":require_water(request).history.list(limit)}


@router.get("/water-quality/history/{record_id}")
def water_history_record(record_id: int, request: Request):
    row = require_water(request).history.get(record_id)
    if not row:
        raise HTTPException(404,"Analisis tidak ditemukan")
    return row


@router.post("/water-quality/replay/sessions/{session_id}/snapshot")
def snapshot(session_id: str, request: Request):
    svc = require_water(request)
    store = replay_store(request)
    session = store.get(session_id)
    if not session.latest_result:
        raise HTTPException(409,"Jalankan sedikitnya satu observasi")
    result = normalize_json(copy.deepcopy(session.latest_result))
    result["replay_metrics"] = svc.replay.state(session)["metrics"]
    ident = svc.history.add("WATER_REPLAY", "HISTORICAL_LOCAL", result,
                            model_version=svc.manifest["version"],rule_version=VERSION)
    return {"history_id":ident,"result":result}


@router.post("/water-quality/scenario")
def scenario(payload: Scenario, request: Request):
    svc = require_water(request)
    record = svc.history.get(payload.history_id)
    if not record or record["kind"] not in {"WATER_ANALYSIS","WATER_REPLAY"}:
        raise HTTPException(404,"Sumber analisis historis tidak ditemukan")
    before = record["result"]
    after = copy.deepcopy(before)
    if payload.input_state != "UNCHANGED":
        after["data_quality"] = {"status":payload.input_state,"reasons":["NO_RECENT_OBSERVATION" if payload.input_state=="STALE" else "INVALID_TIMESTAMP_OR_TIMEZONE"]}
        for hs in after["forecasts"].values():
            for f in hs.values():
                f.update(value=None,lower=None,upper=None,status="INPUT_UNAVAILABLE",interval_status="UNAVAILABLE")
    after["decision_support"] = decision_support(after)
    after = enrich(after)
    after["provenance"] = "SIMULATED_RULE_ONLY"
    for trace in after["decision_support"]["traces"]:
        trace["provenance"] = "SIMULATED_RULE_ONLY"
    result = {"provenance":"SIMULATED_RULE_ONLY","source_history_id":payload.history_id,
        "modification":payload.input_state,"ml_recomputed":False,
        "explanation":"Skenario menguji kelayakan data dan aturan DSS; bukan simulasi perubahan biologis atau hasil sensor baru.",
        "before":before,"after":after}
    result["history_id"] = svc.history.add("WATER_SCENARIO","SIMULATED_RULE_ONLY",result,rule_version=VERSION)
    return api_json(result)


@router.post("/water-quality/replay/sessions/{session_id}/advance")
def advance(session_id: str, request: Request, steps: int = Query(default=25,ge=1,le=80)):
    store = replay_store(request)
    session = store.get(session_id)
    for _ in range(steps):
        state = store.step(session)
        if state["finished"]:
            break
    return api_json(state)


@router.get("/api/v1/demo/catalog")
def demos(request: Request):
    return {"flows":[{"id":"A","label":"Satu foto: segmentasi, estimasi berat, dan DSS","input":"/api/v1/demo/photo"},
        {"id":"B","label":"Pertumbuhan BSF historis dan DSS","input":"development trajectories"},
        {"id":"C","label":"Replay Water dan evaluasi prediksi","input":"/water-quality/replay/periods"},
        {"id":"D","label":"Keputusan Water dan skenario kelayakan data","input":"/water-quality/scenario"}],
        "photo_rules":{"version":PHOTO_VERSION,"rules":PHOTO_RULES},
        "circular_context":{"implemented":["Water AI historical replay","Smart BSF research inference"],
            "planned":["Penerimaan limbah B2B/B2C","Konversi dan kelayakan pakan operasional","Circular Points dan insentif B2B","Orkestrasi permintaan pasar"],
            "impact_measurements":None}}


@router.get("/api/v1/demo/photo")
def example_photo():
    packaged = REPOSITORY_ROOT / "tests/fixtures/a1_development_train.jpg"
    path = packaged if packaged.is_file() else None
    if path is None:
        raise HTTPException(503,"Foto contoh train tidak tersedia")
    return FileResponse(path,media_type="image/jpeg",headers={"X-Data-Provenance":"PUBLIC_RESEARCH_TRAIN_FIXTURE"})


@router.get("/api/v1/bsf-research/treatment-comparison")
def treatment_comparison(request: Request, revealed: int = Query(default=3,ge=2,le=19)):
    svc = require_bsf(request)
    snapshots = [svc.replay(k,revealed) for k in svc.trajectories]
    return {"provenance":"HISTORICAL_RESEARCH", "scope":"IN_SAMPLE_DEVELOPMENT_REPLAY",
        "independent_validation":False,"causal_effect_claim":False,"revealed_per_trajectory":revealed,
        "trajectories":[{"trajectory_id":s["trajectory_id"],"moisture_percent":s["moisture_percent"],
                         "observations":s["observations"],"forecast":s["forecast"],"comparisons":s["comparisons"]} for s in snapshots],
        "limitations":"Perbandingan deskriptif antar replikasi; jumlah foto bukan jumlah sampel biologis independen."}
