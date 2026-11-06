"""Frozen membership, safe gallery access, real development inference and durable job contracts."""
import hashlib
import io
import json
import time
from pathlib import Path

import pandas as pd
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import BSF_ROOT, BSF_GALLERY_ROOT
from app.core.security import tenant_context
from app.main import app
from app.services.bsf_gallery import GalleryRegistry,GalleryService,contained
from app.services.bsf_intelligence import BsfHistory


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    with TestClient(app) as c:
        directory=tmp_path_factory.mktemp("gallery")
        assert c.app.state.bsf_intelligence
        svc=GalleryService(c.app.state.bsf_intelligence.models_runtime,BsfHistory(directory/"history.sqlite3"),db_path=directory/"gallery.sqlite3")
        previous=c.app.state.bsf_gallery;c.app.state.bsf_gallery=svc
        yield c
        svc.close();c.app.state.bsf_gallery=previous


def test_complete_frozen_test_membership_and_integrity(client):
    registry=client.app.state.bsf_gallery.registry
    for name,count in (("a1",46),("a2",178)):
        frozen=pd.read_csv(BSF_ROOT/f"hasil/model_a_preparation_v1/{name}_manifest.csv")
        expected=set(frozen.loc[frozen.split.eq("test"),"image_sha256"])
        discovered=[r for r in registry.records.values() if r["dataset_id"]==name+"-test"]
        assert len(discovered)==count and set(r["sha256"] for r in discovered)==expected
        assert all(r["split"]=="TEST" for r in discovered)
    assert len(registry.records)==226
    assert all(r["split"]=="TRAIN" for r in registry.records.values() if "development" in r["dataset_id"])


def test_pagination_filter_search_and_id_safety(client):
    prefix="/api/v1/bsf/gallery"
    listed=client.get(prefix+"/images?dataset_id=a2-test&page_size=17").json()
    assert listed["total"]==178 and len(listed["items"])==17 and listed["pages"]==11
    searched=client.get(prefix+"/images?dataset_id=a2-test&q=A2_1081").json()
    assert searched["total"]==1 and searched["items"][0]["sample_id"]=="A2_1081"
    assert client.get(prefix+"/images?dataset_id=unknown").status_code==404
    assert client.get(prefix+"/images?status=BAD").status_code==422
    assert client.get(prefix+"/images/unknown/content").status_code==404
    assert client.get(prefix+"/images?image_path=C:/Windows/win.ini").status_code==200  # ignored, never used as a path
    with pytest.raises(HTTPException): contained(BSF_ROOT,"../secret")
    with pytest.raises(HTTPException): contained(BSF_ROOT,Path("C:/Windows/win.ini"))


def test_unreleased_test_stays_locked(tmp_path,client):
    original=client.app.state.bsf_gallery.registry
    for name in ("manifest.json","evaluation_protocol.json"):
        (tmp_path/name).write_bytes((original.root/name).read_bytes())
    sealed=GalleryRegistry(tmp_path)
    record=next(r for r in sealed.records.values() if r["split"]=="TEST")
    assert not sealed.unlocked(record)
    with pytest.raises(HTTPException) as exc: sealed.raw(record["id"])
    assert exc.value.status_code==423


def test_gallery_development_real_inference_cache_and_previews(client):
    svc=client.app.state.bsf_gallery;prefix="/api/v1/bsf/gallery"
    for collection in ("a1-development","a2-development"):
        r=next(r for r in svc.registry.records.values() if r["dataset_id"]==collection)
        raw=client.get(f"{prefix}/images/{r['id']}/content")
        assert raw.status_code==200 and hashlib.sha256(raw.content).hexdigest()==r["sha256"]
        with Image.open(io.BytesIO(raw.content)) as im: assert im.size==(r["width"],r["height"])
        result=client.post(f"{prefix}/images/{r['id']}/analyze",json={"force":True}).json()
        assert result["inference_status"] in {"SUCCESS","PARTIAL"}
        cached=client.post(f"{prefix}/images/{r['id']}/analyze",json={}).json()
        assert cached["cache_hit"] and cached["cache_key"]==result["cache_key"]
        assert client.get(f"{prefix}/images/{r['id']}/content?variant=overlay").status_code==200
        if r["track"]=="A1":
            s=result["summary"];assert s["analyzed"]>0 and s["detected"]==s["analyzed"]+s["rejected"]
        else:
            assert result["reference_measured_weight_mg"]==114
            assert result["absolute_error_mg"]==pytest.approx(abs(result["predicted_weight_mg"]-114))
            assert client.get(f"{prefix}/images/{r['id']}/content?variant=processed").status_code==200
            assert result["geometry"]["scale_factor"]==224/2048


