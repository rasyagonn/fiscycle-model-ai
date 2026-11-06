"""Untrained A2 ROI proposal and aspect-preserving preview; no biological labels.

Input to proposal is pixels only. All outputs are candidates, not certified crops.
Only train/validation rows may be processed during this QA phase.
"""
from __future__ import annotations

import hashlib
import cv2
import numpy as np
from PIL import Image

VERSION = "a2_roi_v1"
CONFIG = {"detection_max_side": 1014, "red_minus_blue": 15, "red_minus_green": 2,
          "minimum_value": 35, "maximum_value": 245, "minimum_saturation": 25,
          "minimum_component_fraction": .0006, "maximum_component_fraction": .15,
          "context_fraction_of_long_side": .08, "minimum_context_native_px": 24,
          "output_size": 512, "padding_rgb": [127, 127, 127]}


def require_development_split(split):
    if split not in ("train", "validation"):
        raise ValueError("QA preprocessing is restricted to frozen train/validation; test/quarantine refused")


def propose_roi(image: Image.Image):
    """Warm-colour connected components, no positional central crop or learned fit.

    Largest plausible component is only a hypothesis. Text, debris, shadows, pale
    larvae and multiple components can invalidate it. Never infer mm or weight.
    """
    image = image.convert("RGB")
    width, height = image.size
    ratio = min(1., CONFIG["detection_max_side"] / max(width, height))
    small = image.resize((round(width * ratio), round(height * ratio)), Image.Resampling.BILINEAR)
    rgb = np.asarray(small)
    rgb16 = rgb.astype(np.int16)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    mask = ((rgb16[:, :, 0] - rgb16[:, :, 2] > CONFIG["red_minus_blue"]) &
            (rgb16[:, :, 0] - rgb16[:, :, 1] > CONFIG["red_minus_green"]) &
            (hsv[:, :, 1] > CONFIG["minimum_saturation"]) &
            (hsv[:, :, 2] > CONFIG["minimum_value"]) &
            (hsv[:, :, 2] < CONFIG["maximum_value"])).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    area = rgb.shape[0] * rgb.shape[1]
    candidates = [i for i in range(1, n) if CONFIG["minimum_component_fraction"] <=
                  stats[i, cv2.CC_STAT_AREA] / area <= CONFIG["maximum_component_fraction"]]
    candidates.sort(key=lambda i: (-stats[i, cv2.CC_STAT_AREA], i))
    result = {"method": VERSION, "candidate_count": len(candidates), "roi_found": bool(candidates),
              "automatic_status": "REVIEW_REQUIRED", "calibration": "UNVERIFIED", "body_bbox": None,
              "crop_bbox": None, "component_area_fraction": None, "component_fill": None,
              "competing_component_ratio": None, "source_edge_contact": None,
              "training_approved": False}
    if not candidates:
        result["automatic_status"] = "NO_CANDIDATE_NO_FALLBACK"
        return result
    best = candidates[0]
    x, y, w, h, count = (int(v) for v in stats[best])
    x0, y0 = int(np.floor(x / ratio)), int(np.floor(y / ratio))
    x1, y1 = min(width, int(np.ceil((x + w) / ratio))), min(height, int(np.ceil((y + h) / ratio)))
    margin = max(CONFIG["minimum_context_native_px"], round(max(x1 - x0, y1 - y0) * CONFIG["context_fraction_of_long_side"]))
    result.update(body_bbox=[x0, y0, x1, y1],
                  crop_bbox=[max(0, x0-margin), max(0, y0-margin), min(width, x1+margin), min(height, y1+margin)],
                  component_area_fraction=float(count / area), component_fill=float(count / (w * h)),
                  competing_component_ratio=float(stats[candidates[1], cv2.CC_STAT_AREA] / count) if len(candidates) > 1 else 0.,
                  source_edge_contact=bool(x <= 1 or y <= 1 or x+w >= rgb.shape[1]-1 or y+h >= rgb.shape[0]-1))
    if result["source_edge_contact"]:
        result["automatic_status"] = "POSSIBLE_SOURCE_TRUNCATION"
    elif result["competing_component_ratio"] > .25:
        result["automatic_status"] = "MULTIPLE_COMPONENTS_REVIEW"
    return result


def letterbox_crop(image, box, size=512):
    """No stretch, rotation, morphing, foreground masking, or physical calibration."""
    width, height = image.size
    x0, y0, x1, y1 = map(int, box)
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ValueError("Invalid or out-of-bounds working ROI")
    crop = image.convert("RGB").crop((x0, y0, x1, y1))
    scale = min(size / crop.width, size / crop.height)
    new_size = (max(1, round(crop.width * scale)), max(1, round(crop.height * scale)))
    resized = crop.resize(new_size, Image.Resampling.LANCZOS)
    left, top = (size-new_size[0]) // 2, (size-new_size[1]) // 2
    canvas = Image.new("RGB", (size, size), tuple(CONFIG["padding_rgb"]))
    canvas.paste(resized, (left, top))
    return canvas, {"native_crop_width": crop.width, "native_crop_height": crop.height,
                    "resize_scale": scale, "resized_width": new_size[0], "resized_height": new_size[1],
                    "pad_left": left, "pad_top": top,
                    "pixel_to_mm": None, "absolute_pixel_scale_retained": False}


def approved_crop(image, *, split, image_sha256, approval):
    """Fail closed: explicit human review bound to source hash AND exact ROI required.

    This phase emits no approved training crops. A caller must supply a separate,
    versioned working review, not edit frozen manifests. Trust the reviewer record,
    not a heuristic threshold; this function cannot prove a human's assertion.
    """
    require_development_split(split)
    required = (approval.get("reviewer_kind") == "human" and approval.get("reviewer_name") and
                approval.get("reviewed_at") and approval.get("source_sha256") == image_sha256 and
                approval.get("whole_larva_visible") is True and approval.get("no_written_markings") is True and
                approval.get("background_acceptable") is True and approval.get("crop_bbox"))
    if not required:
        raise ValueError("Explicit human whole-body/shortcut/ROI/source review required")
    pixel_hash = hashlib.sha256(image.convert("RGB").tobytes()).hexdigest()
    if approval.get("decoded_pixel_sha256") != pixel_hash:
        raise ValueError("Review does not match these decoded pixels")
    return letterbox_crop(image, approval["crop_bbox"], CONFIG["output_size"])
