"""One-source-photo A1 -> native-pixel A2 v3 research pipeline. No B1 conversion."""
import io
import math
import statistics
from threading import BoundedSemaphore

from fastapi import HTTPException
from PIL import Image
from app.services.bsf_intelligence import decode_image

VERSION = "bsf_photo_geometry_v1"
CAPACITY = BoundedSemaphore(1)
MAX_ANALYZED = 64
PHOTO_RULES = [
    {"id": "PHOTO-001", "condition": "no detected instances", "action": "Ambil ulang foto yang jelas; tidak ada bobot yang dapat dianalisis."},
    {"id": "PHOTO-002", "condition": "rejected ROI count > 0", "action": "Periksa larva di tepi, tertumpuk, dan area yang ditolak; massa hanya mencakup larva yang dianalisis."},
    {"id": "PHOTO-003", "condition": "camera scale unverified", "action": "Verifikasi protokol foto dan timbang sampel sebelum menggunakan estimasi dalam keputusan budidaya."},
    {"id": "PHOTO-004", "condition": "estimated instances > 0", "action": "Tinjau sebaran estimasi per larva; jumlah massa bukan biomassa seluruh wadah dan tidak menjadi input B1."},
]


def raw_point(x, y, orientation, width, height):
    # Inverse EXIF mapping in continuous pixel-edge coordinates.
    return {1: (x,y), 2: (width-x,y), 3: (width-x,height-y), 4: (x,height-y),
            5: (y,x), 6: (y,height-x), 7: (width-y,height-x), 8: (width-y,x)}[orientation]


def box_overlap(a, b):
    intersection = max(0, min(a[2],b[2])-max(a[0],b[0])) * max(0,min(a[3],b[3])-max(a[1],b[1]))
    aa, bb = (a[2]-a[0])*(a[3]-a[1]), (b[2]-b[0])*(b[3]-b[1])
    return intersection / min(aa,bb) if min(aa,bb)>0 else 0


def roi_check(polygon, width, height, canvas_size):
    if len(polygon)<3 or any(len(p)!=2 or not all(math.isfinite(v) for v in p) for p in polygon):
        return None, "INVALID_POLYGON"
    xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
    if min(xs)<0 or min(ys)<0 or max(xs)>width or max(ys)>height:
        return None, "OUT_OF_BOUNDS"
    area = abs(sum(polygon[i][0]*polygon[(i+1)%len(polygon)][1]-polygon[(i+1)%len(polygon)][0]*polygon[i][1] for i in range(len(polygon))))/2
    box = [math.floor(min(xs)),math.floor(min(ys)),math.ceil(max(xs)),math.ceil(max(ys))]
    if area<=0 or box[0]>=box[2] or box[1]>=box[3]:
        return box, "ZERO_AREA"
    if box[0]<=0 or box[1]<=0 or box[2]>=width or box[3]>=height:
        return box, "SOURCE_BORDER_TRUNCATION_REVIEW"
    if max(box[2]-box[0],box[3]-box[1])>canvas_size:
        return box, "FULL_ROI_EXCEEDS_TRAIN_SELECTED_CANVAS"
    return box, None


def analyze_photo(runtime, data, content_type):
    if not CAPACITY.acquire(blocking=False):
        raise HTTPException(429, "Analisis foto sedang berjalan; coba kembali setelah selesai.")
    try:
        return _analyze(runtime, data, content_type)
    finally:
        CAPACITY.release()


