from __future__ import annotations

from typing import Any

from app.core.config import BSF_MODELS_DIR, register_domain_paths

register_domain_paths()
from app.services.bsf_b1_inference import B1Predictor


class BsfService:
    def __init__(self) -> None:
        from app.core.artifacts import verify_domain
        verify_domain("bsf", keys=["bsf_b1"])
        self.predictor = B1Predictor(artifact_dir=BSF_MODELS_DIR)

    @property
    def metadata(self) -> dict[str, Any]:
        return self.predictor.metadata

    def predict(self, features: dict[str, float], provenance: str) -> dict[str, Any]:
        result = self.predictor.predict(features)
        result["input_provenance"] = provenance
        result["usage_scope"] = "RESEARCH_DEMO_ONLY"
        return result

