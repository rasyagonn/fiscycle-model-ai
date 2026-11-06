"""BSF research MVP: trusted local models, development replay, and durable result history."""
from __future__ import annotations

import io
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

import pandas as pd
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import BSF_HISTORY_DB, BSF_REPLAY_CSV, BSF_ROOT
from app.services.bsf_models import BsfModelRuntime, STATUS, V3
from app.services.bsf import BsfService
from app.core.security import tenant_context

WIB = timezone(timedelta(hours=7))
DEV = BSF_ROOT / "hasil" / "v2" / "internal" / "bsf_model_b1_development_oof_residuals.csv"
HISTORY_DB = BSF_HISTORY_DB


def timestamp() -> str:
    return datetime.now(WIB).isoformat()


def decode_image(data: bytes, content_type: str, *, require_unrotated: bool = False) -> Image.Image:
    if content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise ValueError("Gunakan gambar JPEG, PNG, atau WebP.")
    if not data or len(data) > 8 * 1024 * 1024:
        raise ValueError("Ukuran gambar harus antara 1 byte dan 8 MiB.")
    try:
        with Image.open(io.BytesIO(data)) as source:
            if not (128 <= source.width <= 6000 and 128 <= source.height <= 6000):
                raise ValueError("Dimensi gambar tidak didukung")
            if require_unrotated and source.getexif().get(274, 1) != 1:
                raise ValueError("Orientasi EXIF foto A2 harus normal; pilih foto sumber tanpa rotasi otomatis.")
            source.load()
            image = source.convert("RGB") if require_unrotated else ImageOps.exif_transpose(source).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ValueError("Gambar tidak dapat dibaca.") from exc
    if not (128 <= image.width <= 6000 and 128 <= image.height <= 6000):
        raise ValueError("Dimensi gambar di luar batas 128–6000 piksel.")
    return image


