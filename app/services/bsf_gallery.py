"""Complete frozen-split gallery, safe image access, versioned cache and durable bounded jobs."""
from __future__ import annotations
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import importlib.metadata
import json
import math
import os
from pathlib import Path
import sqlite3
import threading
import time
import uuid
import zipfile

import psutil
from fastapi import HTTPException
from PIL import Image, ImageDraw, ImageOps

from app.core.config import APP_DIR, BSF_ROOT, BSF_GALLERY_ROOT, BSF_GALLERY_DATA, BSF_HISTORY_DB
from app.core.security import tenant_context
from app.core.http import normalize_json
from app.services.bsf_intelligence import decode_image, timestamp
from app.services.bsf_models import sha256, STATUS
from app.services.bsf_photo import analyze_photo, VERSION as PHOTO_VERSION, roi_check
from app.services.bsf_gallery_roi import propose_roi, CONFIG as ROI_CONFIG

VERSION="bsf_gallery_v1"
TERMINAL={"SUCCESS","PARTIAL","FAILED","REJECTED"}
PUBLIC="__public_final_evaluation__"


def encoded(value):
    return json.dumps(normalize_json(value),sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)


def contained(root, relative):
    path=(root / relative).resolve()
    if Path(relative).is_absolute() or ".." in Path(relative).parts or not path.is_relative_to(root.resolve()):
        raise HTTPException(403,"Akses berkas di luar dataset ditolak")
    return path


class GalleryRegistry:
    def __init__(self, root=BSF_GALLERY_ROOT, source_root=BSF_ROOT, bundle=BSF_GALLERY_DATA):
        self.root,self.source_root,self.bundle=Path(root),Path(source_root),Path(bundle)
        self.manifest=json.loads((self.root/"manifest.json").read_text(encoding="utf-8"))
        self.protocol=json.loads((self.root/"evaluation_protocol.json").read_text(encoding="utf-8"))
        self.digest=hashlib.sha256(encoded(self.manifest).encode()).hexdigest()
        if self.protocol["source_manifest_sha256"]!=self.digest: raise ValueError("Gallery manifest checksum mismatch")
        self.records={r["id"]:r for r in self.manifest["images"]}
        if len(self.records)!=len(self.manifest["images"]): raise ValueError("Duplicate gallery image ID")
        self.deployment=json.loads((self.root/"deployment.json").read_text()) if (self.root/"deployment.json").exists() else {"storage_mode":"source"}
        self._bundle_stat=None
        self._bundle_error=None

    def release(self):
        path=self.root/"final_evaluation.json"
        if not path.is_file(): return None
        value=json.loads(path.read_text(encoding="utf-8"))
        if value.get("registry_digest")!=self.digest or value.get("state")!="COMPLETED_AND_RELEASED": return None
        return value

    def get(self,image_id):
        record=self.records.get(image_id)
        if record is None: raise HTTPException(404,"Foto tidak ditemukan")
        return record

    def unlocked(self,record,evaluation=False):
        return record["split"]!="TEST" or evaluation or self.release() is not None

    def _bundle_ready(self):
        if not self.bundle.is_file(): return False
        stat=self.bundle.stat();key=(stat.st_size,stat.st_mtime_ns)
        if key!=self._bundle_stat:
            self._bundle_stat=key
            self._bundle_error=None if sha256(self.bundle)==self.deployment.get("bundle_sha256") else "Checksum bundle galeri tidak cocok"
        return self._bundle_error is None

    def available(self,record):
        if record["access_status"]!="AVAILABLE": return False
        return self.deployment["storage_mode"]=="source" or record["split"]!="TEST" or self._bundle_ready()

    def raw(self,image_id,*,evaluation=False):
        r=self.get(image_id)
        if not self.unlocked(r,evaluation): raise HTTPException(423,"Final-test menunggu evaluasi dan pelepasan resmi")
        if r["access_status"]!="AVAILABLE": raise HTTPException(422,r["error"] or "Sumber tidak dapat dibaca")
        try:
            if self.deployment["storage_mode"]=="bundle":
                if r["split"]=="TEST":
                    if not self._bundle_ready(): raise HTTPException(503,self._bundle_error or "Bundle galeri belum dipasang; lihat panduan impor")
                    with zipfile.ZipFile(self.bundle) as z:
                        info=z.getinfo(f"images/{image_id}.jpg")
                        if info.file_size>8*1024*1024: raise HTTPException(413,"Berkas gambar terlalu besar")
                        raw=z.read(info)
                else:
                    raw=contained(self.source_root.parent, f"fixtures/{'a1' if r['track']=='A1' else 'a2'}_development_train.jpg").read_bytes()
            else:
                loc=r["locator"]
                if "file" in loc:
                    path=contained(self.source_root,loc["file"])
                    if path.stat().st_size>8*1024*1024: raise HTTPException(413,"Berkas gambar terlalu besar")
                    raw=path.read_bytes()
                else:
                    path=contained(self.source_root,loc["archive"])
                    if Path(loc["member"]).is_absolute() or ".." in Path(loc["member"]).parts: raise HTTPException(403,"Anggota arsip tidak valid")
                    with zipfile.ZipFile(path) as z:
                        info=z.getinfo(loc["member"])
                        if info.file_size>8*1024*1024: raise HTTPException(413,"Berkas gambar terlalu besar")
                        raw=z.read(info)
        except (FileNotFoundError,KeyError,zipfile.BadZipFile) as exc:
            raise HTTPException(503,"Berkas galeri tidak tersedia atau arsip tidak valid") from exc
        if hashlib.sha256(raw).hexdigest()!=r["sha256"]: raise HTTPException(422,"Checksum gambar tidak cocok dengan manifest")
        return raw

    def content(self,image_id,thumbnail=False):
        r=self.get(image_id)
        if not self.unlocked(r): raise HTTPException(423,"Final-test masih terkunci")
        thumb=contained(self.root,f"thumbnails/{image_id}.jpg")
        if thumbnail and thumb.is_file(): return thumb.read_bytes()
        raw=self.raw(image_id)
        if not thumbnail: return raw
        with Image.open(io.BytesIO(raw)) as im:
            image=ImageOps.exif_transpose(im).convert("RGB");image.thumbnail((320,240))
            buffer=io.BytesIO();image.save(buffer,format="JPEG",quality=80)
            return buffer.getvalue()


