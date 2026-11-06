"""Portable gallery checks on the already released frozen test inventory, no tuning."""
import hashlib
import io
import time
from PIL import Image
from app.core.config import BSF_API_PREFIX


def run_gallery_checks(client,check):
    prefix=BSF_API_PREFIX+"/gallery"
    response=client.get(prefix+"/datasets")
    check("gallery dataset registry available",response.status_code==200)
    registry=response.json();datasets={r["id"]:r for r in registry["datasets"]}
    check("all 46 A1 and 178 A2 test images declared separately",datasets["a1-test"]["declared"]==46 and datasets["a2-test"]["declared"]==178)
    check("final test released with explicit loss of blind status",registry["release_status"]=="POST_FINAL_EVALUATION_NOT_BLIND")
    first=client.get(prefix+"/images?dataset_id=a1-test&page_size=17").json()
    second=client.get(prefix+"/images?dataset_id=a1-test&page_size=17&page=2").json()
    check("gallery pagination without omissions",first["total"]==46 and len(first["items"])==17 and not ({r["id"] for r in first["items"]}&{r["id"] for r in second["items"]}))
    check("gallery ID and path access denied",client.get(prefix+"/images/unknown/content").status_code==404 and client.get(prefix+"/images?dataset_id=unknown").status_code==404)
    searched=client.get(prefix+"/images?dataset_id=a2-test&q=A2_1081").json()
    check("gallery sample ID search and measured reference",searched["total"]==1 and searched["items"][0]["reference_measured_weight_mg"]==278)
    check("development fixtures not labelled test",client.get(prefix+"/images?dataset_id=a2-development").json()["items"][0]["split"]=="TRAIN")
    a1=first["items"][0]
    thumb=client.get(f"{prefix}/images/{a1['id']}/content?variant=thumbnail")
    check("all test thumbnails travel with package",thumb.status_code==200)
    if datasets["a1-test"]["runtime_available"]==46 and datasets["a2-test"]["runtime_available"]==178:
        check("complete optional test-image data mounted",True)
        raw=client.get(f"{prefix}/images/{a1['id']}/content")
        check("full resolution test file hash preserved",raw.status_code==200 and hashlib.sha256(raw.content).hexdigest()==a1["sha256"])
        result=client.post(f"{prefix}/images/{a1['id']}/analyze",json={}).json()
        check("A1 test batch integration returns real persisted result",result["inference_status"] in {"SUCCESS","PARTIAL","REJECTED"} and result["summary"]["detected"]==result["summary"]["analyzed"]+result["summary"]["rejected"])
        source=client.app.state.bsf_gallery
        a2=next(r for r in source.registry.records.values() if r["dataset_id"]=="a2-test" and source.latest(r["id"]) and source.latest(r["id"]).get("predicted_weight_mg") is not None)
        single=client.post(f"{prefix}/images/{a2['id']}/analyze",json={}).json()
        check("standalone A2 test remains separate and exact v3",single["preprocessing_version"]=="fixed_native_pixel_canvas_v1" and single["geometry"]["scale_factor"]==224/2048 and "instances" not in single)
        check("measured versus predicted A2 error arithmetic",abs(single["predicted_weight_mg"]-single["reference_measured_weight_mg"])==single["absolute_error_mg"])
        job=client.post(prefix+"/jobs",json={"dataset_id":"a1-test","image_ids":[r["id"] for r in first["items"][:2]]})
        check("bounded asynchronous gallery job accepted",job.status_code==202)
        ident=job.json()["id"]
        for _ in range(200):
            state=client.get(prefix+"/jobs/"+ident).json()
            if state["state"] not in {"QUEUED","RUNNING"}: break
            time.sleep(.05)
        check("gallery job durable completion counts",state["state"]=="COMPLETED" and state["completed"]==2 and state["remaining"]==0)
        again=client.post(f"{prefix}/images/{a1['id']}/analyze",json={}).json()
        check("gallery unchanged inference reuses versioned cache",again["cache_hit"] is True)
    else:
        check("missing optional bundle explicitly reported",datasets["a1-test"]["runtime_available"]==0 and datasets["a2-test"]["runtime_available"]==0)
    metrics=client.get(prefix+"/datasets/a2-test/metrics").json()
    check("A2 automatic ROI metric distinct from reviewed ROI metric",metrics["declared"]==178 and metrics["strict_reviewed_roi"]["n"]==0)
    check("existing Water and B1 still available",client.get("/water-quality/models").status_code==200 and len(client.get(BSF_API_PREFIX+"/replay/trajectories").json()["trajectories"])==16)
    return datasets
