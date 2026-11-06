"""Focused real-artifact integration tests; development images only."""
from __future__ import annotations

import io
import json
import sys
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import BSF_ROOT
from app.main import app
from app.services.bsf_intelligence import BsfHistory, V3


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    with TestClient(app) as test:
        assert test.get("/api/v1/bsf/health").json()["ready"] is True
        test.app.state.bsf_intelligence.history = BsfHistory(tmp_path_factory.mktemp("bsf_history") / "history.sqlite3")
        yield test


def test_existing_water_and_one_app_frontend_survive(client):
    assert client.get("/health").json()["services"]["bsf_intelligence"]["ready"] is True
    assert client.get("/").status_code == 200
    page = client.get("/bsf-intelligence")
    assert page.status_code == 200
    assert "Kualitas Air" in page.text and "Smart BSF" in page.text
    assert all(name in page.text for name in ["Ringkasan BSF", "Analisis Foto", "Pertumbuhan", "Dukungan Keputusan", "Riwayat"])
    assert "@media(max-width:850px)" in page.text
    assert client.get("/manifest.webmanifest").status_code == 200
    assert client.get("/sw.js").status_code == 200
    assert client.get("/water-quality/models").status_code == 200


def test_replay_is_real_chronological_and_has_no_future_weight_input(client):
    listed = client.get("/api/v1/bsf/replay/trajectories").json()["trajectories"]
    assert len(listed) == 16
    assert all(not item["trajectory_id"].endswith("-5") for item in listed)
    ident = listed[0]["trajectory_id"]
    initial = client.get(f"/api/v1/bsf/replay/{ident}?revealed=3").json()
    assert initial["revealed"] == len(initial["observations"]) == 3
    assert [row["day"] for row in initial["observations"]] == sorted(row["day"] for row in initial["observations"])
    feature = initial["forecast"]["input_features"]
    assert feature["previous_weight_mg"] == initial["observations"][-2]["measured_weight_mg"]
    assert feature["current_weight_mg"] == initial["observations"][-1]["measured_weight_mg"]
    assert feature["forecast_horizon_days"] == 1.0
    assert initial["forecast"]["result"]["predicted_next_weight_mg"] is not None
    assert "target_weight_mg" not in feature
    service = client.app.state.bsf_intelligence
    hidden = service.trajectories[ident]["observations"][3]["measured_weight_mg"]
    try:
        service.trajectories[ident]["observations"][3]["measured_weight_mg"] = hidden + 90
        changed = client.get(f"/api/v1/bsf/replay/{ident}?revealed=3").json()
        assert changed["forecast"]["input_features"] == initial["forecast"]["input_features"]
        assert changed["forecast"]["result"] == initial["forecast"]["result"]
    finally:
        service.trajectories[ident]["observations"][3]["measured_weight_mg"] = hidden
    assert client.get(f"/api/v1/bsf/replay/{ident}?revealed=999").status_code == 422
    assert client.get("/api/v1/bsf/replay/45-5").status_code == 404


def test_replay_comparison_only_when_target_day_matches(client):
    ident = client.get("/api/v1/bsf/replay/trajectories").json()["trajectories"][0]["trajectory_id"]
    total = client.app.state.bsf_intelligence.trajectories[ident]["observations"]
    replay = client.get(f"/api/v1/bsf/replay/{ident}?revealed={len(total)}").json()
    assert len(replay["comparisons"]) == len(total) - 2
    for row in replay["comparisons"]:
        if row["time_aligned"]:
            assert row["error_mg"] == pytest.approx(row["predicted_weight_mg"] - row["observed_measured_weight_mg"])
        else:
            assert row["error_mg"] is None


def test_dss_factors_rules_and_durable_history(client):
    rules = client.get("/api/v1/bsf/rules").json()["rules"]
    assert len(rules) >= 7 and all(r["approval_status"] == "OBSERVATION_REQUEST_ONLY" for r in rules)
    assert len(client.get("/api/v1/bsf/factors").json()["factors"]) >= 30
    empty = client.post("/api/v1/bsf/decision-support", json={"data_mode": "USER_ENTERED"}).json()
    assert "BSF-OBS-001" in empty["triggered_rule_ids"]
    assert "BSF-OBS-004" in empty["triggered_rule_ids"]
    assert "average_weight_mg" in empty["missing_information"]
    assert empty["recommendations"][0]["triggered_rule_ids"] == [empty["recommendations"][0]["recommendation_id"]]
    result = client.post("/api/v1/bsf/decision-support", json={"data_mode": "USER_ENTERED", "target_weight_mg": 100,
        "observations": [{"day": 1, "measured_weight_mg": 120}, {"day": 2, "measured_weight_mg": 110}]}).json()
    assert "BSF-OBS-002" in result["triggered_rule_ids"]
    assert "BSF-OBS-005" in result["triggered_rule_ids"]
    assert "BSF-OBS-004" not in result["triggered_rule_ids"]
    assert result["recommendations"][0]["requires_human_confirmation"]
    assert client.get(f"/api/v1/bsf/recommendations/{result['history_id']}").json()["result"]["rule_version"] == result["rule_version"]
    assert client.get("/api/v1/bsf/history").json()["records"][0]["kind"] == "DSS_DECISION"
    simulated = client.post("/api/v1/bsf/decision-support", json={"data_mode": "SIMULATED", "target_weight_mg": 100,
        "observations": [{"day": 1, "measured_weight_mg": 110}, {"day": 2, "measured_weight_mg": 120}]}).json()
    assert "BSF-OBS-005" not in simulated["triggered_rule_ids"]