class GalleryService:
    def __init__(self,runtime,history,*,registry=None,db_path=None,evaluation=False):
        self.registry=registry or GalleryRegistry()
        self.runtime,self.history,self.evaluation=runtime,history,evaluation
        self.path=Path(db_path or os.getenv("FISCYCLE_BSF_GALLERY_DB",str(BSF_HISTORY_DB.with_name("bsf_gallery.sqlite3"))))
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix="bsf-gallery")
        self.owner=uuid.uuid4().hex
        self.birth=psutil.Process().create_time()
        self.closed=False
        self.stop=threading.Event()
        self.active=threading.Lock()
        self.result_locks={}
        with self.connect() as c:
            c.executescript("""CREATE TABLE IF NOT EXISTS gallery_results (
              tenant TEXT NOT NULL,cache_key TEXT NOT NULL,image_id TEXT NOT NULL,status TEXT NOT NULL,
              payload TEXT NOT NULL,elapsed REAL NOT NULL,created TEXT NOT NULL, PRIMARY KEY(tenant,cache_key));
              CREATE INDEX IF NOT EXISTS gallery_image_results ON gallery_results(tenant,image_id,created);
              CREATE TABLE IF NOT EXISTS gallery_jobs (
              id TEXT PRIMARY KEY,tenant TEXT NOT NULL,dataset_id TEXT NOT NULL,state TEXT NOT NULL,
              created TEXT NOT NULL,updated TEXT NOT NULL,config TEXT NOT NULL,pid INTEGER,birth REAL,owner TEXT);
              CREATE TABLE IF NOT EXISTS gallery_items (
              job_id TEXT NOT NULL,image_id TEXT NOT NULL,status TEXT NOT NULL,cache_key TEXT,
              error TEXT,elapsed REAL,cache_hit INTEGER NOT NULL DEFAULT 0,attempts INTEGER NOT NULL DEFAULT 0,
              PRIMARY KEY(job_id,image_id));
              PRAGMA user_version=1;""")
            for job,pid,birth in c.execute("SELECT id,pid,birth FROM gallery_jobs WHERE state IN ('RUNNING','QUEUED')").fetchall():
                alive=False
                try: alive=bool(pid and abs(psutil.Process(pid).create_time()-birth)<.01)
                except (psutil.Error,TypeError): pass
                if not alive:
                    c.execute("UPDATE gallery_jobs SET state='INTERRUPTED',updated=? WHERE id=?",(timestamp(),job))
                    c.execute("UPDATE gallery_items SET status='PENDING' WHERE job_id=? AND status='RUNNING'",(job,))
        self.configuration={"pipeline_version":VERSION,"photo_version":PHOTO_VERSION,"imgsz":320,"confidence":.25,
            "max_det":300,"max_analyzed":64,"overlap_min_area_threshold":.5,"border_touch":"REJECT",
            "preprocessing":runtime.preprocessing,"roi_adapter":"a2_roi_v2_ranked","roi_config":ROI_CONFIG,
            "device":runtime.device,"artifact_hashes":self.registry.protocol["model_hashes"],
            "library_versions":{name:importlib.metadata.version(name) for name in ("torch","torchvision","ultralytics","Pillow","opencv-python","numpy")},
            "runtime_code_sha256":{f:sha256(APP_DIR/f) for f in ("services/bsf_models.py","services/bsf_photo.py","services/bsf_gallery_roi.py","services/bsf_gallery.py")}}
        self.fingerprint=hashlib.sha256(encoded(self.configuration).encode()).hexdigest()
        baseline=self.registry.root/"baseline_results.jsonl"
        if not evaluation and self.registry.release() and baseline.exists():
            with self.connect() as c:
                for line in baseline.read_text(encoding="utf-8").splitlines():
                    record=json.loads(line)
                    if record["fingerprint"]!=self.fingerprint: continue
                    result=record["result"];result.pop("history_id",None)
                    c.execute("INSERT OR IGNORE INTO gallery_results VALUES(?,?,?,?,?,?,?)",
                        (PUBLIC,record["cache_key"],result["image_id"],result["inference_status"],encoded(result),record["elapsed_seconds"],record["created_at_wib"]))

    def connect(self):
        c=sqlite3.connect(self.path,timeout=30);c.row_factory=sqlite3.Row
        return c

    def _cached(self,key):
        tenant=tenant_context.get()
        with self.connect() as c:
            return c.execute("SELECT * FROM gallery_results WHERE cache_key=? AND tenant IN (?,?) ORDER BY tenant=? DESC LIMIT 1",(key,tenant,PUBLIC,tenant)).fetchone()

    def key(self,r,review=None):
        return hashlib.sha256(encoded({"image_sha256":r["sha256"],"track":r["track"],"registry_digest":self.registry.digest,"roi_bbox":r.get("roi_bbox"),"pipeline":self.configuration,"review":review}).encode()).hexdigest()

    def latest(self,image_id):
        r=self.registry.get(image_id)
        tenant=tenant_context.get()
        with self.connect() as c:
            result=c.execute("SELECT * FROM gallery_results WHERE image_id=? AND tenant IN (?,?) AND json_extract(payload,'$.configuration_fingerprint')=? ORDER BY tenant=? DESC,created DESC LIMIT 1",
                (image_id,tenant,PUBLIC,self.fingerprint,tenant)).fetchone()
        return json.loads(result["payload"]) if result else None

    def public_record(self,r):
        allowed={k:v for k,v in r.items() if k not in {"locator","label_locator","label_sha256"}}
        unlocked=self.registry.unlocked(r,self.evaluation)
        result=self.latest(r["id"]) if unlocked else None
        allowed.update(locked=not unlocked,source_available=self.registry.available(r),
            inference_status=result["inference_status"] if result else "NOT_ANALYZED",
            inference_summary=result.get("summary") if result else None,
            predicted_weight_mg=result.get("predicted_weight_mg") if result else None,
            absolute_error_mg=result.get("absolute_error_mg") if result else None)
        if not unlocked: allowed["reference_measured_weight_mg"]=None
        return allowed

    def datasets(self):
        release=self.registry.release()
        collections=[]
        for source in self.registry.manifest["collections"]:
            images=[r for r in self.registry.records.values() if r["dataset_id"]==source["id"]]
            collections.append({**source,"runtime_available":sum(self.registry.available(r) for r in images),
                "demo_eligible":sum(self.registry.available(r) and self.registry.unlocked(r,self.evaluation) for r in images),
                "locked":source["split"]=="TEST" and not (release or self.evaluation)})
        return {"version":VERSION,"datasets":collections,"release_status":"POST_FINAL_EVALUATION_NOT_BLIND" if release else "FINAL_EVALUATION_PENDING",
            "status":STATUS,"storage_mode":self.registry.deployment["storage_mode"],"final_evaluation":release}

    def images(self,dataset=None,query="",status=None,page=1,page_size=20):
        if dataset and dataset not in {x["id"] for x in self.registry.manifest["collections"]}: raise HTTPException(404,"Koleksi tidak ditemukan")
        records=[r for r in self.registry.records.values() if (not dataset or r["dataset_id"]==dataset) and (not query or query.casefold() in (r["filename"]+" "+r["sample_id"]).casefold())]
        records=sorted(records,key=lambda r:(r["dataset_id"],r["sample_id"]))
        public=[self.public_record(r) for r in records]
        if status: public=[r for r in public if r["inference_status"]==status]
        start=(page-1)*page_size
        return {"items":public[start:start+page_size],"total":len(public),"page":page,"page_size":page_size,"pages":math.ceil(len(public)/page_size)}

    def _compute(self,r,review):
        raw=self.registry.raw(r["id"],evaluation=self.evaluation)
        common={"image_id":r["id"],"sample_id":r["sample_id"],"dataset_id":r["dataset_id"],"split":r["split"],
            "split_group_id":r["split_group_id"],"source":r["source"],"image_sha256":r["sha256"],"pipeline_version":VERSION,"status":STATUS}
        if r["track"]=="A1":
            if review: raise HTTPException(422,"ROI tunggal hanya untuk koleksi A2")
            value=analyze_photo(self.runtime,raw,"image/jpeg")
            summary=value["summary"]
            status="PARTIAL" if summary["analyzed"] and summary["rejected"] else "SUCCESS" if summary["analyzed"] else "REJECTED"
            return {**value,**common,"inference_status":status,"evaluation_scope":"EXPERIMENTAL_A1_TO_A2_INTEGRATION",
                "segmentation_accuracy":None,"annotation_limitation":"Kelengkapan anotasi belum disahkan; tidak menghitung akurasi segmentasi dari label yang belum lengkap."}
        image=decode_image(raw,"image/jpeg",require_unrotated=True)
        if image.size!=(4056,3040): raise ValueError("A2 source resolution incompatible")
        proposal=None
        if review:
            roi=review["roi_bbox"];roi_source="USER_REVIEWED_SOURCE_ROI"
            if not all(review.get(k) for k in ("whole_larva_visible","no_written_markings","reviewer")): raise HTTPException(422,"Konfirmasi review ROI belum lengkap")
        elif r.get("roi_bbox"):
            roi=r["roi_bbox"];roi_source=r["roi_source"]
        else:
            proposal=propose_roi(image);roi=proposal["crop_bbox"];roi_source="FROZEN_RANKED_V2_AUTOMATIC_PROPOSAL_UNREVIEWED"
        reason=None
        if not roi: reason="NO_CANDIDATE"
        elif proposal and proposal["source_edge_contact"]: reason="SOURCE_EDGE_CONTACT"
        elif proposal and proposal["shortcut_suspected"]: reason="SHORTCUT_SCREEN"
        elif not (0<=roi[0]<roi[2]<=image.width and 0<=roi[1]<roi[3]<=image.height): reason="OUT_OF_BOUNDS"
        elif max(roi[2]-roi[0],roi[3]-roi[1])>2048: reason="FULL_ROI_EXCEEDS_TRAIN_SELECTED_CANVAS"
        value=None
        if not reason: value=self.runtime.estimate_roi(image,roi,reviewed=bool(review))
        predicted=value["predicted_measured_weight_mg"] if value else None
        if predicted is not None and (not math.isfinite(predicted) or predicted<0):
            reason="INVALID_MODEL_WEIGHT";predicted=None
        reference=r["reference_measured_weight_mg"]
        error=predicted-reference if predicted is not None and reference is not None else None
        return {**common,"inference_status":"REJECTED" if reason else "SUCCESS","provenance":"AI_PREDICTED_A2",
            "evaluation_scope":"DEVELOPMENT_COMPATIBILITY" if r["split"]!="TEST" else "POST_FREEZE_FINAL_TEST_EXPLORATORY_ROI_PROTOCOL",
            "roi_bbox":roi,"roi_source":roi_source,"roi_review":review,"roi_proposal":proposal,"rejection_reason":reason,
            "predicted_weight_mg":predicted,"reference_measured_weight_mg":reference,"error_mg":error,"absolute_error_mg":abs(error) if error is not None else None,
            "unit":"mg/larva","weight_protocol":"MEASURED_WEIGHT_WET_DRY_UNCONFIRMED","model_version":"model_a2_training_v3/best.pt",
            "preprocessing_version":self.runtime.preprocessing["method"],"geometry":value["geometry"] if value else None,
            "processed_png_base64":value["processed_png_base64"] if value else None,
            "strict_reviewed_roi_protocol":bool(review) or bool(r.get("roi_bbox")),
            "limitations":["Native canvas 2048 -> 224 dan transform bobot persis v3.","ROI otomatis belum disahkan manusia; error bersifat deskriptif, bukan benchmark reviewed-ROI.",
                "Weight basah/kering dan skala fisik belum terverifikasi.","Satu primary group A2 test; jumlah foto bukan replikasi biologis independen."],
            "decision_support":{"status":"ABSTAIN_OPERATIONAL","rule_version":VERSION,
                "triggered_rule_ids":["A2-REVIEW-ROI"],"factors":{"roi_source":roi_source,"roi_bbox":roi,"rejection_reason":reason,"predicted_weight_mg":predicted},
                "evidence":"Frozen ROI ranking v2 and exact A2 v3 preprocessing contract", "approval_status":"VERIFICATION_ONLY",
                "recommendations":["Periksa larva utuh dan penanda pada ROI; konfirmasi pengukuran sebelum keputusan budidaya."]}}

    def analyze(self,image_id,*,review=None,force=False):
        r=self.registry.get(image_id)
        if not self.registry.unlocked(r,self.evaluation): raise HTTPException(423,"Final-test masih terkunci")
        key=self.key(r,review)
        with self.active:
            cached=self._cached(key)
            if cached and cached["status"]!="FAILED" and not force:
                value=json.loads(cached["payload"])
                if cached["tenant"]==PUBLIC:
                    value=self._save(r,key,value,0.0)
                return {**value,"cache_key":key,"cache_hit":True,"elapsed_seconds":float(cached["elapsed"])}
            start=time.perf_counter()
            try: value=self._compute(r,review)
            except Exception as exc:
                detail=exc.detail if isinstance(exc,HTTPException) else str(exc)
                value={"image_id":r["id"],"sample_id":r["sample_id"],"dataset_id":r["dataset_id"],"split":r["split"],
                    "inference_status":"FAILED","error":detail,"error_code":str(exc.status_code) if isinstance(exc,HTTPException) else type(exc).__name__,
                    "status":STATUS,"pipeline_version":VERSION,"provenance":"INFERENCE_ATTEMPT_FAILED"}
            elapsed=time.perf_counter()-start
            value=self._save(r,key,value,elapsed)
            return {**value,"cache_key":key,"cache_hit":False,"elapsed_seconds":elapsed}

    def _save(self,r,key,value,elapsed):
        value={k:v for k,v in value.items() if not k.endswith("_png_base64")}
        value.update(cache_key=key,configuration_fingerprint=self.fingerprint,created_at_wib=timestamp())
        value["history_id"]=self.history.add("GALLERY_"+r["track"],value.get("provenance","AI_PREDICTED"),normalize_json(value),
            model_version="a1_initial+model_a2_training_v3" if r["track"]=="A1" else "model_a2_training_v3",
            preprocessing_version=self.runtime.preprocessing["method"],rule_version=VERSION,image_sha256=r["sha256"])
        with self.connect() as c:
            c.execute("INSERT OR REPLACE INTO gallery_results VALUES(?,?,?,?,?,?,?)",(tenant_context.get(),key,r["id"],value["inference_status"],encoded(value),elapsed,timestamp()))
        return value

    def result(self,image_id,key=None):
        r=self.registry.get(image_id)
        if not self.registry.unlocked(r,self.evaluation): raise HTTPException(423,"Final-test masih terkunci")
        if key:
            row=self._cached(key)
            if not row or row["image_id"]!=image_id: raise HTTPException(404,"Hasil tidak ditemukan")
            value=json.loads(row["payload"])
        else: value=self.latest(image_id)
        if not value: raise HTTPException(404,"Foto belum dianalisis pada konfigurasi ini")
        return value

    def overlay(self,image_id,key=None):
        value=self.result(image_id,key)
        image=decode_image(self.registry.raw(image_id),"image/jpeg")
        pen=ImageDraw.Draw(image)
        for item in value.get("instances",[]):
            points=[tuple(p) for p in item["polygon_xy"]]
            if len(points)>=3:
                color="#e07822" if item.get("rejection_reason") else "#087f70"
                pen.line(points+[points[0]],fill=color,width=2)
                pen.text(points[0],item.get("instance_id",""),fill=color)
        if value.get("roi_bbox"): pen.rectangle(value["roi_bbox"],outline="#087f70",width=8)
        image.thumbnail((1200,1200));stream=io.BytesIO();image.save(stream,format="PNG")
        return stream.getvalue()

    def create_job(self,dataset_id,*,image_ids=None,force=False):
        valid=[r for r in self.registry.records.values() if r["dataset_id"]==dataset_id]
        if not valid: raise HTTPException(404,"Koleksi tidak ditemukan")
        if image_ids is not None:
            wanted=set(image_ids)
            if not wanted or wanted-{r["id"] for r in valid}: raise HTTPException(422,"ID foto tidak sesuai koleksi")
            valid=[r for r in valid if r["id"] in wanted]
        if any(not self.registry.unlocked(r,self.evaluation) for r in valid): raise HTTPException(423,"Final-test belum dilepaskan")
        ident=uuid.uuid4().hex;tenant=tenant_context.get()
        with self.connect() as c:
            if c.execute("SELECT count(*) FROM gallery_jobs WHERE tenant=? AND state IN ('QUEUED','RUNNING')",(tenant,)).fetchone()[0]>=8:
                raise HTTPException(429,"Antrean tenant penuh")
            c.execute("INSERT INTO gallery_jobs VALUES(?,?,?,?,?,?,?,?,?,?)",(ident,tenant,dataset_id,"QUEUED",timestamp(),timestamp(),encoded({"fingerprint":self.fingerprint,"force":force}),os.getpid(),self.birth,self.owner))
            c.executemany("INSERT INTO gallery_items(job_id,image_id,status) VALUES(?,?,'PENDING')",[(ident,r["id"]) for r in valid])
        self.executor.submit(self._run,ident,tenant)
        return self.job(ident)

    def _run(self,ident,tenant):
        context=tenant_context.set(tenant)
        try:
            with self.connect() as c:
                claimed=c.execute("UPDATE gallery_jobs SET state='RUNNING',pid=?,birth=?,owner=?,updated=? WHERE id=? AND state='QUEUED'",(os.getpid(),self.birth,self.owner,timestamp(),ident)).rowcount
                if not claimed: return
                config=json.loads(c.execute("SELECT config FROM gallery_jobs WHERE id=?",(ident,)).fetchone()[0])
                ids=[r[0] for r in c.execute("SELECT image_id FROM gallery_items WHERE job_id=? AND status='PENDING' ORDER BY image_id",(ident,))]
            if config["fingerprint"]!=self.fingerprint:
                with self.connect() as c: c.execute("UPDATE gallery_jobs SET state='CONFIG_CHANGED',updated=? WHERE id=?",(timestamp(),ident))
                return
            for image_id in ids:
                with self.connect() as c:
                    state=c.execute("SELECT state FROM gallery_jobs WHERE id=?",(ident,)).fetchone()[0]
                    if self.stop.is_set() or state!="RUNNING": break
                    c.execute("UPDATE gallery_items SET status='RUNNING',attempts=attempts+1 WHERE job_id=? AND image_id=?",(ident,image_id))
                result=self.analyze(image_id,force=config.get("force",False))
                with self.connect() as c:
                    c.execute("UPDATE gallery_items SET status=?,cache_key=?,error=?,elapsed=?,cache_hit=? WHERE job_id=? AND image_id=?",
                        (result["inference_status"],result["cache_key"],result.get("error") or result.get("rejection_reason"),result["elapsed_seconds"],int(result["cache_hit"]),ident,image_id))
                    c.execute("UPDATE gallery_jobs SET updated=? WHERE id=?",(timestamp(),ident))
            with self.connect() as c:
                pending=c.execute("SELECT count(*) FROM gallery_items WHERE job_id=? AND status IN ('PENDING','RUNNING')",(ident,)).fetchone()[0]
                c.execute("UPDATE gallery_jobs SET state=?,updated=? WHERE id=?",("INTERRUPTED" if pending else "COMPLETED",timestamp(),ident))
                if pending: c.execute("UPDATE gallery_items SET status='PENDING' WHERE job_id=? AND status='RUNNING'",(ident,))
        except Exception:
            with self.connect() as c:
                c.execute("UPDATE gallery_jobs SET state='INTERRUPTED',updated=? WHERE id=?",(timestamp(),ident))
                c.execute("UPDATE gallery_items SET status='PENDING' WHERE job_id=? AND status='RUNNING'",(ident,))
        finally: tenant_context.reset(context)

    def job(self,ident):
        with self.connect() as c:
            row=c.execute("SELECT * FROM gallery_jobs WHERE id=? AND tenant=?",(ident,tenant_context.get())).fetchone()
            if not row: raise HTTPException(404,"Pekerjaan tidak ditemukan")
            items=[dict(r) for r in c.execute("SELECT * FROM gallery_items WHERE job_id=? ORDER BY image_id",(ident,))]
        counts={s:sum(r["status"]==s for r in items) for s in (*TERMINAL,"PENDING","RUNNING")}
        return {"id":ident,"dataset_id":row["dataset_id"],"state":row["state"],"created_at_wib":row["created"],"updated_at_wib":row["updated"],
            "total":len(items),"completed":sum(counts[s] for s in TERMINAL),"successful":counts["SUCCESS"],"partial":counts["PARTIAL"],
            "failed":counts["FAILED"],"rejected":counts["REJECTED"],"remaining":counts["PENDING"]+counts["RUNNING"],"counts":counts,
            "cache_hits":sum(r["cache_hit"] for r in items),"items":items,"configuration":json.loads(row["config"])}

    def jobs(self):
        with self.connect() as c: ids=[r[0] for r in c.execute("SELECT id FROM gallery_jobs WHERE tenant=? ORDER BY created DESC LIMIT 20",(tenant_context.get(),))]
        return [self.job(i) for i in ids]

    def resume(self,ident,retry_failed=False):
        previous=self.job(ident)
        if previous["state"] in {"RUNNING","QUEUED"}: return previous
        if previous["configuration"]["fingerprint"]!=self.fingerprint: raise HTTPException(409,"Konfigurasi berubah; buat pekerjaan baru agar hasil lama tidak tercampur")
        with self.connect() as c:
            if retry_failed: c.execute("UPDATE gallery_items SET status='PENDING' WHERE job_id=? AND status='FAILED'",(ident,))
            c.execute("UPDATE gallery_jobs SET state='QUEUED',updated=? WHERE id=?",(timestamp(),ident))
        self.executor.submit(self._run,ident,tenant_context.get())
        return self.job(ident)

    def metrics(self,dataset_id):
        records=[r for r in self.registry.records.values() if r["dataset_id"]==dataset_id]
        if not records: raise HTTPException(404,"Koleksi tidak ditemukan")
        values=[self.latest(r["id"]) for r in records];values=[v for v in values if v]
        pairs=[v for v in values if v.get("error_mg") is not None]
        def scores(items):
            errors=[v["error_mg"] for v in items];n=len(errors)
            return {"n":n,"MAE_mg":sum(abs(v) for v in errors)/n if n else None,"RMSE_mg":math.sqrt(sum(v*v for v in errors)/n) if n else None,"bias_mg":sum(errors)/n if n else None}
        return {"dataset_id":dataset_id,"declared":len(records),"analyzed":len(values),"pending":len(records)-len(values),
            "statuses":{s:sum(v["inference_status"]==s for v in values) for s in TERMINAL},
            "descriptive_automatic_roi":scores(pairs),"strict_reviewed_roi":scores([v for v in pairs if v.get("strict_reviewed_roi_protocol")]),
            "prediction_coverage":len(pairs)/len(records) if records[0]["track"]=="A2" else None,
            "segmentation_accuracy":None,"primary_split_groups":len({r["split_group_id"] for r in records}),
            "limitation":"A1 annotations incomplete; A2 automatic-ROI errors are exploratory. Image count is not independent biological group count.","status":STATUS}

    def close(self):
        self.closed=True;self.stop.set();self.executor.shutdown(wait=True,cancel_futures=True)
        with self.connect() as c:
            c.execute("UPDATE gallery_jobs SET state='INTERRUPTED',updated=? WHERE owner=? AND state IN ('RUNNING','QUEUED')",(timestamp(),self.owner))
