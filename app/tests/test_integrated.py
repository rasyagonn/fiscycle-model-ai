import io
import json
import math
import sqlite3

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from app.main import app
from app.services.bsf_intelligence import BsfHistory
from app.services.bsf_photo import roi_check, raw_point, _analyze
from app.core.security import tenant_context
from app.integration_checks import run_integrated_checks


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    with TestClient(app) as c:
        directory=tmp_path_factory.mktemp("combined")
        c.app.state.bsf_intelligence.history=BsfHistory(directory / "bsf.sqlite3")
        c.app.state.water_quality.history=BsfHistory(directory / "water.sqlite3")
        yield c


def test_four_actual_flows(client):
    def check(label,condition):
        assert condition,label
    result=run_integrated_checks(client,check)
    print("ACTUAL_FOUR_FLOW_RESULT",json.dumps(result))


def test_roi_failure_and_exif_contract():
    assert roi_check([[0,3],[9,3],[9,9]],100,100,2048)[1]=="SOURCE_BORDER_TRUNCATION_REVIEW"
    assert roi_check([[1,1],[2,2],[3,3]],100,100,2048)[1]=="ZERO_AREA"
    assert roi_check([[1,1],[float('nan'),2],[3,3]],100,100,2048)[1]=="INVALID_POLYGON"
    assert roi_check([[1,1],[3000,1],[3000,10]],4000,3000,2048)[1]=="FULL_ROI_EXCEEDS_TRAIN_SELECTED_CANVAS"
    assert raw_point(10,20,6,400,300)==(20,290)
    assert raw_point(10,20,8,400,300)==(380,10)


def test_zero_detection_null_mass_and_all_rejected():
    # Deterministic boundary tests; real model flow is separately tested above.
    class Empty:
        preprocessing={"canvas_size":2048,"method":"fixed_native_pixel_canvas_v1"}
        def segment(self,image):
            return {"instances":[],"visible_instance_count":0}
    stream=io.BytesIO();Image.new("RGB",(128,128)).save(stream,format="PNG")
    result=_analyze(Empty(),stream.getvalue(),"image/png")
    assert result["summary"]["analyzed_visible_mass_mg"] is None
    assert result["summary"]["coverage"] is None
    class Border(Empty):
        def segment(self,image):
            return {"instances":[{"polygon_xy":[[0,0],[10,0],[10,10]]}],"visible_instance_count":1}
    result=_analyze(Border(),stream.getvalue(),"image/png")
    assert result["summary"]["rejected"]==1 and result["summary"]["analyzed_visible_mass_mg"] is None


def test_tenant_history_isolation_and_restart(tmp_path):
    store=BsfHistory(tmp_path / "history.sqlite3")
    token=tenant_context.set("farm-a")
    try:
        ident=store.add("USER_OBSERVATION","USER_ENTERED",{"batch_id":"same","day":1,"measured_weight_mg":5})
        assert BsfHistory(store.path).get(ident)
        tenant_context.set("farm-b")
        assert store.get(ident) is None and store.list()==[] and store.observations("same")==[]
    finally:
        tenant_context.reset(token)


def test_tenant_replay_isolation(client):
    store=client.app.state.water_quality.replay
    existing=next(iter(store.sessions.values())) if store.sessions else None
    if existing is None:
        pytest.skip("covered by separate real-flow test")
    token=tenant_context.set("other-farm")
    try:
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            store.get(existing.session_id)
        assert exc.value.status_code==404
    finally:
        tenant_context.reset(token)