class BsfHistory:
    def __init__(self, path: Path = HISTORY_DB):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = Lock()
        with self.connect() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at_wib TEXT NOT NULL,
                kind TEXT NOT NULL,
                provenance TEXT NOT NULL,
                model_version TEXT,
                preprocessing_version TEXT,
                rule_version TEXT,
                image_sha256 TEXT,
                payload_json TEXT NOT NULL
            )""")
            version = con.execute("PRAGMA user_version").fetchone()[0]
            if version in (0, 1):
                con.execute("ALTER TABLE records ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'local_demo'")
                con.execute("CREATE INDEX records_tenant ON records(tenant_id,id)")
                con.execute("PRAGMA user_version=2")
            elif version != 2:
                raise RuntimeError(f"Unsupported BSF history schema version: {version}")

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def add(self, kind: str, provenance: str, payload: dict, *, model_version: str | None = None,
            preprocessing_version: str | None = None, rule_version: str | None = None,
            image_sha256: str | None = None) -> int:
        # Images and large base64 previews are not stored in history.
        stored = {key: value for key, value in payload.items() if not key.endswith("_png_base64")}
        with self.lock, self.connect() as con:
            cursor = con.execute("""INSERT INTO records
                (created_at_wib,kind,provenance,model_version,preprocessing_version,rule_version,image_sha256,payload_json,tenant_id)
                VALUES (?,?,?,?,?,?,?,?,?)""", (timestamp(), kind, provenance, model_version,
                preprocessing_version, rule_version, image_sha256, json.dumps(stored, allow_nan=False), tenant_context.get()))
            return int(cursor.lastrowid)

    def list(self, limit: int = 50, kind: str | None = None) -> list[dict]:
        query = "SELECT id,created_at_wib,kind,provenance,model_version,preprocessing_version,rule_version,image_sha256,payload_json FROM records"
        query += " WHERE tenant_id=?"
        args: list = [tenant_context.get()]
        if kind:
            query += " AND kind=?"
            args.append(kind)
        query += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self.connect() as con:
            rows = con.execute(query, args).fetchall()
        keys = ["id", "created_at_wib", "kind", "provenance", "model_version", "preprocessing_version", "rule_version", "image_sha256", "result"]
        return [dict(zip(keys, [*row[:-1], json.loads(row[-1])])) for row in rows]

    def get(self, record_id: int) -> dict | None:
        with self.connect() as con:
            row = con.execute("SELECT id,created_at_wib,kind,provenance,model_version,preprocessing_version,rule_version,image_sha256,payload_json FROM records WHERE id=? AND tenant_id=?", (record_id, tenant_context.get())).fetchone()
        if row is None:
            return None
        keys = ["id", "created_at_wib", "kind", "provenance", "model_version", "preprocessing_version", "rule_version", "image_sha256", "result"]
        return dict(zip(keys, [*row[:-1], json.loads(row[-1])]))

    def observations(self, batch_id: str) -> list[dict]:
        with self.connect() as con:
            rows = con.execute("""SELECT id,created_at_wib,payload_json FROM records
                WHERE kind='USER_OBSERVATION' AND json_extract(payload_json,'$.batch_id')=? AND tenant_id=?
                ORDER BY id DESC LIMIT 1000""", (batch_id, tenant_context.get())).fetchall()
        values = [{**json.loads(payload), "history_id": record_id, "recorded_at_wib": created}
                  for record_id, created, payload in rows]
        return sorted(values, key=lambda row: (row["day"], row["history_id"]))


class BsfIntelligence:
    def __init__(self, b1: BsfService | None = None):
        self.b1 = b1 or BsfService()
        self.history = BsfHistory()
        self.models_runtime = BsfModelRuntime()
        self.a2_preprocessing = self.models_runtime.preprocessing
        self.v3_receipt = self.models_runtime.receipt
        self.trajectories = self._load_development_trajectories()

    def _load_development_trajectories(self) -> dict[str, dict]:
        # Both sources contain development folds only; final-test replicates are absent.
        columns = ["replicate_id", "moisture_percent", "measurement_index_1based", "elapsed_days",
                   "current_weight_mg", "previous_weight_mg", "previous_elapsed_days"]
        source = BSF_REPLAY_CSV if BSF_REPLAY_CSV.is_file() else DEV
        if source == BSF_REPLAY_CSV:
            metadata_path = source.with_suffix(".metadata.json")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            from app.services.bsf_models import sha256
            if sha256(source) != metadata["sha256"] or metadata["version"] != "bsf_replay_development_v1":
                raise ValueError("Replay seed checksum/version mismatch")
        frame = pd.read_csv(source, usecols=columns)
        allowed = set(self.b1.metadata["development_replicates"])
        if set(frame.replicate_id) != allowed:
            raise ValueError("Replay development groups do not match frozen B1 metadata")
        result = {}
        for replicate, group in frame.groupby("replicate_id", sort=True):
            group = group.sort_values("elapsed_days")
            first = group.iloc[0]
            observations = [{"day": float(first.previous_elapsed_days), "measured_weight_mg": float(first.previous_weight_mg), "provenance": "HISTORICAL_RESEARCH"}]
            observations += [{"day": float(row.elapsed_days), "measured_weight_mg": float(row.current_weight_mg), "provenance": "HISTORICAL_RESEARCH"} for row in group.itertuples()]
            if any(b["day"] <= a["day"] for a, b in zip(observations, observations[1:])):
                raise ValueError("Replay observations must be strictly chronological")
            result[replicate] = {"trajectory_id": replicate, "moisture_percent": float(first.moisture_percent),
                                 "curation_experiment_id": "mendeley_k435zc736t_v1",
                                 "treatment_id": "moisture_" + replicate.split("-")[0],
                                 "replicate_number": int(replicate.split("-")[1]),
                                 "observations": observations}
        return result

    def models(self) -> dict:
        return {"status": STATUS, "a1": {"checkpoint": "a1_initial/weights/best.pt", "task": "visible instance segmentation", "loaded": self.models_runtime.a1_model is not None},
                "a2": {"checkpoint": "model_a2_training_v3/best.pt", "input": "single-ROI endpoint: original 4056×3040 reviewed image; one-photo endpoint: technically valid native-pixel ROI in explicitly experimental unverified imaging domain", "preprocessing": self.a2_preprocessing["method"],
                       "development_validation_mae_mg": self.v3_receipt["metrics"]["v3"]["MAE_mg"], "loaded": self.models_runtime.a2_model is not None},
                "b1": {"method": self.b1.metadata["method"], "features": self.b1.metadata["features"],
                       "horizon": "one next recorded observation; replay uses a predeclared one-day horizon"}}

    def segment(self, image: Image.Image, *, confidence: float = 0.25) -> dict:
        return self.models_runtime.segment(image, confidence)

    def estimate_weight(self, image: Image.Image, roi: tuple[int, int, int, int], *, reviewed_roi: bool) -> dict:
        return self.models_runtime.estimate_weight(image, roi, reviewed_roi)

    def trajectory_list(self) -> list[dict]:
        return [{"trajectory_id": value["trajectory_id"], "moisture_percent": value["moisture_percent"],
                 "curation_experiment_id": value["curation_experiment_id"],
                 "treatment_id": value["treatment_id"], "replicate_number": value["replicate_number"],
                 "observation_count": len(value["observations"]), "data_mode": "HISTORICAL_RESEARCH"}
                for value in self.trajectories.values()]

    def replay(self, trajectory_id: str, revealed: int) -> dict:
        record = self.trajectories.get(trajectory_id)
        if record is None:
            raise KeyError(trajectory_id)
        observations = record["observations"]
        if revealed < 0 or revealed > len(observations):
            raise ValueError("Posisi replay tidak valid")
        visible = observations[:revealed]
        forecast = None
        if len(visible) >= 2:
            prev, current = visible[-2:]
            elapsed = current["day"] - prev["day"]
            features = {"moisture_percent": record["moisture_percent"], "elapsed_days": current["day"],
                        "current_weight_mg": current["measured_weight_mg"], "previous_weight_mg": prev["measured_weight_mg"],
                        "recent_growth_mg_per_day": (current["measured_weight_mg"] - prev["measured_weight_mg"]) / elapsed,
                        "forecast_horizon_days": 1.0}
            output = self.b1.predict(features, "PUBLIC_RESEARCH_DEVELOPMENT")
            forecast = {"forecast_at_day": current["day"], "target_day": current["day"] + 1,
                        "input_features": features, "result": output, "provenance": "AI_PREDICTED_B1",
                        "explanation": "B1 memakai dua berat terukur terakhir, selang hari yang sudah lewat, dan perlakuan kelembapan penelitian. Horizon satu hari ditetapkan sebelum melihat pengamatan berikutnya."}
        comparisons = []
        for index in range(2, len(visible)):
            previous, current, actual = visible[index-2:index+1]
            features = {"moisture_percent": record["moisture_percent"], "elapsed_days": current["day"],
                        "current_weight_mg": current["measured_weight_mg"], "previous_weight_mg": previous["measured_weight_mg"],
                        "recent_growth_mg_per_day": (current["measured_weight_mg"] - previous["measured_weight_mg"]) / (current["day"] - previous["day"]),
                        "forecast_horizon_days": 1.0}
            prediction = self.b1.predict(features, "PUBLIC_RESEARCH_DEVELOPMENT")
            aligned = abs(actual["day"] - (current["day"] + 1)) <= 1e-4
            comparisons.append({"from_day": current["day"], "forecast_target_day": current["day"] + 1,
                                "observed_day": actual["day"], "observed_measured_weight_mg": actual["measured_weight_mg"],
                                "predicted_weight_mg": prediction["predicted_next_weight_mg"],
                                "error_mg": prediction["predicted_next_weight_mg"] - actual["measured_weight_mg"] if aligned and prediction["predicted_next_weight_mg"] is not None else None,
                                "time_aligned": aligned, "note": "Waktu pengukuran tidak cocok dengan horizon 1 hari" if not aligned else None})
        return {"trajectory_id": trajectory_id, "replicate_id": trajectory_id,
                "curation_experiment_id": record["curation_experiment_id"],
                "treatment_id": record["treatment_id"], "replicate_number": record["replicate_number"],
                "moisture_percent": record["moisture_percent"],
                "data_mode": "HISTORICAL_RESEARCH", "source": "B1 development fold observations; Mendeley Data v1 DOI 10.17632/k435zc736t.1",
                "evaluation_scope": "IN_SAMPLE_DEVELOPMENT_REPLAY", "independent_validation": False,
                "revealed": revealed, "total_observations": len(observations), "observations": visible,
                "forecast": forecast, "comparisons": comparisons, "status": STATUS,
                "limitation": "Model memprediksi satu hari ke depan. Selisih hanya dihitung bila pengamatan berikutnya tepat pada hari tersebut; replay bukan data live."}
