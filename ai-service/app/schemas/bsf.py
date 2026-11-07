from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class BsfNextWeightRequest(BaseModel):
    """HTTP envelope; only the six numeric features are sent to Model B1."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    input_provenance: Literal["PUBLIC_RESEARCH_HOLDOUT", "SYNTHETIC_SCENARIO"]
    moisture_percent: float
    elapsed_days: float
    current_weight_mg: float
    previous_weight_mg: float
    recent_growth_mg_per_day: float
    forecast_horizon_days: float

    def inference_features(self) -> dict[str, float]:
        return self.model_dump(exclude={"input_provenance"})

