"""Verify immutable, trusted runtime copies before deserializing checkpoints."""
import hashlib
import json
import os
from app.core.config import APP_DIR, BSF_ROOT, WATER_QUALITY_ROOT


def verify_domain(domain, keys=None):
    root = {"bsf": BSF_ROOT, "water": WATER_QUALITY_ROOT}[domain]
    if os.getenv("FISCYCLE_SKIP_REGISTRY_BOOTSTRAP") != "1":
        from app.core.model_registry import REPORTS
        required = keys or (["water"] if domain=="water" else ["bsf_a1","bsf_a2","bsf_b1"])
        if any(not REPORTS.get(key,{}).get("artifacts_verified") for key in required):
            raise ValueError("Requested model source did not pass artifact verification")
    expected = json.loads((APP_DIR / "runtime_artifacts.json").read_text(encoding="utf-8"))[domain]
    if keys is not None:
        from app.core.model_registry import load_registry
        entries = load_registry()["models"]
        names = {name for key in keys for name in entries[key]["files"]}
        expected = {name:value for name,value in expected.items() if name in names}
    for rel, value in expected.items():
        path = (root / rel).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Runtime artifact missing")
        if hashlib.sha256(path.read_bytes()).hexdigest() != value:
            raise ValueError("Runtime artifact checksum mismatch")
    return expected

