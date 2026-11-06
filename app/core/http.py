from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd
from fastapi.responses import JSONResponse


def normalize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): normalize_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_json(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def api_json(value: Any, status_code: int = 200) -> JSONResponse:
    content = normalize_json(value)
    json.dumps(content, allow_nan=False)
    return JSONResponse(content=content, status_code=status_code)

