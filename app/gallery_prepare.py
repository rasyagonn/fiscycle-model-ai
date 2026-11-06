"""Inventory every frozen A1/A2 test record; no inference, split edits or label repair."""
from __future__ import annotations
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pandas as pd
from PIL import Image
from app.core.config import BSF_ROOT, BSF_GALLERY_ROOT, APP_DIR

VERSION = "bsf_gallery_v1"
SOURCE = "Quentin Geissmann; Black Soldier Fly detection, phenotyping and sex prediction dataset; Zenodo v1; DOI 10.5281/zenodo.13359376"


def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda:stream.read(1024*1024),b""): h.update(part)
    return h.hexdigest()


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()


def write(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")


def contained(root,relative):
    p=(root/relative).resolve()
    if Path(relative).is_absolute() or ".." in Path(relative).parts or not p.is_relative_to(root.resolve()):
        raise ValueError("Path di luar dataset")
    return p


def prepare():
    root=BSF_GALLERY_ROOT
    if (root/"manifest.json").exists():
        raise FileExistsError("Inventory version already exists; verify it, do not silently replace it")
    prep=BSF_ROOT/"hasil/model_a_preparation_v1"
    freeze=json.loads((prep/"FREEZE.json").read_text(encoding="utf-8"))
    provenance=json.loads((BSF_ROOT/"hasil/model_a_audit/provenance.json").read_text(encoding="utf-8"))
    if provenance["license_id_from_api"]!="cc-by-4.0": raise ValueError("Dataset redistribution requires review")
    frames={}
    for track in ("a1","a2"):
        file=prep/f"{track}_manifest.csv"
        if sha(file)!=freeze["outputs"][file.name]: raise ValueError("Frozen split checksum mismatch")
        frames[track]=pd.read_csv(file,keep_default_na=False)
    geometry=json.loads((BSF_ROOT/"hasil/model_a2_training_v3/geometry.json").read_text())
    dev_a1=sorted((BSF_ROOT/"hasil/model_a_training_v1/a1_dataset/images/train").glob("*.jpg"))[0]
    dev_a1_sha=sha(dev_a1)
    dev_a2=next(x for x in geometry if x["id"]=="A2_0001")
    rows=[]
    with zipfile.ZipFile(BSF_ROOT/"data/Single Larvae data.zip") as archive:
        for track,frame in frames.items():
            tests=frame[frame.split.eq("test")]
            if len(tests)!=freeze["split_counts"][track]["test"]: raise ValueError("Test count mismatch")
            development=frame[frame.image_sha256.eq(dev_a1_sha)] if track=="a1" else frame[frame.L_ID.eq(1)]
            if len(development)!=1 or development.iloc[0].split!="train": raise ValueError("Development fixture split mismatch")
            for collection,subset in ((f"{track}-test",tests),(f"{track}-development",development)):
                for _,r in subset.iterrows():
                    is_a1=track=="a1"
                    filename=Path(r.image_path if is_a1 else r.archive_member).name
                    sample=(f"A1_{r.image_sha256[:16]}" if is_a1 else f"A2_{int(r.L_ID):04d}")
                    image_id=hashlib.sha256((collection+":"+sample+":"+r.image_sha256).encode()).hexdigest()[:24]
                    locator={"file":r.image_path} if is_a1 else {"archive":r.archive_path,"member":r.archive_member}
                    record={"id":image_id,"dataset_id":collection,"track":track.upper(),"sample_id":sample,"filename":filename,
                        "split":str(r.split).upper(),"split_group_id":r.split_group_id,"sha256":r.image_sha256,
                        "width":int(r.width),"height":int(r.height),"source":SOURCE,"license":"CC BY 4.0",
                        "locator":locator,"annotation_available":False,"annotation_completeness":"NOT_CERTIFIED",
                        "reference_measured_weight_mg":None,"weight_protocol":"WET_DRY_UNCONFIRMED",
                        "camera":None,"roi_bbox":None,"roi_source":None,"access_status":"AVAILABLE","error":None}
                    if is_a1:
                        label=contained(BSF_ROOT,r.label_path)
                        record.update(label_locator=r.label_path,label_sha256=r.label_sha256,
                            annotation_available=label.is_file(),source_annotation_count=int(r.total_instances),
                            source_group_id=r.source_group_id,source_class_meaning="UNRESOLVED_IDS_0_1")
                        if label.is_file() and sha(label)!=r.label_sha256:
                            record["annotation_completeness"]="SOURCE_ANNOTATION_HASH_MISMATCH"
                    else:
                        record.update(reference_measured_weight_mg=float(r.Weight_mg),batch_id=r.Batch_ID,
                            camera={"make":r.camera_make or None,"model":r.camera_model or None,"exif_datetime":r.exif_datetime or None,"timezone":r.camera_timezone},
                            reference_unit_source=r.weight_unit,reference_conversion="g * 1000 = mg")
                        if collection.endswith("development"):
                            record.update(roi_bbox=dev_a2["roi_bbox"],roi_source="FROZEN_DEVELOPMENT_GEOMETRY")
                    try:
                        raw=contained(BSF_ROOT,r.image_path).read_bytes() if is_a1 else archive.read(r.archive_member)
                        record["bytes"]=len(raw)
                        if hashlib.sha256(raw).hexdigest()!=r.image_sha256: raise ValueError("IMAGE_CHECKSUM_MISMATCH")
                        with Image.open(io.BytesIO(raw)) as im:
                            im.load()
                            if im.size!=(int(r.width),int(r.height)) or im.format not in ("JPEG","PNG","WEBP"): raise ValueError("IMAGE_METADATA_MISMATCH")
                    except (FileNotFoundError,KeyError):
                        record.update(access_status="MISSING",error="Berkas sumber tidak ditemukan")
                    except Exception as exc:
                        record.update(access_status="CORRUPT",error=type(exc).__name__+": "+str(exc))
                    rows.append(record)
    collections=[]
    for name in ("a1-test","a2-test","a1-development","a2-development"):
        items=[r for r in rows if r["dataset_id"]==name]
        collections.append({"id":name,"name":{"a1-test":"Dataset Pengujian A1","a2-test":"Dataset Pengujian A2","a1-development":"Contoh Development A1 — Bukan Test","a2-development":"Contoh Development A2 — Bukan Test"}[name],
            "track":items[0]["track"],"split":items[0]["split"],"declared":len(items),"accessible":sum(r["access_status"]=="AVAILABLE" for r in items),
            "missing":sum(r["access_status"]=="MISSING" for r in items),"corrupt":sum(r["access_status"]=="CORRUPT" for r in items),
            "restricted":0,"eligible_after_release":sum(r["access_status"]=="AVAILABLE" for r in items),
            "primary_split_groups":len({r["split_group_id"] for r in items}),"permission":"CC BY 4.0, attribution required",
            "release_requires":"COMPLETED_FINAL_EVALUATION" if name.endswith("test") else None})
    manifest={"version":VERSION,"source":SOURCE,"license_evidence":provenance,"collections":collections,"images":rows,
              "freeze_sha256":sha(prep/"FREEZE.json"),"split_manifest_sha256":{t:sha(prep/f"{t}_manifest.csv") for t in frames},
              "sampling_policy":"ALL_FROZEN_TEST_ROWS; no prediction-based exclusions; two prior development fixtures explicitly separate"}
    from app.services.bsf_gallery_roi import CONFIG
    protocol={"version":VERSION,"authorization":"User: lakukan evaluasi final, lalu lepaskan (current session)",
        "model_hashes":json.loads((APP_DIR/"runtime_artifacts.json").read_text())["bsf"],
        "source_manifest_sha256":hashlib.sha256(canonical(manifest)).hexdigest(),"a1":{"imgsz":320,"confidence":.25,"max_det":300},
        "batch_pipeline":{"version":"bsf_photo_geometry_v1","max_analyzed":64,"overlap_min_area_threshold":.5,"border_touch":"REJECT"},
        "a2":{"native_canvas":2048,"network_input":224,"normalization":"ImageNet RGB; frozen target inverse",
              "roi_adapter":"UNCHANGED a2_roi_v2_ranked; pixels only; no target/ID input","roi_config":CONFIG,
              "roi_review":"Existing exact development geometry when present; test has no frozen reviewed ROI. Automatic test proposal is exploratory, not a certified reviewed-ROI benchmark.",
              "reject_conditions":["NO_CANDIDATE","SOURCE_EDGE_CONTACT","SHORTCUT_SCREEN","OUT_OF_BOUNDS","EXCEEDS_2048_CANVAS"],
              "metrics":"Report attempted/rejected/failed denominator; descriptive automatic-ROI errors separately from strict reviewed-ROI metrics"},
        "protected_inputs":{str(p.relative_to(BSF_ROOT)):sha(p) for p in [prep/"FREEZE.json",prep/"a1_manifest.csv",prep/"a2_manifest.csv",BSF_ROOT/"a2_preprocessing_v2.py",BSF_ROOT/"hasil/model_a2_training_v3/preprocessing_config.json"]},
        "runtime_code_sha256":{name:sha(APP_DIR/name) for name in ("services/bsf_models.py","services/bsf_photo.py","services/bsf_gallery_roi.py")},
        "rules":"No tuning, checkpoint selection or retraining after test inspection; do not claim future blind status"}
    root.mkdir(parents=True,exist_ok=True)
    write(root/"manifest.json",manifest);write(root/"evaluation_protocol.json",protocol)
    write(root/"inventory.json",{"version":VERSION,"collections":collections,"total":len(rows),"evaluation_status":"AUTHORIZED_NOT_STARTED","final_test_blind_status":"PENDING_AUTHORIZED_FINAL_EVALUATION"})
    print(json.dumps({"root":str(root),"collections":collections},indent=2))


if __name__=="__main__": prepare()
