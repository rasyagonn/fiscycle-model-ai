"""Executable standalone smoke suite for an extracted generated handover service."""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import atexit
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import torch
from fastapi.testclient import TestClient
from PIL import Image

SERVICE = Path(__file__).resolve().parent
assert Path.cwd().resolve() == SERVICE, "Run from extracted service/: python verify_package.py"
assert (SERVICE / "bsf_assets").is_dir()
_verification_dir = Path(tempfile.mkdtemp(prefix="verify_", dir=SERVICE))
atexit.register(lambda: shutil.rmtree(_verification_dir, ignore_errors=True))
os.environ["FISCYCLE_BSF_HISTORY_DB"] = str(_verification_dir / "history.sqlite3")

from app.core.config import BSF_ROOT  # noqa: E402
from app.main import app  # noqa: E402
from app.services.bsf_intelligence import BsfHistory  # noqa: E402
from app.services.bsf_models import BsfModelRuntime, a2_tensor, fixed_canvas  # noqa: E402

assert BSF_ROOT == (SERVICE / "bsf_assets").resolve(), "Research workspace dependency detected"
reference = json.loads((SERVICE / "fixtures/golden_reference.json").read_text(encoding="utf-8"))
fixture = json.loads((SERVICE / "fixtures/fixture_metadata.json").read_text(encoding="utf-8"))