def test_dss_image_link_requires_explicit_user_batch(client):
    for data_mode in ("SIMULATED", "USER_ENTERED"):
        response = client.post("/api/v1/bsf/decision-support", json={
            "data_mode": data_mode, "image_record_id": 1,
        })
        assert response.status_code == 422


def test_b1_forecast_real_model_and_provenance(client):
    ident = client.get("/api/v1/bsf/replay/trajectories").json()["trajectories"][0]["trajectory_id"]
    snapshot = client.get(f"/api/v1/bsf/replay/{ident}?revealed=3").json()
    features = snapshot["forecast"]["input_features"]
    result = client.post("/api/v1/bsf/forecast", json={**features, "input_provenance": "SYNTHETIC_SCENARIO"}).json()
    assert result["predicted_next_weight_mg"] == pytest.approx(snapshot["forecast"]["result"]["predicted_next_weight_mg"])
    assert result["validation_status"] == "NOT_FIELD_VALIDATED"
    assert client.get(f"/api/v1/bsf/history/{result['history_id']}").json()["provenance"] == "SIMULATED"
    assert client.post("/api/v1/bsf/forecast", json={**features, "input_provenance": "PUBLIC_RESEARCH_DEVELOPMENT"}).status_code == 422
    assert client.post("/api/v1/bsf/forecast", json={**features, "input_provenance": "SYNTHETIC_SCENARIO", "moisture_percent": 50}).json()["input_domain_status"] == "OUT_OF_DOMAIN"


def test_user_observations_reopen_by_batch(client):
    payload = {"batch_id": "batch-uji", "day": 3, "measured_weight_mg": 144.2}
    saved = client.post("/api/v1/bsf/observations", json=payload)
    assert saved.status_code == 201
    reopened = client.get("/api/v1/bsf/observations?batch_id=batch-uji").json()
    assert reopened["provenance"] == "USER_ENTERED"
    assert reopened["observations"][-1]["measured_weight_mg"] == 144.2
    assert client.get(f"/api/v1/bsf/history/{saved.json()['history_id']}").json()["result"]["batch_id"] == "batch-uji"
    assert client.post("/api/v1/bsf/observations", json=payload).status_code == 422


def test_a1_actual_checkpoint_and_bad_upload(client):
    image = next((BSF_ROOT / "hasil/model_a_training_v1/a1_dataset/images/train").glob("*.jpg"))
    raw = image.read_bytes()
    before = A1_HASH = __import__("hashlib").sha256((BSF_ROOT / "hasil/model_a_training_v1/a1_initial/weights/best.pt").read_bytes()).hexdigest()
    output = client.post("/api/v1/bsf/segment", content=raw, headers={"Content-Type": "image/jpeg"})
    assert output.status_code == 200, output.text[:500]
    result = output.json()
    assert result["visible_instance_count"] == len(result["instances"])
    assert result["visible_instance_count"] > 0
    assert all(len(item["polygon_xy"]) >= 3 for item in result["instances"])
    assert result["overlay_png_base64"]
    assert client.get(f"/api/v1/bsf/history/{result['history_id']}").json()["result"].get("overlay_png_base64") is None
    assert __import__("hashlib").sha256((BSF_ROOT / "hasil/model_a_training_v1/a1_initial/weights/best.pt").read_bytes()).hexdigest() == before
    assert client.post("/api/v1/bsf/segment", content=b"not image", headers={"Content-Type": "image/jpeg"}).status_code == 422
    assert client.post("/api/v1/bsf/segment", content=raw, headers={"Content-Type": "text/plain"}).status_code == 422


def test_a2_exact_preprocessing_and_checkpoint(client):
    sys.path.append(str(BSF_ROOT))
    from a2_scale_v3 import fixed_canvas, predict_measured_weight, tensor
    geometry = next(g for g in json.loads((V3 / "geometry.json").read_text(encoding="utf-8")) if g["id"] == "A2_0001")
    with zipfile.ZipFile(BSF_ROOT / geometry["archive_path"]) as archive:
        raw = archive.read(geometry["archive_member"])
    with Image.open(io.BytesIO(raw)) as source:
        source.load()
        original = source.convert("RGB")
    roi = geometry["roi_bbox"]
    prepared, details = fixed_canvas(original, roi, 2048)
    assert prepared.size == (224, 224)
    assert tuple(tensor(prepared, 224).shape) == (3, 224, 224)
    assert details["scale_factor"] == 224 / 2048
    expected = predict_measured_weight(original, roi_box=roi, device="cpu")["predicted_measured_weight_mg"]
    query = "&".join(f"{key}={val}" for key, val in zip(["x0", "y0", "x1", "y1"], roi))
    output = client.post(f"/api/v1/bsf/estimate-weight?{query}&reviewed_roi=true", content=raw, headers={"Content-Type": "image/jpeg"})
    assert output.status_code == 200, output.text[:500]
    result = output.json()
    assert result["predicted_measured_weight_mg"] == pytest.approx(expected, abs=1e-4)
    assert result["preprocessing_version"] == "fixed_native_pixel_canvas_v1"
    assert result["processed_png_base64"]
    assert client.get(f"/api/v1/bsf/history/{result['history_id']}").json()["result"].get("processed_png_base64") is None
    assert client.post(f"/api/v1/bsf/estimate-weight?{query}", content=raw, headers={"Content-Type": "image/jpeg"}).status_code == 422
    assert client.post("/api/v1/bsf/estimate-weight?x0=0&y0=0&x1=128&y1=128&reviewed_roi=true",
                       content=io.BytesIO(_small_image()).getvalue(), headers={"Content-Type": "image/png"}).status_code == 422


def _small_image() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (128, 128), "white").save(out, "PNG")
    return out.getvalue()
