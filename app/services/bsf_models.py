"""Portable BSF AI runtime. No HTTP, replay, storage, or training dependencies."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
import random
from pathlib import Path
from threading import Lock

import torch
from PIL import Image, ImageDraw, ImageOps
from torch import nn
from torchvision.models import mobilenet_v3_small
from torchvision.transforms import functional as TF

from app.core.config import BSF_ROOT

V3 = BSF_ROOT / "hasil" / "model_a2_training_v3"
A1 = BSF_ROOT / "hasil" / "model_a_training_v1" / "a1_initial" / "weights" / "best.pt"
STATUS = ["RESEARCH_PROTOTYPE", "NOT_FIELD_VALIDATED"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_base64(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def fixed_canvas(image: Image.Image, roi, canvas_size: int, output_size: int = 224):
    """Exact A2 v3 geometry/pixel transform from frozen a2_scale_v3.fixed_canvas."""
    im = image.convert("RGB")
    x0, y0, x1, y1 = map(int, roi)
    if not (0 <= x0 < x1 <= im.width and 0 <= y0 < y1 <= im.height):
        raise ValueError("ROI outside source")
    width, height = x1 - x0, y1 - y0
    if max(width, height) > canvas_size:
        raise ValueError("FULL_ROI_EXCEEDS_TRAIN_SELECTED_CANVAS")
    left = (x0 + x1) // 2 - canvas_size // 2
    top = (y0 + y1) // 2 - canvas_size // 2
    offset_x, offset_y = x0 - left, y0 - top
    canvas = Image.new("RGB", (canvas_size, canvas_size), (127, 127, 127))
    patch = im.crop((x0, y0, x1, y1))
    canvas.paste(patch, (offset_x, offset_y))
    assert canvas.crop((offset_x, offset_y, offset_x + width, offset_y + height)).tobytes() == patch.tobytes()
    result = canvas.resize((output_size, output_size), Image.Resampling.BILINEAR)
    return result, dict(source_width=im.width, source_height=im.height, roi_bbox=[x0, y0, x1, y1],
        source_canvas_bbox=[left, top, left + canvas_size, top + canvas_size], roi_offset=[offset_x, offset_y],
        padding_ltrb=[offset_x, offset_y, canvas_size - offset_x - width, canvas_size - offset_y - height],
        source_boundary_padding_ltrb=[max(0, -left), max(0, -top), max(0, left + canvas_size - im.width), max(0, top + canvas_size - im.height)],
        native_roi_width=width, native_roi_height=height, native_roi_long_side=max(width, height),
        scale_factor=output_size / canvas_size, retained_native_roi_pixels=width * height,
        roi_pixels_preserved_before_resize=True, outside_roi_policy="neutral127; no new source context", pixel_to_mm=None)


def a2_tensor(image: Image.Image, size: int, augment: bool = False):
    """Exact ImageNet normalization and v3 augmentation ordering; inference uses augment=False."""
    im = image.convert("RGB")
    if im.size != (size, size):
        raise ValueError("Expected v3 fixed-scale prepared224x224 image")
    if augment:
        if random.random() < .5:
            im = ImageOps.mirror(im)
        if random.random() < .5:
            im = ImageOps.flip(im)
        if random.random() < .5:
            im = im.transpose(random.choice([Image.Transpose.ROTATE_90, Image.Transpose.ROTATE_180, Image.Transpose.ROTATE_270]))
    return TF.normalize(TF.to_tensor(im), [.485, .456, .406], [.229, .224, .225])


def a2_model():
    model = mobilenet_v3_small(weights=None)
    model.classifier = nn.Sequential(nn.Linear(576, 128), nn.Hardswish(), nn.Dropout(.2), nn.Linear(128, 1))
    return model


class BsfModelRuntime:
    def __init__(self):
        from app.core.artifacts import verify_domain
        verify_domain("bsf")
        self.lock = Lock()
        self.a1_model = None
        self.a2_model = None
        self.a2_config = None
        self.preprocessing = json.loads((V3 / "preprocessing_config.json").read_text(encoding="utf-8"))
        self.receipt = json.loads((V3 / "COMPLETE.json").read_text(encoding="utf-8"))
        if not A1.is_file() or not (V3 / "best.pt").is_file():
            raise FileNotFoundError("Checkpoint A1 atau A2 v3 tidak tersedia")
        if sha256(V3 / "best.pt") != self.receipt["files"]["best.pt"]:
            raise ValueError("Hash checkpoint A2 v3 tidak sesuai receipt")
        if sha256(V3 / "preprocessing_config.json") != self.receipt["files"]["preprocessing_config.json"]:
            raise ValueError("Hash preprocessing A2 v3 tidak sesuai receipt")
        self.device = self._device()
        # Readiness reflects actual checkpoint loading, not merely file presence.
        from ultralytics import YOLO
        self.a1_model = YOLO(str(A1))
        self._load_a2()

    @staticmethod
    def _device() -> str:
        requested = os.getenv("FISCYCLE_BSF_DEVICE", "cpu").lower()
        if requested not in {"cpu", "cuda", "auto"}:
            raise ValueError("FISCYCLE_BSF_DEVICE must be cpu, cuda, or auto")
        if requested == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA requested but not available")
        return "cuda" if (requested == "cuda" or requested == "auto" and torch.cuda.is_available()) else "cpu"

    def segment(self, image: Image.Image, confidence: float = .25) -> dict:
        from ultralytics import YOLO
        with self.lock:
            if self.a1_model is None:
                self.a1_model = YOLO(str(A1))
            result = self.a1_model.predict(image, imgsz=320, conf=confidence,
                                           device=0 if self.device == "cuda" else "cpu", max_det=300, verbose=False)[0]
        polygons = result.masks.xy if result.masks is not None else []
        instances = [{"polygon_xy": polygon.tolist(), "confidence": float(score), "class_name": "visible_bsf_larva"}
                     for polygon, score in zip(polygons, result.boxes.conf.tolist())]
        overlay = image.convert("RGBA")
        layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        pen = ImageDraw.Draw(layer)
        for instance in instances:
            vertices = [tuple(point) for point in instance["polygon_xy"]]
            if len(vertices) >= 3:
                pen.polygon(vertices, fill=(8, 127, 112, 80), outline=(8, 127, 112, 255), width=2)
        overlay = Image.alpha_composite(overlay, layer).convert("RGB")
        overlay.thumbnail((1024, 1024))
        return {"visible_instance_count": len(instances), "instances": instances, "overlay_png_base64": png_base64(overlay),
                "image_width": image.width, "image_height": image.height, "coordinates": "decoded_oriented_image_pixels",
                "detection_limit_reached": len(result.boxes) >= 300, "model_version": "a1_initial/best.pt", "provenance": "AI_PREDICTED_A1",
                "status": STATUS, "warning": "Jumlah ini hanya larva yang terdeteksi dan terlihat, bukan seluruh populasi.",
                "limitations": ["Anotasi pengembangan mungkin belum lengkap, terutama pada adegan padat.",
                                "Makna biologis dua ID kelas sumber belum terkonfirmasi.",
                                "Skor detektor bukan probabilitas yang terkalibrasi."]}

    def _load_a2(self):
        if self.a2_model is not None:
            return
        obj = torch.load(V3 / "best.pt", map_location="cpu", weights_only=False)  # trusted, hashed local checkpoint
        model = a2_model()
        model.load_state_dict(obj["model"])
        model.eval()
        self.a2_model = model.to(self.device)
        self.a2_config = obj["config"]
        if self.a2_config["version"] != "model_a2_training_v3" or self.a2_config["input_size"] != 224:
            raise ValueError("A2 checkpoint contract mismatch")

    def estimate_weight(self, image: Image.Image, roi, reviewed_roi: bool) -> dict:
        if image.size != (4056, 3040):
            raise ValueError("A2 v3 memerlukan foto sumber 4056×3040 piksel dari protokol penelitian yang kompatibel.")
        if not reviewed_roi:
            raise ValueError("ROI perlu diperiksa: satu larva utuh dan tanpa penanda yang dapat dibaca.")
        return self.estimate_roi(image, roi, reviewed=True)

    def estimate_roi(self, image: Image.Image, roi, reviewed: bool = False) -> dict:
        """Exact frozen v3 preprocessing; arbitrary source domains are explicitly experimental."""
        prepared, geometry = fixed_canvas(image, roi, self.preprocessing["canvas_size"])
        with self.lock:
            self._load_a2()
            x = a2_tensor(prepared, self.a2_config["input_size"]).unsqueeze(0).to(self.device)
            with torch.inference_mode():
                value = float(self.a2_model(x).item() * self.a2_config["target_std_mg"] + self.a2_config["target_mean_mg"])
        if not math.isfinite(value):
            raise ValueError("Prediksi A2 tidak valid")
        return {"predicted_measured_weight_mg": value, "processed_png_base64": png_base64(prepared),
                "model_version": "model_a2_training_v3/best.pt", "preprocessing_version": self.preprocessing["method"],
                "input_quality": "USER_REVIEWED_ROI_UNVERIFIED_CAMERA_SCALE" if reviewed else "AUTOMATIC_ROI_EXPERIMENTAL_UNVERIFIED_DOMAIN", "geometry": geometry,
                "provenance": "AI_PREDICTED_A2", "status": STATUS,
                "limitations": ["Pemeriksaan ROI berasal dari pengguna; kamera dan skala fisik belum diverifikasi.",
                                "Berat terukur pada dataset belum dipastikan sebagai berat basah atau kering.",
                                "MAE validasi kelompok tidak menjamin error per foto."]}
