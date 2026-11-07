from __future__ import annotations

import math
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.config import register_domain_paths

register_domain_paths()
from app.services.water_core import timestamp

MAX_READINGS = 1_000
MAX_REPLAY_HOURS = 24


def parse_naive_timestamp(value: str, field_name: str) -> str:
    parsed = timestamp(value)
    if pd.isna(parsed):
        raise ValueError(
            f"{field_name} harus berupa timestamp ISO lokal tanpa suffix timezone; "
            "nilainya dibaca sebagai WIB"
        )
    return parsed.isoformat()


class Reading(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: str
    ph: float | str | None
    temperature_c: float | str | None
    turbidity_ntu: float | str | None
    pond_id: str | None = None

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        return parse_naive_timestamp(value, "timestamp pembacaan")

    @field_validator("ph", "temperature_c", "turbidity_ntu")
    @classmethod
    def reject_non_finite_number(cls, value: float | str | None):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Nilai NaN atau Infinity tidak diterima")
        return value

    @field_validator("pond_id")
    @classmethod
    def validate_optional_pond(cls, value: str | None):
        if value is not None and not value.strip():
            raise ValueError("pond_id pada pembacaan tidak boleh kosong")
        return value.strip() if value else value


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pond_id: str
    mode: Literal["historical_replay"]
    current_timestamp: str
    readings: list[Reading] = Field(default_factory=list, max_length=MAX_READINGS)

    @field_validator("pond_id")
    @classmethod
    def validate_pond(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("pond_id tidak boleh kosong")
        return value.strip()

    @field_validator("current_timestamp")
    @classmethod
    def validate_current_timestamp(cls, value: str) -> str:
        return parse_naive_timestamp(value, "current_timestamp")

    @model_validator(mode="after")
    def validate_history(self):
        now = pd.Timestamp(self.current_timestamp)
        for row in self.readings:
            if pd.Timestamp(row.timestamp) > now:
                raise ValueError("Pembacaan masa depan relatif terhadap current_timestamp tidak diterima")
            if row.pond_id is not None and row.pond_id != self.pond_id:
                raise ValueError("Satu request tidak boleh mencampur pond_id")
        return self


class ReplayCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: str
    end: str
    pond_id: str = "fiscycle_local_pond_unknown"
    replace_session_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")

    @field_validator("start", "end")
    @classmethod
    def validate_times(cls, value: str, info) -> str:
        return parse_naive_timestamp(value, info.field_name)

    @field_validator("pond_id")
    @classmethod
    def validate_pond(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("pond_id tidak boleh kosong")
        return value.strip()

    @model_validator(mode="after")
    def validate_range(self):
        start, end = pd.Timestamp(self.start), pd.Timestamp(self.end)
        if end <= start:
            raise ValueError("end harus lebih besar daripada start")
        if end - start > pd.Timedelta(hours=MAX_REPLAY_HOURS):
            raise ValueError(f"Periode replay maksimum {MAX_REPLAY_HOURS} jam")
        return self

