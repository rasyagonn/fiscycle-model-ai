from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import BSF_ROOT, WATER_QUALITY_ROOT
from app.main import app


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    with TestClient(app) as test_client:
        from app.services.bsf_intelligence import BsfHistory
        directory = tmp_path_factory.mktemp("api_history")
        test_client.app.state.water_quality.history = BsfHistory(directory / "water.sqlite3")
        test_client.app.state.bsf_intelligence.history = BsfHistory(directory / "bsf.sqlite3")
        yield test_client


@pytest.fixture(scope="module")
def water_payload():
    path = WATER_QUALITY_ROOT / "research" / "replay_input_example.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def bsf_payload():
    from app.services.bsf import BsfService
    features = {"moisture_percent":55.0,"elapsed_days":5.0,"current_weight_mg":90.0,
                "previous_weight_mg":70.0,"recent_growth_mg_per_day":20.0,"forecast_horizon_days":1.0}
    return {"input_provenance":"SYNTHETIC_SCENARIO",**features}, BsfService().predict(features,"SYNTHETIC_SCENARIO")


def test_combined_health_reports_both_domains(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SIAP"
    assert body["ready"] is True
    assert body["services"]["water_quality"]["ready"] is True
    assert body["services"]["bsf"]["ready"] is True
    assert body["services"]["bsf"]["validation_status"] == "NOT_FIELD_VALIDATED"


def test_water_models_are_namespaced_and_legacy_alias_survives(client):
    current = client.get("/water-quality/models")
    legacy = client.get("/models")
    assert current.status_code == legacy.status_code == 200
    assert current.json() == legacy.json()
    rows = current.json()["models"]
    assert len(rows) == 9
    assert sum(row["is_trained_ml"] for row in rows) == 7


def test_water_reference_inference_is_unchanged(client, water_payload):
    response = client.post("/water-quality/analyze", json=water_payload)
    assert response.status_code == 200
    body = response.json()
    assert body["timezone"] == "Asia/Jakarta"
    assert body["forecasts"]["ph"]["30"]["value"] == pytest.approx(6.891136386683323)
    assert "NaN" not in response.text and "Infinity" not in response.text


def test_water_replay_uses_namespaced_routes(client):
    period = client.get("/water-quality/replay/periods").json()["periods"][0]
    created = client.post(
        "/water-quality/replay/sessions",
        json={"start": period["start"], "end": period["end"]},
    )
    assert created.status_code == 201
    session_id = created.json()["session_id"]
    advanced = client.post(f"/water-quality/replay/sessions/{session_id}/next")
    assert advanced.status_code == 200
    assert advanced.json()["processed_observations"] == 1


def test_water_replay_keeps_pond_provenance_and_replaces_session(client):
    period = client.get("/water-quality/replay/periods").json()["periods"][0]
    assert period["pond_id"] == "fiscycle_local_pond_unknown"
    wrong = client.post("/water-quality/replay/sessions", json={"start": period["start"],
        "end": period["end"], "pond_id": "another_pond"})
    assert wrong.status_code == 422
    first = client.post("/water-quality/replay/sessions", json={"start": period["start"],
        "end": period["end"], "pond_id": period["pond_id"]})
    assert first.status_code == 201
    old_id = first.json()["session_id"]
    second = client.post("/water-quality/replay/sessions", json={"start": period["start"],
        "end": period["end"], "pond_id": period["pond_id"], "replace_session_id": old_id})
    assert second.status_code == 201
    assert second.json()["session_id"] != old_id
    assert client.get(f"/water-quality/replay/sessions/{old_id}").status_code == 404


def test_bsf_reference_prediction_and_disclosures(client, bsf_payload):
    payload, expected = bsf_payload
    response = client.post("/bsf/next-weight", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["predicted_next_weight_mg"] == pytest.approx(expected["predicted_next_weight_mg"])
    assert body["input_domain_status"] == "IN_DOMAIN"
    assert body["input_provenance"] == "SYNTHETIC_SCENARIO"
    assert body["model_status"] == "RESEARCH_PROTOTYPE"
    assert body["validation_status"] == "NOT_FIELD_VALIDATED"
    assert body["usage_scope"] == "RESEARCH_DEMO_ONLY"


def test_bsf_requires_explicit_provenance(client, bsf_payload):
    payload, _ = bsf_payload
    payload = dict(payload)
    payload.pop("input_provenance")
    response = client.post("/bsf/next-weight", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"] == "Data request tidak valid"


def test_bsf_out_of_domain_is_not_served_as_normal_prediction(client, bsf_payload):
    payload, _ = bsf_payload
    payload = {**payload, "moisture_percent": 50.0}
    response = client.post("/bsf/next-weight", json=payload)
    assert response.status_code == 422
    assert response.json()["input_domain_status"] == "OUT_OF_DOMAIN"
    assert response.json()["predicted_next_weight_mg"] is None


def test_dashboard_calls_namespaced_water_routes(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "/water-quality/replay/periods" in response.text
    assert "/water-quality/replay/sessions" in response.text
    assert "6.891136" not in response.text


def test_openapi_exposes_domain_routes_not_legacy_aliases(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/water-quality/analyze" in paths
    assert "/water-quality/replay/periods" in paths
    assert "/bsf/next-weight" in paths
    assert "/replay/periods" not in paths
    assert "/models" not in paths


def test_domains_fail_independently(client):
    water = client.app.state.water_quality
    try:
        client.app.state.water_quality = None
        health = client.get("/health").json()
        assert health["status"] == "DEGRADED"
        assert health["services"]["water_quality"]["ready"] is False
        assert health["services"]["bsf"]["ready"] is True
        assert client.get("/water-quality/models").status_code == 503
        assert client.get("/bsf/models").status_code == 200
    finally:
        client.app.state.water_quality = water

