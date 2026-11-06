"""One post-freeze final inference pass, then release every eligible test record for demo.

Requires the user's recorded explicit authorization. Never edits training/frozen artifacts.
"""
import hashlib
import io
import json
import time
from pathlib import Path
from PIL import Image,ImageOps

from app.core.config import BSF_GALLERY_ROOT, BSF_ROOT, APP_DIR
from app.core.security import tenant_context
from app.services.bsf_gallery import GalleryRegistry,GalleryService,encoded
from app.services.bsf_models import BsfModelRuntime,sha256
from app.services.bsf_intelligence import BsfHistory,timestamp
from app.gallery_prepare import write


def evaluate():
    root=BSF_GALLERY_ROOT
    if (root/"final_evaluation.json").exists(): raise FileExistsError("Final pass already recorded; do not rerun or silently overwrite it")
    registry=GalleryRegistry()
    if registry.protocol["authorization"]!="User: lakukan evaluasi final, lalu lepaskan (current session)": raise ValueError("Explicit authorization required")
    from app.core.artifacts import verify_domain
    before=verify_domain("bsf")
    for name,expected in registry.protocol["protected_inputs"].items():
        if sha256(BSF_ROOT/name)!=expected: raise ValueError("Protected input changed before final evaluation")
    for name,expected in registry.protocol["runtime_code_sha256"].items():
        if sha256(APP_DIR/name)!=expected: raise ValueError("Pre-registered inference code changed")
    runtime=BsfModelRuntime()
    history=BsfHistory(root/"final_history.sqlite3")
    gallery=GalleryService(runtime,history,registry=registry,db_path=root/"final_jobs.sqlite3",evaluation=True)
    marker=tenant_context.set("__public_final_evaluation__")
    try:
        write(root/"evaluation_started.json",{"started_at_wib":timestamp(),"configuration_fingerprint":gallery.fingerprint,"configuration":gallery.configuration,
            "protocol_sha256":sha256(root/"evaluation_protocol.json"),"registry_digest":registry.digest,
            "final_test_blind_status":"AUTHORIZED_FINAL_EVALUATION_STARTED_NOT_UNTOUCHED"})
        summaries={}
        for dataset in ("a1-test","a2-test"):
            with gallery.connect() as c:
                previous=c.execute("SELECT id,state FROM gallery_jobs WHERE dataset_id=? AND tenant=? ORDER BY created DESC LIMIT 1",(dataset,tenant_context.get())).fetchone()
            job=gallery.resume(previous["id"],retry_failed=False) if previous and previous["state"]!="COMPLETED" else gallery.job(previous["id"]) if previous else gallery.create_job(dataset)
            last=-1
            while job["state"] in {"QUEUED","RUNNING"}:
                if job["completed"]!=last and (job["completed"]%10==0 or job["completed"]==job["total"]):
                    print(dataset,job["completed"],"/",job["total"],"failed",job["failed"],"rejected",job["rejected"],flush=True);last=job["completed"]
                time.sleep(.5);job=gallery.job(job["id"])
            if job["state"]!="COMPLETED" or job["remaining"]: raise RuntimeError("Final evaluation interrupted; resume the same jobs instead of selecting a new subset")
            summaries[dataset]={"job":job,"metrics":gallery.metrics(dataset)}
        # Reproducible compatibility checks on the same existing development fixtures, kept separate.
        for r in registry.records.values():
            if r["split"]=="TRAIN": gallery.analyze(r["id"])
        with gallery.connect() as c:
            baseline=[{"fingerprint":gallery.fingerprint,"cache_key":r["cache_key"],"result":json.loads(r["payload"]),"elapsed_seconds":r["elapsed"],"created_at_wib":r["created"]} for r in c.execute("SELECT * FROM gallery_results WHERE tenant=? ORDER BY image_id",(tenant_context.get(),))]
        (root/"baseline_results.jsonl").write_text("\n".join(encoded(r) for r in baseline)+"\n",encoding="utf-8")
        if verify_domain("bsf")!=before: raise ValueError("Frozen model integrity failure")
        for name,expected in registry.protocol["protected_inputs"].items():
            if sha256(BSF_ROOT/name)!=expected: raise ValueError("Frozen data changed during evaluation")
        receipt={"state":"COMPLETED_AND_RELEASED","released_at_wib":timestamp(),"registry_digest":registry.digest,
            "protocol_sha256":sha256(root/"evaluation_protocol.json"),"configuration_fingerprint":gallery.fingerprint,
            "baseline_sha256":sha256(root/"baseline_results.jsonl"),"final_test_blind_status":"RELEASED_NOT_BLIND_AFTER_FINAL_EVALUATION",
            "historical_exposure":"A2 ID1102 had prior preview exposure; no claim of pristine prior visual blindness",
            "authorization":registry.protocol["authorization"],"datasets":summaries,"frozen_models_preserved":True,
            "scientific_status":"EXPLORATORY_UNVERIFIED_ROIS_AND_INCOMPLETE_A1_LABELS_NOT_FIELD_VALIDATED",
            "strict_A2_final_metric_status":"UNAVAILABLE_WITHOUT_REVIEWED_FINAL_TEST_ROIS; automatic-ROI descriptive errors are separate"}
        write(root/"final_evaluation.json",receipt)
        inventory=json.loads((root/"inventory.json").read_text(encoding="utf-8"))
        inventory.update(evaluation_status="COMPLETED_AND_RELEASED",final_test_blind_status=receipt["final_test_blind_status"])
        write(root/"inventory.json",inventory)
        thumbdir=root/"thumbnails";thumbdir.mkdir(exist_ok=True)
        for r in registry.records.values():
            if r["access_status"]!="AVAILABLE": continue
            with Image.open(io.BytesIO(registry.raw(r["id"]))) as im:
                image=ImageOps.exif_transpose(im).convert("RGB");image.thumbnail((320,240));image.save(thumbdir/f"{r['id']}.jpg",quality=80)
        print(json.dumps({"state":receipt["state"],"metrics":{k:v["metrics"] for k,v in summaries.items()},"thumbnail_count":len(list(thumbdir.glob("*.jpg")))},indent=2),flush=True)
    finally:
        gallery.close();tenant_context.reset(marker)


if __name__=="__main__": evaluate()
