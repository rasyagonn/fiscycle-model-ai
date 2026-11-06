"""Reproducible complete optional test-image bundle and gallery release assets."""
from pathlib import Path
import hashlib
import json
import os
import tempfile
import zipfile

from app.core.config import REPOSITORY_ROOT, BSF_GALLERY_ROOT
from app.services.bsf_gallery import GalleryRegistry,encoded
from app.services.bsf_models import sha256

BUNDLE=REPOSITORY_ROOT/"FISCYCLE_GALLERY_DATA.zip"


def build_bundle():
    registry=GalleryRegistry()
    if not registry.release(): raise RuntimeError("Do not redistribute still-sealed test images")
    receipt_path=BSF_GALLERY_ROOT/"bundle_receipt.json"
    if BUNDLE.is_file() and receipt_path.is_file():
        receipt=json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("registry_digest")==registry.digest and sha256(BUNDLE)==receipt["sha256"]: return receipt
    tests=[r for r in registry.records.values() if r["split"]=="TEST"]
    if len(tests)!=224: raise RuntimeError("Incomplete frozen test inventory")
    manifest={"version":"bsf_gallery_data_v1","license":"CC BY 4.0","attribution":registry.manifest["source"],
        "registry_digest":registry.digest,"images":[{"id":r["id"],"sample_id":r["sample_id"],"dataset_id":r["dataset_id"],"sha256":r["sha256"],"member":f"images/{r['id']}.jpg"} for r in sorted(tests,key=lambda r:r["id"])],
        "status":"POST_FINAL_EVALUATION_NOT_BLIND","annotation_limit":"Original A1 class IDs 0/1 and incomplete labels preserved; no accuracy guarantee"}
    descriptor,temp=tempfile.mkstemp(prefix=".gallery_bundle_",suffix=".zip",dir=REPOSITORY_ROOT)
    os.close(descriptor);temporary=Path(temp)
    def add(z,name,raw):
        info=zipfile.ZipInfo(name,date_time=(2026,11,6,0,0,0));info.compress_type=zipfile.ZIP_STORED
        z.writestr(info,raw)
    try:
        with zipfile.ZipFile(temporary,"w",allowZip64=True) as z:
            add(z,"MANIFEST.json",(json.dumps(manifest,indent=2)+"\n").encode())
            add(z,"ATTRIBUTION.txt",(registry.manifest["source"]+"\nLicense: CC BY 4.0; https://creativecommons.org/licenses/by/4.0/\nOriginal test files, no image or annotation repair.\n").encode())
            for r in sorted(tests,key=lambda r:r["id"]):
                if r["access_status"]!="AVAILABLE": raise RuntimeError("Unavailable source requires explicit bundle omission report, not silent exclusion")
                add(z,f"images/{r['id']}.jpg",registry.raw(r["id"]))
                if r.get("annotation_available"):
                    from app.services.bsf_gallery import contained
                    path=contained(registry.source_root,r["label_locator"])
                    if sha256(path)!=r["label_sha256"]: raise RuntimeError("Annotation checksum mismatch")
                    add(z,f"annotations/{r['id']}.txt",path.read_bytes())
        os.replace(temporary,BUNDLE)
    finally:
        if temporary.exists(): temporary.unlink()
    receipt={"version":"bsf_gallery_data_v1","filename":BUNDLE.name,"sha256":sha256(BUNDLE),"bytes":BUNDLE.stat().st_size,
        "registry_digest":registry.digest,"image_count":len(tests),"a1_images":46,"a2_images":178,
        "annotation_files":sum(bool(r.get("annotation_available")) for r in tests),"excluded_images":0,
        "main_zip_contains_full_test_images":False,"main_zip_contains_all_test_thumbnails":True,"license":"CC BY 4.0"}
    receipt_path.write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    return receipt


def export_gallery(service,copy,write):
    registry=GalleryRegistry()
    receipt=build_bundle()
    if not registry.release(): raise RuntimeError("Final evaluation release receipt missing")
    target=service/"bsf_assets/gallery"
    for name in ("manifest.json","evaluation_protocol.json","inventory.json","final_evaluation.json","baseline_results.jsonl","bundle_receipt.json"):
        copy(registry.root/name,target/name)
    if sha256(registry.root/"baseline_results.jsonl")!=registry.release()["baseline_sha256"]: raise RuntimeError("Final results checksum mismatch")
    for r in registry.records.values():
        copy(registry.root/f"thumbnails/{r['id']}.jpg",target/f"thumbnails/{r['id']}.jpg")
    write(target/"deployment.json",json.dumps({"storage_mode":"bundle","bundle_sha256":receipt["sha256"],"filename":receipt["filename"],
        "full_test_images":224,"mount_instruction":"Place FISCYCLE_GALLERY_DATA.zip inside service/ or set FISCYCLE_BSF_GALLERY_DATA to the approved bundle path"},indent=2)+"\n")
    write(service/"migrations/003_gallery.sql","-- GalleryService initializes these separate tables automatically in bsf_gallery.sqlite3.\n-- gallery_results: tenant+cache_key, image_id, status, payload JSON, elapsed, created.\n-- gallery_jobs: opaque id, tenant, dataset_id, state, timestamps, config fingerprint, worker pid/birth/owner.\n-- gallery_items: job_id+image_id, status, cache_key, error, elapsed, cache_hit, attempts.\n-- No raw images or client filesystem paths in this database.\n")
    return receipt


if __name__=="__main__": print(json.dumps(build_bundle(),indent=2))
