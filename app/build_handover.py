"""Build the generated, standalone Smart BSF research handover from root app/.

Run from the repository root: python -m app.build_handover
The output directory is disposable; edit app/ and rebuild instead.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from PIL import Image

from app.core.config import APP_DIR, BSF_ROOT, REPOSITORY_ROOT

ROOT = REPOSITORY_ROOT
OUTPUT = ROOT / "FISCYCLE_DEV_HANDOVER"
RELEASE = "fiscycle-integrated-research-mvp-2.1.0-gallery"
REPLAY_VERSION = "bsf_replay_development_v1"
REPLAY_COLUMNS = ["replicate_id", "moisture_percent", "measurement_index_1based", "elapsed_days",
                  "current_weight_mg", "previous_weight_mg", "previous_elapsed_days"]
APP_FILES = [
    "__init__.py", "main.py", "run.py", "core/__init__.py", "core/config.py", "core/http.py",
    "routers/__init__.py", "routers/bsf.py", "routers/bsf_intelligence.py", "routers/health.py",
    "schemas/__init__.py", "schemas/bsf.py", "services/__init__.py", "services/bsf.py",
    "services/bsf_models.py", "services/bsf_intelligence.py", "services/bsf_decisions.py",
    "static/bsf.html", "static/fiscycle-icon.svg", "static/manifest.webmanifest", "static/sw.js",
]
MODEL_FILES = ["bsf_b1_inference.py", "bsf_model_b1_estimator.joblib",
               "bsf_model_b1_model_metadata.json", "bsf_model_b1_uncertainty.json"]
APP_FILES += ["core/security.py", "routers/integration.py", "routers/water_quality.py", "schemas/water_quality.py",
    "services/water_quality.py", "services/water_core.py", "services/water_insights.py", "services/bsf_photo.py",
    "static/dashboard.html", "static/ecosystem.html", "static/integration.js", "static/integration.css", "static/gateway.js",
    "integration_checks.py", "core/artifacts.py", "runtime_artifacts.json"]
APP_FILES += ["routers/bsf_gallery.py", "services/bsf_gallery.py", "services/bsf_gallery_roi.py", "gallery_checks.py",
    "static/gallery.html", "static/gallery.js", "static/gallery.css", "tests/__init__.py", "tests/test_gallery_portable.py"]


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy(source: Path, target: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"Required build input missing: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def source_revision() -> str | None:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def build_replay(service: Path) -> dict:
    source = BSF_ROOT / "hasil/v2/internal/bsf_model_b1_development_oof_residuals.csv"
    metadata = json.loads((BSF_ROOT / "models/bsf_model_b1_model_metadata.json").read_text(encoding="utf-8"))
    frame = pd.read_csv(source, usecols=REPLAY_COLUMNS)
    if set(frame.replicate_id) != set(metadata["development_replicates"]):
        raise ValueError("Development replay groups differ from frozen B1 metadata")
    if set(frame.replicate_id) & set(metadata["excluded_final_test_replicates"]):
        raise ValueError("Reserved final-test replicate in replay")
    frame = frame[REPLAY_COLUMNS].sort_values(["replicate_id", "elapsed_days"], kind="stable")
    parts = frame.replicate_id.str.extract(r"^(45|55|65|75)-([1-4])$")
    if parts.isna().any().any() or not (parts[0].astype(float).to_numpy() == frame.moisture_percent.to_numpy()).all():
        raise ValueError("Replay treatment/replicate IDs do not match source rows")
    frame.insert(0, "curation_experiment_id", "mendeley_k435zc736t_v1")
    frame.insert(1, "treatment_id", "moisture_" + parts[0])
    frame.insert(2, "replicate_number", parts[1].astype(int))
    frame.insert(3, "trajectory_id", frame.replicate_id)
    path = service / "bsf_assets/replay" / f"{REPLAY_VERSION}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, float_format="%.12g", lineterminator="\n")
    meta = {"version": REPLAY_VERSION, "sha256": digest(path), "rows": len(frame),
            "replicate_count": frame.replicate_id.nunique(), "columns": list(frame.columns),
            "source": "Mendeley Data v1, DOI 10.17632/k435zc736t.1", "license": "CC BY 4.0",
            "scope": "IN_SAMPLE_DEVELOPMENT_REPLAY", "independent_validation": False,
            "excluded_final_test_replicates": metadata["excluded_final_test_replicates"],
            "source_file_sha256": digest(source),
            "meaning": "Research observations from B1 development folds; no future target is supplied to inference.",
            "identifier_note": "curation_experiment_id and treatment_id are transparent curation identifiers derived from source DOI and replicate_id, not original published field names."}
    write(path.with_suffix(".metadata.json"), json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    index = [{"trajectory_id": key, "curation_experiment_id": "mendeley_k435zc736t_v1",
              "treatment_id": "moisture_" + key.split("-")[0], "replicate_number": int(key.split("-")[1]),
              "moisture_percent": float(group.moisture_percent.iloc[0]),
              "observation_count": len(group) + 1} for key, group in frame.groupby("replicate_id", sort=True)]
    write(path.parent / "trajectory_index.json", json.dumps(index, indent=2) + "\n")
    return meta


def build_fixtures(service: Path) -> dict:
    # Both fixtures are development TRAIN images from Zenodo, never reserved test data.
    a1 = next(iter(sorted((BSF_ROOT / "hasil/model_a_training_v1/a1_dataset/images/train").glob("*.jpg"))), None)
    if a1 is None:
        raise FileNotFoundError("A1 training fixture missing")
    copy(a1, service / "fixtures/a1_development_train.jpg")
    geometry = json.loads((BSF_ROOT / "hasil/model_a2_training_v3/geometry.json").read_text(encoding="utf-8"))
    selected = next((row for row in geometry if row["id"] == "A2_0001"), None)
    if selected is None or selected.get("split") not in (None, "train"):
        raise ValueError("A2 train fixture not confirmed")
    with zipfile.ZipFile(BSF_ROOT / selected["archive_path"]) as archive:
        raw = archive.read(selected["archive_member"])
    with Image.open(io.BytesIO(raw)) as im:
        if im.size != (4056, 3040):
            raise ValueError("A2 fixture source resolution mismatch")
    fixture = service / "fixtures/a2_development_train.jpg"
    fixture.write_bytes(raw)
    record = {"a1": {"file": "a1_development_train.jpg", "sha256": digest(service / "fixtures/a1_development_train.jpg")},
              "a2": {"file": fixture.name, "sha256": digest(fixture), "roi_bbox": selected["roi_bbox"],
                     "source_id": selected["id"]},
              "source": "Geissmann, Black Soldier Fly detection, phenotyping and sex prediction dataset, Zenodo v1, DOI 10.5281/zenodo.13359376, CC BY 4.0",
              "usage": "Two development training images solely for executable smoke tests; not representative validation data."}
    write(service / "fixtures/fixture_metadata.json", json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    return record


def make_golden(service: Path, fixture: dict) -> dict:
    from app.services.bsf_models import BsfModelRuntime, a2_tensor, fixed_canvas
    from app.services.bsf import BsfService
    core = BsfModelRuntime()
    with Image.open(service / "fixtures/a1_development_train.jpg") as im:
        a1 = core.segment(im.convert("RGB"))
    with Image.open(service / "fixtures/a2_development_train.jpg") as im:
        image = im.convert("RGB")
        roi = fixture["a2"]["roi_bbox"]
        prepared, _ = fixed_canvas(image, roi, core.preprocessing["canvas_size"])
        tensor = a2_tensor(prepared, 224)
        a2 = core.estimate_weight(image, roi, True)
    import torch
    b1 = BsfService()
    features = {"moisture_percent": 55.0, "elapsed_days": 5.0, "current_weight_mg": 90.0,
                "previous_weight_mg": 70.0, "recent_growth_mg_per_day": 20.0,
                "forecast_horizon_days": 1.0}
    prediction = b1.predict(features, "SYNTHETIC_SCENARIO")
    reference = {"a1_visible_instance_count": a1["visible_instance_count"],
                 "a1_first_polygon_xy": a1["instances"][0]["polygon_xy"] if a1["instances"] else [],
                 "a2_predicted_measured_weight_mg": a2["predicted_measured_weight_mg"],
                 "a2_prepared_sha256": hashlib.sha256(prepared.tobytes()).hexdigest(),
                 "a2_tensor_sha256": hashlib.sha256(tensor.numpy().tobytes()).hexdigest(),
                 "b1_features": features, "b1_predicted_next_weight_mg": prediction["predicted_next_weight_mg"],
                 "pytorch_version": torch.__version__, "device": "cpu",
                 "fixture_scope": "DEVELOPMENT_TRAIN_SMOKE_ONLY"}
    write(service / "fixtures/golden_reference.json", json.dumps(reference, indent=2) + "\n")
    return reference


def build() -> Path:
    if ROOT.resolve() != Path(__file__).resolve().parents[1]:
        raise RuntimeError("Unexpected repository root")
    if OUTPUT.resolve().parent != ROOT.resolve() or OUTPUT.name != "FISCYCLE_DEV_HANDOVER":
        raise RuntimeError("Unsafe handover output path")
    stage = Path(tempfile.mkdtemp(prefix=".handover_stage_", dir=ROOT))
    try:
        service = stage / "service"
        for relative in APP_FILES:
            copy(APP_DIR / relative, service / "app" / relative)
        for relative in MODEL_FILES:
            copy(BSF_ROOT / "models" / relative, service / "bsf_assets/models" / relative)
        copy(BSF_ROOT / "hasil/model_a_training_v1/a1_initial/weights/best.pt",
             service / "bsf_assets/hasil/model_a_training_v1/a1_initial/weights/best.pt")
        for name in ("best.pt", "preprocessing_config.json", "COMPLETE.json"):
            copy(BSF_ROOT / "hasil/model_a2_training_v3" / name,
                 service / "bsf_assets/hasil/model_a2_training_v3" / name)
        replay = build_replay(service)
        from app.handover_extension import build_water, combined_docs
        water = build_water(service, copy, write, digest)
        fixture = build_fixtures(service)
        make_golden(service, fixture)
        combined_docs(stage, water, replay, write)
        copy(ROOT / "FISCYCLE_TEAM_INTEGRATION_GUIDE.md", stage / "docs/PRODUCT_MVP_INTEGRATION_GUIDE.md")
        product_readme = stage / "README.md"
        write(product_readme, product_readme.read_text(encoding="utf-8") + "\n\nProduct frontend/server integration: start with docs/PRODUCT_MVP_INTEGRATION_GUIDE.md. The included HTML is an internal reference UI; product teams may build their own UI/public backend routes. Online staging deployment has not been performed.\n")
        from app.gallery_bundle import export_gallery, BUNDLE
        gallery = export_gallery(service, copy, write)
        from app.gallery_docs import write_gallery_docs
        write_gallery_docs(stage, gallery, write)
        copy(APP_DIR / "handover_verify.py", service / "verify_package.py")
        copy(APP_DIR / "handover_checksums.py", stage / "verify_checksums.py")
        verification = subprocess.run([sys.executable, "verify_package.py"], cwd=service,
                                      env={**os.environ, "PYTHONPATH": str(service), "PYTHONDONTWRITEBYTECODE": "1", "FISCYCLE_BSF_GALLERY_DATA": str(BUNDLE)},
                                      capture_output=True, text=True, check=False)
        if verification.returncode:
            raise RuntimeError("Staged handover smoke test failed:\n" + verification.stdout + verification.stderr)
        # The smoke suite creates a private SQLite file. It must never be distributed.
        for transient in list(service.rglob("*")):
            if transient.is_dir() and (transient.name == "__pycache__" or
                                       transient.parent == service and transient.name.startswith("verify_")):
                if not transient.resolve().is_relative_to(stage.resolve()):
                    raise RuntimeError("Unsafe staging cleanup target")
                shutil.rmtree(transient)
        if any(p.suffix in {".pyc", ".sqlite3"} for p in stage.rglob("*")):
            raise RuntimeError("Transient cache or database remains in package")
        checks = [line for line in verification.stdout.splitlines() if line.startswith("PASS:")]
        write(stage / "VERIFICATION_REPORT.md", "# Build-time verification\n\n"
              f"Executable standalone smoke suite: **PASS ({len(checks)} checks)** in isolated staging service.\n\n"
              + "\n".join("- " + line for line in checks) +
              "\n\nRun `python verify_checksums.py` from package root and `python verify_package.py` from `service/` after extraction. Independent extraction, clean dependency installation and Docker evidence are recorded in the repository root verification report.\n")
        from app.main import app
        write(stage / "openapi.json", json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n")
        artifacts = {
            "a1_checkpoint": "service/bsf_assets/hasil/model_a_training_v1/a1_initial/weights/best.pt",
            "a2_checkpoint": "service/bsf_assets/hasil/model_a2_training_v3/best.pt",
            "a2_preprocessing": "service/bsf_assets/hasil/model_a2_training_v3/preprocessing_config.json",
            "b1_estimator": "service/bsf_assets/models/bsf_model_b1_estimator.joblib",
            "b1_metadata": "service/bsf_assets/models/bsf_model_b1_model_metadata.json",
            "replay_seed": f"service/bsf_assets/replay/{REPLAY_VERSION}.csv",
            "dss_rules": "service/app/services/bsf_decisions.py",
            "dependencies": "service/requirements.txt",
            "water_model_manifest": "service/water_assets/models/mvp_v2/manifest.json",
            "water_replay_seed": "service/water_assets/replay/water_replay_v1.csv",
            "water_qa_and_inference": "service/app/services/water_core.py",
            "water_dss_rules": "service/app/services/water_insights.py",
            "photo_dss_and_geometry": "service/app/services/bsf_photo.py",
            "gallery_image_manifest": "service/bsf_assets/gallery/manifest.json",
            "gallery_final_evaluation": "service/bsf_assets/gallery/final_evaluation.json",
            "gallery_evaluation_protocol": "service/bsf_assets/gallery/evaluation_protocol.json",
            "gallery_inference_cache_baseline": "service/bsf_assets/gallery/baseline_results.jsonl",
            "gallery_jobs_and_cache": "service/app/services/bsf_gallery.py",
        }
        manifest = {"release_id": RELEASE, "build_timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "source_revision": source_revision(), "api_version": app.version,
                    "model_versions": {"water_a": "deterministic_qa_v2", "water_b": "water-replay-v2", "water_c": "water_dss_engineering_v2", "a1": "a1_initial", "a2": "model_a2_training_v3", "b1": "frozen_v1"},
                    "a2_preprocessing_version": "fixed_native_pixel_canvas_v1",
                    "replay_version": {"bsf": REPLAY_VERSION, "water":"water_replay_v1"}, "dss_rule_version": {"growth":"bsf_dss_observation_v1","photo":"bsf_photo_geometry_v1","water":"water_dss_engineering_v2"},
                    "artifacts": {key: {"path": rel, "sha256": digest(stage / rel)} for key, rel in artifacts.items()},
                    "package_integrity": "CHECKSUMS.sha256 covers all payload files excluding itself"}
        manifest["gallery_version"]="bsf_gallery_v1"
        manifest["optional_artifacts"]={"complete_test_images":gallery}
        write(stage / "HANDOVER_MANIFEST.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        write(stage / "HANDOVER_MANIFEST.md", "# Handover manifest\n\n" +
              f"Release `{RELEASE}`; built `{manifest['build_timestamp_utc']}`; source revision `{manifest['source_revision'] or 'UNAVAILABLE_NO_GIT_REPOSITORY'}`.\n\n" +
              "| Artifact | SHA-256 |\n|---|---|\n" + "".join(f"| {key} | `{item['sha256']}` |\n" for key, item in manifest["artifacts"].items()))
        lines = [f"{digest(p)}  {p.relative_to(stage).as_posix()}" for p in sorted(stage.rglob("*")) if p.is_file() and p.name != "CHECKSUMS.sha256"]
        write(stage / "CHECKSUMS.sha256", "\n".join(lines) + "\n")
        if OUTPUT.exists():
            if not OUTPUT.is_dir() or OUTPUT.is_symlink():
                raise RuntimeError("Handover target is not an ordinary directory")
            shutil.rmtree(OUTPUT)
        stage.rename(OUTPUT)
        return OUTPUT
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__ == "__main__":
    print(build())