def test_cache_invalidation_and_result_persistence(client):
    svc=client.app.state.bsf_gallery
    r=next(r for r in svc.registry.records.values() if r["dataset_id"]=="a2-development")
    before=svc.key(r)
    assert svc.key({**r,"sha256":"different-image-hash"})!=before
    assert svc.key(r,{"roi_bbox":[1,2,3,4],"reviewer":"test"})!=before
    saved=dict(svc.configuration)
    try:
        svc.configuration={**saved,"pipeline_version":"cache-contract-next-version"}
        assert svc.key(r)!=before
        svc.configuration={**saved,"artifact_hashes":{**saved["artifact_hashes"],"test-only-checkpoint-hash":"different"}}
        assert svc.key(r)!=before
    finally: svc.configuration=saved
    reopened=GalleryService(svc.runtime,svc.history,registry=svc.registry,db_path=svc.path)
    try: assert reopened.latest(r["id"])["predicted_weight_mg"]==svc.latest(r["id"])["predicted_weight_mg"]
    finally: reopened.close()


def wait_job(client,ident):
    for _ in range(120):
        j=client.get("/api/v1/bsf/gallery/jobs/"+ident).json()
        if j["state"] not in {"RUNNING","QUEUED"}: return j
        time.sleep(.1)
    raise AssertionError("Job timeout")


def test_incremental_job_and_failed_items_remain_visible(client,monkeypatch):
    svc=client.app.state.bsf_gallery;prefix="/api/v1/bsf/gallery"
    r=next(r for r in svc.registry.records.values() if r["dataset_id"]=="a2-development")
    actual=svc._compute
    def fail(record,review): raise ValueError("Simulated software I/O failure for job recovery test")
    monkeypatch.setattr(svc,"_compute",fail)
    created=client.post(prefix+"/jobs",json={"dataset_id":"a2-development","force":True})
    assert created.status_code==202
    failed=wait_job(client,created.json()["id"])
    assert failed["completed"]==1 and failed["failed"]==1 and failed["remaining"]==0
    visible=client.get(prefix+"/images?dataset_id=a2-development&status=FAILED").json()
    assert visible["total"]==1 and visible["items"][0]["id"]==r["id"]
    monkeypatch.setattr(svc,"_compute",actual)
    retry=client.post(prefix+f"/jobs/{failed['id']}/resume?retry_failed=true")
    assert retry.status_code==202
    completed=wait_job(client,failed["id"])
    assert completed["successful"]==1 and completed["completed"]==1 and completed["items"][0]["attempts"]==2


def test_dead_worker_restart_and_tenant_isolation(client):
    svc=client.app.state.bsf_gallery
    import uuid
    ident=uuid.uuid4().hex
    r=next(r for r in svc.registry.records.values() if r["dataset_id"]=="a2-development")
    with svc.connect() as c:
        c.execute("INSERT INTO gallery_jobs VALUES(?,?,?,?,?,?,?,?,?,?)",(ident,"local_demo","a2-development","RUNNING","now","now",json.dumps({"fingerprint":svc.fingerprint,"force":False}),99999999,0,"dead-worker"))
        c.execute("INSERT INTO gallery_items(job_id,image_id,status) VALUES(?,?,'RUNNING')",(ident,r["id"]))
    recovered=GalleryService(svc.runtime,svc.history,registry=svc.registry,db_path=svc.path)
    try:
        assert recovered.job(ident)["state"]=="INTERRUPTED"
        assert recovered.job(ident)["remaining"]==1
        recovered.resume(ident)
        for _ in range(100):
            if recovered.job(ident)["state"]=="COMPLETED":break
            time.sleep(.1)
        assert recovered.job(ident)["completed"]==1
        token=tenant_context.set("another-farm")
        try:
            with pytest.raises(HTTPException) as e: recovered.job(ident)
            assert e.value.status_code==404
        finally: tenant_context.reset(token)
    finally: recovered.close()


def test_roi_adapter_is_frozen_development_algorithm(client):
    from app.services.bsf_gallery_roi import propose_roi
    import a2_preprocessing_v2 as original
    registry=client.app.state.bsf_gallery.registry
    r=next(r for r in registry.records.values() if r["dataset_id"]=="a2-development")
    with Image.open(io.BytesIO(registry.raw(r["id"]))) as image:
        assert propose_roi(image)==original.propose_roi(image)


def test_missing_or_corrupted_optional_bundle_is_explicit(tmp_path):
    source=BSF_GALLERY_ROOT
    for name in ("manifest.json","evaluation_protocol.json","final_evaluation.json"):
        (tmp_path/name).write_bytes((source/name).read_bytes())
    bundle_receipt=json.loads((source/"bundle_receipt.json").read_text())
    (tmp_path/"deployment.json").write_text(json.dumps({"storage_mode":"bundle","bundle_sha256":bundle_receipt["sha256"]}))
    registry=GalleryRegistry(tmp_path,bundle=tmp_path/"missing.zip")
    record=next(r for r in registry.records.values() if r["dataset_id"]=="a1-test")
    assert registry.unlocked(record) and not registry.available(record)
    with pytest.raises(HTTPException) as exc: registry.raw(record["id"])
    assert exc.value.status_code==503 and "belum dipasang" in exc.value.detail
    registry.bundle.write_bytes(b"not the signed approved bundle")
    assert not registry.available(record)
    with pytest.raises(HTTPException) as exc: registry.raw(record["id"])
    assert exc.value.status_code==503 and "Checksum" in exc.value.detail