def test_qa_barriers_scenario_anti_future(client):
    from app.core.config import WATER_QUALITY_ROOT
    payload=json.loads((WATER_QUALITY_ROOT / "research/replay_input_example.json").read_text(encoding="utf-8"))
    original=client.post("/water-quality/analyze",json=payload).json()
    assert original["input_verification"]=="CALLER_DECLARED_HISTORICAL_UNVERIFIED"
    assert original["provenance"]=="USER_SUPPLIED_HISTORICAL_CLAIM_WITH_AI_PREDICTIONS"
    assert original["forecasts"]["ph"]["30"]["value"]==pytest.approx(6.891136386683323)
    payload["readings"][-1]["temperature_c"]=-127
    bad=client.post("/water-quality/analyze",json=payload).json()
    assert bad["data_quality"]["parameters"]["temperature_c"]["status"]=="SENSOR_ERROR"
    assert all(f["value"] is None for hs in bad["forecasts"].values() for f in hs.values())
    payload["readings"][-1]["timestamp"]="2099-01-01T12:00:00"
    assert client.post("/water-quality/analyze",json=payload).status_code==422


def test_gateway_auth_and_streaming_limit(monkeypatch,tmp_path):
    from fastapi import FastAPI
    from app.core.security import GatewayBoundary
    from app.core import config
    monkeypatch.setenv("FISCYCLE_GATEWAY_TOKENS",json.dumps({"test-secret-a":"farm-a","test-secret-b":"farm-b"}))
    boundary=FastAPI()
    boundary.add_middleware(GatewayBoundary)
    store=BsfHistory(tmp_path / "auth.sqlite3")
    @boundary.post("/records")
    def create():
        return {"id":store.add("TEST","USER_ENTERED",{"measured":4})}
    @boundary.get("/records/{ident}")
    def read(ident:int):
        from fastapi import HTTPException
        result=store.get(ident)
        if not result: raise HTTPException(404,"Not found")
        return result
    with TestClient(boundary) as c:
        assert c.post("/records").status_code==401
        assert c.post("/records",headers={"Authorization":"Bearer wrong"}).status_code==401
        ident=c.post("/records",headers={"Authorization":"Bearer test-secret-a"}).json()["id"]
        assert c.get(f"/records/{ident}",headers={"Authorization":"Bearer test-secret-b","X-Tenant-ID":"farm-a"}).status_code==404
        assert c.get(f"/records/{ident}",headers={"Authorization":"Bearer test-secret-a"}).status_code==200
        monkeypatch.setattr(config,"MAX_BODY_BYTES",8)
        response=c.post("/records",headers={"Authorization":"Bearer test-secret-a"},content=iter([b"123456",b"7890"]))
        assert response.status_code==413


def test_corrupt_replay_seeds_rejected(client,tmp_path,monkeypatch):
    import app.services.water_quality as water_module
    import app.services.bsf_intelligence as bsf_module
    directory=tmp_path / "water_assets/replay";directory.mkdir(parents=True)
    seed=directory / "water_replay_v1.csv";seed.write_text("corrupt")
    seed.with_suffix(".metadata.json").write_text(json.dumps({"version":"water_replay_v1","sha256":"wrong"}))
    monkeypatch.setattr(water_module,"WATER_QUALITY_ROOT",directory.parent)
    with pytest.raises(ValueError,match="checksum"):
        water_module.WaterQualityService()
    bsf_seed=tmp_path / "bsf.csv";bsf_seed.write_text("corrupt")
    bsf_seed.with_suffix(".metadata.json").write_text(json.dumps({"version":"bsf_replay_development_v1","sha256":"wrong"}))
    monkeypatch.setattr(bsf_module,"BSF_REPLAY_CSV",bsf_seed)
    with pytest.raises(ValueError,match="checksum"):
        client.app.state.bsf_intelligence._load_development_trajectories()


def test_frozen_water_numeric_parity(client):
    import importlib.util
    from app.core.config import WATER_QUALITY_ROOT
    path=WATER_QUALITY_ROOT / "water_quality.py"
    spec=importlib.util.spec_from_file_location("frozen_water_reference",path)
    original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
    payload=json.loads((WATER_QUALITY_ROOT / "research/replay_input_example.json").read_text(encoding="utf-8"))
    expected=original.WaterQualityEngine().infer(payload)
    actual=client.app.state.water_quality.engine.infer(payload)
    assert expected["forecasts"]==actual["forecasts"]
    assert expected["data_quality"]==actual["data_quality"]