def check(label: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(label)
    print("PASS:", label)


def main() -> None:
    model = BsfModelRuntime()
    a1_raw = (SERVICE / "fixtures/a1_development_train.jpg").read_bytes()
    a2_raw = (SERVICE / "fixtures/a2_development_train.jpg").read_bytes()
    roi = fixture["a2"]["roi_bbox"]
    with Image.open(io.BytesIO(a2_raw)) as im:
        prepared, geometry = fixed_canvas(im, roi, model.preprocessing["canvas_size"])
        tensor = a2_tensor(prepared, 224)
    check("A2 native pixel canvas matches golden pixels", hashlib.sha256(prepared.tobytes()).hexdigest() == reference["a2_prepared_sha256"])
    check("A2 normalized tensor matches golden bytes", hashlib.sha256(tensor.numpy().tobytes()).hexdigest() == reference["a2_tensor_sha256"])
    check("A2 geometry is 2048 source to 224 network", geometry["scale_factor"] == 224 / 2048)
    check("real CPU tensor operation", float((torch.tensor([2.0]) * 3)[0]) == 6.0)
    with TestClient(app) as client:
        check("standalone health", client.get("/health").json()["ready"] is True)
        check("standalone frontend", client.get("/bsf-intelligence").status_code == 200)
        check("Water Quality included in combined export", client.get("/water-quality/models").status_code == 200)
        from app.integration_checks import run_integrated_checks
        run_integrated_checks(client, check)
        from app.gallery_checks import run_gallery_checks
        run_gallery_checks(client, check)
        water_reference = json.loads((SERVICE / "fixtures/water_reference.json").read_text(encoding="utf-8"))
        water_output = client.post("/water-quality/analyze", json=water_reference["input"]).json()
        check("Water nine golden forecasts preserved", all(math.isclose(f["value"], water_reference["expected_forecasts"][p][h]["value"], abs_tol=1e-8) for p, hs in water_output["forecasts"].items() for h, f in hs.items()))
        a1 = client.post("/api/v1/bsf/segment", content=a1_raw, headers={"Content-Type": "image/jpeg"})
        check("real A1 inference HTTP 200", a1.status_code == 200)
        result = a1.json()
        check("A1 golden count and polygons", result["visible_instance_count"] == reference["a1_visible_instance_count"] and len(result["instances"]) == result["visible_instance_count"] and all(len(item["polygon_xy"]) >= 3 for item in result["instances"]))
        if reference["a1_first_polygon_xy"]:
            check("A1 first polygon original-image coordinates", math.isclose(result["instances"][0]["polygon_xy"][0][0], reference["a1_first_polygon_xy"][0][0], abs_tol=1))
        check("A1 invalid image rejected", client.post("/api/v1/bsf/segment", content=b"bad", headers={"Content-Type": "image/jpeg"}).status_code == 422)
        query = "&".join(f"{name}={number}" for name, number in zip(("x0", "y0", "x1", "y1"), roi))
        a2 = client.post(f"/api/v1/bsf/estimate-weight?{query}&reviewed_roi=true", content=a2_raw, headers={"Content-Type": "image/jpeg"})
        check("real A2 inference HTTP 200", a2.status_code == 200)
        check("A2 golden mg output", math.isclose(a2.json()["predicted_measured_weight_mg"], reference["a2_predicted_measured_weight_mg"], abs_tol=1e-4))
        check("unreviewed A2 ROI rejected", client.post(f"/api/v1/bsf/estimate-weight?{query}", content=a2_raw, headers={"Content-Type": "image/jpeg"}).status_code == 422)
        check("invalid A2 ROI rejected", client.post("/api/v1/bsf/estimate-weight?x0=-1&y0=0&x1=1&y1=1&reviewed_roi=true", content=a2_raw, headers={"Content-Type": "image/jpeg"}).status_code == 422)
        features = reference["b1_features"]
        b1 = client.post("/api/v1/bsf/forecast", json={**features, "input_provenance": "SYNTHETIC_SCENARIO"})
        check("real B1 forecast HTTP 200", b1.status_code == 200)
        check("B1 golden mg output", math.isclose(b1.json()["predicted_next_weight_mg"], reference["b1_predicted_next_weight_mg"], abs_tol=1e-8))
        check("unsupported forecast provenance rejected", client.post("/api/v1/bsf/forecast", json={**features, "input_provenance": "HISTORICAL_RESEARCH"}).status_code == 422)
        listed = client.get("/api/v1/bsf/replay/trajectories").json()["trajectories"]
        check("16 development-only replay trajectories", len(listed) == 16 and all(not t["trajectory_id"].endswith("-5") for t in listed))
        check("replay experiment/treatment/replicate identities explicit",
              all(t["curation_experiment_id"] == "mendeley_k435zc736t_v1" and
                  t["treatment_id"] == "moisture_" + t["trajectory_id"].split("-")[0] and
                  t["replicate_number"] == int(t["trajectory_id"].split("-")[1]) for t in listed))
        ident = listed[0]["trajectory_id"]
        replay = client.get(f"/api/v1/bsf/replay/{ident}?revealed=3").json()
        check("replay uses visible measured history only", replay["forecast"]["input_features"]["current_weight_mg"] == replay["observations"][-1]["measured_weight_mg"] and replay["evaluation_scope"] == "IN_SAMPLE_DEVELOPMENT_REPLAY" and not replay["independent_validation"])
        check("unknown replay rejected", client.get("/api/v1/bsf/replay/45-5").status_code == 404)
        dss = client.post("/api/v1/bsf/decision-support", json={"data_mode": "USER_ENTERED"})
        check("DSS abstains and requests data", dss.status_code == 200 and "BSF-OBS-001" in dss.json()["triggered_rule_ids"])
        check("history excludes image bytes", "overlay_png_base64" not in client.get(f"/api/v1/bsf/history/{result['history_id']}").json()["result"])
        obs = client.post("/api/v1/bsf/observations", json={"batch_id": "handover-test", "day": 1, "measured_weight_mg": 50})
        check("operational observation stored separately", obs.status_code == 201 and client.get("/api/v1/bsf/observations?batch_id=handover-test").json()["observations"][-1]["measured_weight_mg"] == 50)
    reopened = BsfHistory(Path(os.environ["FISCYCLE_BSF_HISTORY_DB"]))
    check("SQLite survives service restart", any(x["kind"] == "USER_OBSERVATION" for x in reopened.list(100)))
    customization = "import os; os.environ['FISCYCLE_BSF_API_PREFIX']='/custom/bsf'; from app.main import app; from fastapi.testclient import TestClient;\nwith TestClient(app) as c: assert c.get('/custom/bsf/health').status_code==200; assert c.get('/custom/bsf/models').status_code==200; assert c.get('/bsf-intelligence').text.find('content=\"/custom/bsf\"')>=0"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SERVICE)
    custom = subprocess.run([sys.executable, "-c", customization], cwd=SERVICE, env=env, capture_output=True, text=True)
    check("configurable endpoint prefix leaves AI core intact", custom.returncode == 0)
    production_code = "from app.main import app\nfrom fastapi.testclient import TestClient\ntry:\n    with TestClient(app): pass\nexcept RuntimeError as exc:\n    assert 'tenant isolation' in str(exc)\nelse:\n    raise AssertionError('production must be blocked')"
    guarded = subprocess.run([sys.executable, "-c", production_code], cwd=SERVICE,
                             env={**env, "FISCYCLE_RUNTIME_ENV": "production"}, capture_output=True, text=True)
    check("unauthenticated production startup blocked", guarded.returncode == 0)
    print("Standalone package smoke suite complete")


if __name__ == "__main__":
    main()