def _analyze(runtime, data, content_type):
    image = decode_image(data, content_type)
    with Image.open(io.BytesIO(data)) as source:
        raw_width, raw_height = source.size
        orientation = source.getexif().get(274,1)
    if orientation not in range(1,9):
        raise ValueError("Orientasi EXIF tidak didukung")
    result = runtime.segment(image)
    boxes = []
    for i, item in enumerate(result["instances"]):
        box, reason = roi_check(item["polygon_xy"], image.width, image.height, runtime.preprocessing["canvas_size"])
        item.update(instance_id=f"larva-{i+1:03d}", bbox_xyxy=box, rejection_reason=reason,
                    predicted_weight_mg=None, geometry=None, warnings=["SKALA_KAMERA_BELUM_TERVERIFIKASI", "ROI_OTOMATIS_PERLU_TINJAUAN_MANUSIA"],
                    source_polygon_xy=[raw_point(x,y,orientation,raw_width,raw_height) for x,y in item["polygon_xy"]])
        boxes.append(box)
    analyzed = 0
    for i, item in enumerate(result["instances"]):
        if not item["rejection_reason"]:
            overlaps = [j for j,b in enumerate(boxes) if j!=i and b and box_overlap(boxes[i],b)>.5]
            if overlaps:
                item["rejection_reason"] = "OVERLAP_HEURISTIC_REVIEW"
            elif analyzed>=MAX_ANALYZED:
                item["rejection_reason"] = "REQUEST_RESOURCE_LIMIT"
            else:
                output = runtime.estimate_roi(image, boxes[i])
                value = output["predicted_measured_weight_mg"]
                if value<0 or not math.isfinite(value):
                    item["rejection_reason"] = "INVALID_MODEL_WEIGHT"
                else:
                    item.update(predicted_weight_mg=value, geometry=output["geometry"])
                    analyzed += 1
        item["eligibility"] = "EXPERIMENTAL_ESTIMATE" if item["predicted_weight_mg"] is not None else "REJECTED"
    weights = [x["predicted_weight_mg"] for x in result["instances"] if x["predicted_weight_mg"] is not None]
    count = len(result["instances"])
    histogram = []
    if weights:
        low, high = min(weights), max(weights)
        step = (high-low)/5 if high>low else 1
        histogram = [{"lower_mg":low+i*step,"upper_mg":low+(i+1)*step,"count":0} for i in range(5)]
        for value in weights:
            histogram[min(4,int((value-low)/step))]["count"] += 1
    result.update(pipeline_version=VERSION, a2_model_version="model_a2_training_v3/best.pt",
        preprocessing_version=runtime.preprocessing["method"],
        source_geometry={"raw_width":raw_width,"raw_height":raw_height,"exif_orientation":orientation,
            "a1_coordinates":"EXIF_ORIENTED_ORIGINAL_PIXELS", "a2_crop_source":"SAME_ORIENTED_ORIGINAL_PIXELS_NO_UPSCALE",
            "source_polygon_coordinates":"RAW_SOURCE_PIXEL_EDGES", "physical_calibration":None},
        technical_screening={"border_policy":"reject boundary-touching boxes", "overlap_policy":"reject both boxes when intersection/minimum_area > 0.5",
            "validation":"PROVISIONAL_GEOMETRIC_HEURISTIC_NOT_CALIBRATED", "max_analyzed":MAX_ANALYZED,
            "unresolved":"Occlusion, written markings, and biological identity cannot be certified automatically"},
        summary={"detected":count,"analyzed":analyzed,"rejected":count-analyzed,"coverage":analyzed/count if count else None,
            "mean_estimated_weight_mg":statistics.mean(weights) if weights else None,
            "median_estimated_weight_mg":statistics.median(weights) if weights else None,
            "analyzed_visible_mass_mg":sum(weights) if weights else None,
            "analyzed_visible_mass_g":sum(weights)/1000 if weights else None,"histogram":histogram,
            "meaning":"Estimasi massa larva terlihat yang dianalisis; bukan biomassa populasi"},
        domain_status="EXPERIMENTAL_UNVERIFIED_IMAGING_SCALE", weight_protocol="MEASURED_WEIGHT_WET_DRY_UNCONFIRMED",
        provenance="AI_PREDICTED_A1_A2_FROM_ONE_PHOTO", b1_link="NOT_USED_NOT_SCIENTIFICALLY_VALIDATED")
    active = {"PHOTO-001": count==0, "PHOTO-002":count>analyzed, "PHOTO-003":True, "PHOTO-004":analyzed>0}
    result["decision_support"] = {"status":"ABSTAIN_OPERATIONAL", "rule_version":VERSION,
        "traces":[{**rule,"triggered":active[rule["id"]],"inputs":result["summary"],"provenance":result["provenance"],
                  "approval_status":"OBSERVATION_REQUEST_ONLY", "evidence":"A1 visible-instance contract and frozen A2 v3 preprocessing; no biological thresholds"} for rule in PHOTO_RULES],
        "recommendations":[r["action"] for r in PHOTO_RULES if active[r["id"]]]}
    return result
