"""Version lock for trusted immutable runtime files. Never load a mismatched checkpoint."""
import hashlib
import json
from app.core.config import APP_DIR, BSF_ROOT, WATER_QUALITY_ROOT


def verify_domain(domain):
    root={"bsf":BSF_ROOT,"water":WATER_QUALITY_ROOT}[domain]
    registry=json.loads((APP_DIR / "runtime_artifacts.json").read_text(encoding="utf-8"))[domain]
    for name,expected in registry.items():
        path=(root / name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError("Required runtime artifact missing")
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError("Runtime artifact checksum mismatch")
    return registry
