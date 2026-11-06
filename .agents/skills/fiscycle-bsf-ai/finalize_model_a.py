"""Model A working-data finalization, without fitting or changing frozen inputs.

prepare: class mapping + 43-image development comparison; expand: all development crops;
package: review pages/reports/receipt; verify: integrity; import-reviews: human decisions.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import math
import platform
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import a2_preprocessing_v2 as roi
from a2_preprocessing import letterbox_crop

ROOT=Path(__file__).resolve().parent
FROZEN=ROOT/"hasil/model_a_preparation_v1"
QA=ROOT/"hasil/model_a_pretraining_qa_v1"
OUT=ROOT/"hasil/model_a_finalization_v1"
FONT=ImageFont.truetype("C:/Windows/Fonts/arial.ttf",16)
CHECKS={"A1":["coverage_complete","instances_separate","visible_masks_only","boundaries_unambiguous",
               "duplicates_checked","minimum_visibility_policy","truncation_policy"],
        "A2":["correct_larva","source_body_complete","both_ends_inside","morphology_preserved",
               "no_id_or_sex","no_ruler","background_acceptable"]}
POLICY={"version":"model_a_annotation_policy_v1","status":"PROJECT_POLICY_APPROVED_NOT_IMAGE_APPROVAL",
        "authorization":"User attachment a5123662-feb2-4330-883a-c10d0883fdd3; approved project decisions",
        "source_to_target":{"0":0,"1":0},"target_class_name":"visible_bsf_larva",
        "biological_equivalence_verified":False,"mask_type":"visible_only",
        "minimum_visible_area_native_pixels":16,"minimum_bbox_short_side_native_pixels":3,
        "minimum_visibility_ratio":"NOT_ESTIMATED: invisible extent unknown",
        "ambiguous_or_too_small":"HOLD_WHOLE_IMAGE; no implicit background negatives or invented geometry",
        "disconnected_visible_fragments":"HOLD until same-instance multipolygon representation supported; no bridge across occluder",
        "truncation":"A1 allowed only if visible identity/boundary unambiguous and human approved; A2 source truncated held",
        "source_classes_preserved":True,"human_image_review_required":True,
        "training_allowed_splits":["train"],"metric_allowed_splits":["validation","test"],
        "a2_preprocessing_allowed_splits":["train","validation"],"target_weight_name":"measured_weight_g",
        "pixel_to_mm":None,"wet_dry_protocol":"UNKNOWN"}
# Agent visual observations on the unchanged prior 43-image development subset.
# These are hold reasons, never approvals, and do not enter ROI coordinates.
VISUAL_V2={18:"CROP_TRUNCATES_BODY",1460:"WRONG_OBJECT_STAIN",253:"SOURCE_TRUNCATED",
           **{i:"RULER_RETAINED" for i in [107,723,724,773,815,907,908,954,1000,1002,1041,1080]},
           **{i:"BACKGROUND_REVIEW" for i in [62,1372,1461,1474]}}


def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(8*1024*1024),b""): h.update(b)
    return h.hexdigest()


def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()


def object_hash(obj): return hashlib.sha256(canonical(obj)).hexdigest()
def read_json(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def write_json(path,obj): Path(path).write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
def csv(name,frame): frame.to_csv(OUT/name,index=False,lineterminator="\n")


def inputs(full=False):
    freeze=read_json(FROZEN/"FREEZE.json")
    assert sha(ROOT/"prepare_model_a.py")==freeze["script_sha256"]
    for name,h in freeze["outputs"].items(): assert sha(FROZEN/name)==h,name
    receipt=read_json(QA/"QA_RECEIPT.json")
    for name,h in receipt["outputs"].items(): assert sha(QA/name)==h,name
    for name,h in receipt["code_sha256"].items(): assert sha(ROOT/name)==h,name
    for name,h in read_json(FROZEN/"protected_integrity.json").items(): assert sha(ROOT/name)==h,name
    if full:
        for r in pd.read_csv(FROZEN/"source_integrity.csv").itertuples(): assert sha(ROOT/r.path)==r.sha256,r.path
    return {"freeze_sha256":sha(FROZEN/"FREEZE.json"),"qa_receipt_sha256":sha(QA/"QA_RECEIPT.json"),
            "full_raw_verification":full,"old_outputs_and_b1_unchanged":True}


def parse_labels(path):
    records=[]
    for i,line in enumerate(Path(path).read_text().splitlines(),1):
        tokens=line.split()
        points=np.array(tokens[1:],float).reshape(-1,2)
        assert int(tokens[0]) in (0,1) and len(points)>=3 and np.isfinite(points).all()
        assert ((points>=0)&(points<=1)).all() and cv2.contourArea(points.astype(np.float32))>0
        records.append(dict(source_line=i,source_class=int(tokens[0]),target_class=0,points=points.tolist()))
    return records


def validate_polygons(polys, enforce_visibility=False):
    if not isinstance(polys,list): raise ValueError("Polygon list required")
    seen=set()
    for p in polys:
        pts=np.array(p.get("points"),float)
        if pts.ndim!=2 or pts.shape[1]!=2 or len(pts)<3 or not np.isfinite(pts).all():
            raise ValueError("Invalid polygon coordinates")
        if not ((pts>=0)&(pts<=1)).all() or p.get("target_class")!=0:
            raise ValueError("Invalid normalized coordinates/target class")
        area=cv2.contourArea(pts.astype(np.float32))*640*640
        if area<=0: raise ValueError("Zero polygon area")
        if enforce_visibility and (area<POLICY["minimum_visible_area_native_pixels"] or
                float(np.ptp(pts,axis=0).min())*640<POLICY["minimum_bbox_short_side_native_pixels"]):
            raise ValueError("Below documented visibility floor; hold image")
        key=p.get("source_line")
        if key is not None:
            if key in seen: raise ValueError("Duplicated source instance ID")
            seen.add(key)
        # Proper crossings of non-adjacent edges: no bow-tie polygons accepted.
        for i in range(len(pts)):
            a,b=pts[i],pts[(i+1)%len(pts)]
            if np.array_equal(a,b): raise ValueError("Zero-length polygon edge")
            for j in range(i+2,len(pts)):
                if i==0 and j==len(pts)-1: continue
                c,d=pts[j],pts[(j+1)%len(pts)]
                cross=lambda u,v:float(u[0]*v[1]-u[1]*v[0])
                if cross(b-a,c-a)*cross(b-a,d-a)<-1e-15 and cross(d-c,a-c)*cross(d-c,b-c)<-1e-15:
                    raise ValueError("Self-crossing polygon")


def polygon_text(polys,source_lines):
    lines=[]
    for p in polys:
        source_line=p.get("source_line")
        if source_line is not None and 1<=source_line<=len(source_lines):
            original=source_lines[source_line-1].split()
            old=np.array(original[1:],float).reshape(-1,2).tolist()
            if old==p["points"]:
                lines.append("0 "+" ".join(original[1:])); continue
        lines.append("0 "+" ".join(format(float(c),".12g") for xy in p["points"] for c in xy))
    return "\n".join(lines)+("\n" if lines else "")


def propose_duplicates(records):
    masks=[]; changes=[]; removed=set()
    for p in records:
        mask=np.zeros((640,640),np.uint8)
        cv2.fillPoly(mask,[np.round(np.array(p["points"])*639).astype(np.int32)],1)
        masks.append(mask)
    for i in range(len(records)):
        if i in removed: continue
        for j in range(i):
            if j in removed: continue
            a=np.array(records[i]["points"]); b=np.array(records[j]["points"])
            if (a.max(0)<b.min(0)).any() or (b.max(0)<a.min(0)).any(): continue
            intersection=int((masks[i]&masks[j]).sum())
            union=int(masks[i].sum()+masks[j].sum()-intersection)
            iou=intersection/max(union,1)
            if iou>=.90:
                removed.add(i)
                changes.append({"type":"PROPOSE_REMOVE_POSSIBLE_DUPLICATE","source_line":records[i]["source_line"],
                                "keep_source_line":records[j]["source_line"],"raster_iou":iou,
                                "human_approval_required":True})
                break
    return [p for i,p in enumerate(records) if i not in removed],changes


def build_a1():
    (OUT/"a1_mapped_labels").mkdir(exist_ok=True)
    (OUT/"a1_proposed_labels").mkdir(exist_ok=True)
    a=pd.read_csv(FROZEN/"a1_manifest.csv")
    q=pd.read_csv(QA/"a1_prioritized_review_queue.csv").set_index("image_path")
    rows=[]; entries=[]; lineage=[]; proposals=[]
    for r in a.itertuples():
        assert sha(ROOT/r.image_path)==r.image_sha256 and sha(ROOT/r.label_path)==r.label_sha256
        raw_lines=(ROOT/r.label_path).read_text().splitlines()
        source=parse_labels(ROOT/r.label_path)
        mapped="\n".join("0 "+line.split(maxsplit=1)[1] for line in raw_lines)+("\n" if raw_lines else "")
        name=Path(r.label_path).name
        mp=OUT/"a1_mapped_labels"/name
        mp.write_text(mapped,encoding="utf-8")
        check=parse_labels(mp)
        assert len(check)==len(source) and all(p["points"]==c["points"] for p,c in zip(source,check))
        proposed,changes=propose_duplicates(source) if q.loc[r.image_path,"high_iou_pairs_over_80pct"]>0 else (source,[])
        cleaned=[]
        for p in proposed:
            points=[]
            for xy in p["points"]:
                if not points or xy!=points[-1]: points.append(xy)
            if len(points)>1 and points[0]==points[-1]: points.pop()
            if points!=p["points"]:
                changes.append({"type":"PROPOSE_REMOVE_REPEATED_VERTEX","source_line":p["source_line"],
                                "keep_source_line":p["source_line"],"human_approval_required":True})
            cleaned.append({**p,"points":points})
        proposed=cleaned
        geometry_issues=[]
        try: validate_polygons(proposed)
        except ValueError as exc: geometry_issues.append(str(exc))
        pp=OUT/"a1_proposed_labels"/name
        pp.write_text(polygon_text(proposed,raw_lines),encoding="utf-8")
        review=q.loc[r.image_path]
        issues=str(review.priority_reasons)+"; "+str(review.agent_visual_notes if pd.notna(review.agent_visual_notes) else "")+"; "+"; ".join(geometry_issues)
        original=ROOT/r.image_path
        entry={"id":"A1_"+r.image_sha256[:16],"track":"A1","image_id":Path(r.image_path).name,
               "source_path":r.image_path,"source_label_path":r.label_path,"source_sha256":r.image_sha256,
               "source_label_sha256":r.label_sha256,"split":r.split,"reserved_group_split":r.reserved_group_split,
               "split_group_id":r.split_group_id,"source_group_id":r.source_group_id,
               "source_polygons":source,"proposed_polygons":proposed,"changes":changes,
               "image_url":"../../"+r.image_path,"width":640,"height":640,
               "issues":issues,"rank":int(review.review_rank),"policy_hash":object_hash(POLICY),
               "mapped_label_path":mp.relative_to(OUT).as_posix(),"proposed_label_path":pp.relative_to(OUT).as_posix(),
               "proposed_label_sha256":sha(pp),"checks_required":CHECKS["A1"],
               "hard_hold":r.split not in ("train","validation","test")}
        entry["proposal_hash"]=object_hash(entry)
        entries.append(entry)
        rows.append({**r._asdict(),"mapped_label_path":entry["mapped_label_path"],"mapped_label_sha256":sha(mp),
                     "proposed_label_path":entry["proposed_label_path"],"proposed_label_sha256":sha(pp),
                     "mapping_geometry_unchanged":True,"proposed_removed_instances":len(source)-len(proposed),
                     "proposal_geometry_issues":"|".join(geometry_issues),
                     "review_status":"PENDING_HUMAN" if not entry["hard_hold"] else "PRESERVED_HOLD_OR_EXCLUSION",
                     "training_eligible":False,"metric_eligible":False,"policy_version":POLICY["version"],
                     "review_id":entry["id"],"proposal_hash":entry["proposal_hash"],"issues":issues})
        for p in source:
            lineage.append(dict(image_path=r.image_path,source_line=p["source_line"],source_class=p["source_class"],target_class=0,
                                coordinate_sha256=object_hash(p["points"]),source_label_sha256=r.label_sha256,
                                retained_in_proposal=any(x["source_line"]==p["source_line"] for x in proposed)))
        proposals.extend(dict(image_path=r.image_path,split=r.split,**c) for c in changes)
    csv("a1_working_manifest.csv",pd.DataFrame(rows))
    csv("a1_instance_lineage.csv",pd.DataFrame(lineage))
    csv("a1_proposed_corrections.csv",pd.DataFrame(proposals,columns=["image_path","split","type","source_line","keep_source_line","raster_iou","human_approval_required"]))
    write_json(OUT/"a1_review_items.json",sorted(entries,key=lambda x:x["rank"]))


def compare_image(image,v1box,v2result,identity):
    canvas=Image.new("RGB",(1536,550),"white")
    original=image.copy(); original.thumbnail((512,512)); canvas.paste(original,(0,38))
    draw=ImageDraw.Draw(canvas)
    draw.text((8,8),f"{identity} | development source",font=FONT,fill="black")
    for x,title,box in [(512,"v1 proposed crop",v1box),(1024,"v2 proposed crop",v2result["crop_bbox"])]:
        draw.text((x+8,8),title,font=FONT,fill="black")
        if box:
            crop,_=letterbox_crop(image,box)
            canvas.paste(crop,(x,38))
        else: draw.text((x+20,150),"ABSTAIN",font=FONT,fill="red")
    return canvas


def build_a2(sample_only):
    (OUT/"a2_context").mkdir(exist_ok=True)
    (OUT/"a2_candidate_crops").mkdir(exist_ok=True)
    (OUT/"a2_comparison").mkdir(exist_ok=True)
    a=pd.read_csv(FROZEN/"a2_manifest.csv")
    dev=a[a.split.isin(["train","validation"])].copy()
    old=pd.read_csv(QA/"a2_roi_candidates.csv").set_index("L_ID")
    observed=pd.read_csv(QA/"a2_visual_findings.csv").set_index("L_ID")
    selected=set(observed.index)
    if sample_only: dev=dev[dev.L_ID.isin(selected)]
    entries=[]; rows=[]
    with zipfile.ZipFile(ROOT/"data/Single Larvae data.zip") as z:
        for count,r in enumerate(dev.itertuples(),1):
            roi.require_development_split(r.split)
            payload=z.read(r.archive_member)
            assert hashlib.sha256(payload).hexdigest()==r.image_sha256
            with Image.open(io.BytesIO(payload)) as src:
                src=src.convert("RGB")
                result=roi.propose_roi(src)
                reasons=[]
                prior=str(observed.loc[r.L_ID,"agent_visual_status"]) if r.L_ID in observed.index else "NOT_VISUALLY_REVIEWED"
                visual=VISUAL_V2.get(r.L_ID,"NO_OBVIOUS_DEFECT_IN_TRIAGE" if r.L_ID in selected else "NOT_VISUALLY_REVIEWED")
                confirmed_hold=visual in ["CROP_TRUNCATES_BODY","WRONG_OBJECT_STAIN","SOURCE_TRUNCATED","RULER_RETAINED"]
                if visual not in ["NO_OBVIOUS_DEFECT_IN_TRIAGE","NOT_VISUALLY_REVIEWED"]:
                    reasons.append("AGENT_VISUAL_"+visual)
                if prior=="SOURCE_TRUNCATED":
                    reasons.append("PRIOR_VISUALLY_OBSERVED_SOURCE_TRUNCATION")
                if result["source_edge_contact"]: reasons.append("POSSIBLE_SOURCE_TRUNCATION")
                if result["shortcut_suspected"]: reasons.append("SHORTCUT_SCREEN_FLAG")
                if not result["roi_found"]: reasons.append("NO_CANDIDATE")
                context=src.copy(); context.thumbnail((1014,1014))
                context_path=OUT/"a2_context"/f"{r.L_ID:04}.jpg"
                context.save(context_path,quality=94)
                crop_path=OUT/"a2_candidate_crops"/f"{r.L_ID:04}.png"
                transform={}; crop_sha=""; crop_pixel_sha=""
                if result["roi_found"]:
                    crop,transform=letterbox_crop(src,result["crop_bbox"])
                    crop.save(crop_path)
                    crop_sha=sha(crop_path)
                    crop_pixel_sha=hashlib.sha256(crop.tobytes()).hexdigest()
                if r.L_ID in selected:
                    comparison=compare_image(src,json.loads(old.loc[r.L_ID,"crop_bbox"]),result,f"ID {r.L_ID:04} {r.split}")
                    comparison.save(OUT/"a2_comparison"/f"{r.L_ID:04}.jpg",quality=94)
                entry={"id":f"A2_{r.L_ID:04}","track":"A2","image_id":f"{r.L_ID:04}","L_ID":r.L_ID,
                       "source_sha256":r.image_sha256,"archive_path":r.archive_path,"archive_member":r.archive_member,
                       "split":r.split,"reserved_group_split":r.reserved_group_split,"split_group_id":r.split_group_id,
                       "width":r.width,"height":r.height,"crop_bbox":result["crop_bbox"],
                       "image_url":context_path.relative_to(OUT).as_posix(),"context_sha256":sha(context_path),
                       "crop_url":crop_path.relative_to(OUT).as_posix() if crop_sha else "",
                       "crop_sha256":crop_sha,"crop_pixel_sha256":crop_pixel_sha,
                       "issues":"; ".join(reasons)+"; prior QA: "+prior+"; v2 agent triage: "+visual,
                       "policy_hash":object_hash(POLICY),"checks_required":CHECKS["A2"],
                       "hard_hold":confirmed_hold or prior=="SOURCE_TRUNCATED" or result["source_edge_contact"] or not result["roi_found"],
                       "method_version":roi.VERSION,"config_hash":object_hash(roi.CONFIG),"transform":transform}
                entry["proposal_hash"]=object_hash(entry)
                entries.append(entry)
                rows.append({"L_ID":r.L_ID,"image_sha256":r.image_sha256,"split":r.split,"reserved_group_split":r.reserved_group_split,
                             "split_group_id":r.split_group_id,"Batch_ID":r.Batch_ID,"measured_weight_g":r.Weight,
                             "crop_bbox":json.dumps(result["crop_bbox"]),"crop_sha256":crop_sha,"crop_pixel_sha256":crop_pixel_sha,
                             "crop_path":entry["crop_url"],"source_edge_contact":result["source_edge_contact"],
                             "shortcut_suspected":result["shortcut_suspected"],"straight_dark_lines":result["straight_dark_lines"],
                             "candidate_count":len(result["candidates"]),"roi_found":result["roi_found"],
                             "status":"HOLD" if reasons else "PENDING_HUMAN_REVIEW","hold_reasons":"|".join(reasons),
                             "prior_visual_status":prior,"v2_agent_visual_status":visual,"human_approved":False,"training_eligible":False,
                             "review_id":entry["id"],"proposal_hash":entry["proposal_hash"],"hard_hold":entry["hard_hold"]})
            if count%200==0: print(f"A2 v2: {count}/{len(dev)} development images",flush=True)
    stem="a2_subset" if sample_only else "a2_working"
    csv(stem+"_manifest.csv",pd.DataFrame(rows))
    write_json(OUT/(stem+"_review_items.json"),entries)
    sample_rows=[r for r in rows if r["L_ID"] in selected]
    # Contact sheets compare v1/v2 on the exact earlier 43-image review subset.
    for start in range(0,len(sample_rows),4):
        sheet=Image.new("RGB",(1536,4*325),"#eeeeee")
        for i,r in enumerate(sample_rows[start:start+4]):
            with Image.open(OUT/"a2_comparison"/f"{r['L_ID']:04}.jpg") as im:
                im.thumbnail((900,325)); sheet.paste(im,(0,i*325))
            d=ImageDraw.Draw(sheet)
            d.text((920,i*325+40),f"ID {r['L_ID']:04} {r['split']}\nPrior: {r['prior_visual_status']}\nV2 screen: {r['status']}\n{r['hold_reasons']}",font=FONT,fill="black")
        sheet.save(OUT/"a2_comparison"/f"sheet_{start//4+1:02}.jpg",quality=94)
    print(f"A2 proposals built: {len(rows)}, prior-review comparisons: {len(sample_rows)}",flush=True)


def summarize(values):
    a=pd.Series(values).dropna()
    return {"n":len(a),"min":float(a.min()) if len(a) else None,"max":float(a.max()) if len(a) else None,
            "mean":float(a.mean()) if len(a) else None,"median":float(a.median()) if len(a) else None}


def prepare():
    OUT.mkdir(exist_ok=True,parents=True)
    assert not (OUT/"PACKAGE_RECEIPT.json").exists(),"Completed working version; do not overwrite"
    write_json(OUT/"input_integrity.json",inputs(full=True))
    write_json(OUT/"annotation_policy.json",POLICY)
    write_json(OUT/"class_mapping.json",{"source_to_target":POLICY["source_to_target"],"target_names":["visible_bsf_larva"],
        "authorization":POLICY["authorization"],"biological_equivalence_verified":False,"geometry_change_from_mapping":False})
    write_json(OUT/"a2_roi_config.json",{"version":roi.VERSION,"parameters":roi.CONFIG,"input_features":"pixels_only"})
    print("Integrity verified. Mapping A1 instances and preparing unapproved proposals...",flush=True)
    build_a1()
    build_a2(sample_only=True)


def verify_package(full=False):
    inputs(full=full)
    receipt=read_json(OUT/"PACKAGE_RECEIPT.json")
    for name,h in receipt["outputs"].items(): assert sha(OUT/name)==h,name
    for name,h in receipt["code"].items(): assert sha(ROOT/name)==h,name
    assert receipt["input_freeze_sha256"]==sha(FROZEN/"FREEZE.json")
    return receipt


def validate_decision(decision,entry):
    if decision.get("reviewer_kind")!="human" or not str(decision.get("reviewer","")).strip():
        raise ValueError("Recorded human reviewer required")
    stamp=decision.get("reviewed_at","")
    if not stamp or datetime.fromisoformat(stamp.replace("Z","+00:00")).tzinfo is None:
        raise ValueError("Review timestamp with timezone required")
    for key in ["id","proposal_hash","policy_hash","source_sha256","split"]:
        if decision.get(key)!=entry[key]: raise ValueError("Review binding mismatch: "+key)
    if decision.get("decision") not in ["approve","reject","needs_revision"]:
        raise ValueError("Unsupported decision")
    if decision["decision"]!="approve": return
    if entry["hard_hold"]: raise ValueError("Hard-held image cannot be approved in this version")
    if not all(decision.get("checks",{}).get(k) is True for k in entry["checks_required"]):
        raise ValueError("All acceptance checks require explicit human confirmation")
    if entry["track"]=="A1":
        polys=decision.get("polygons")
        if not polys: raise ValueError("No empty-negative approval under current positive-image policy")
        validate_polygons(polys,enforce_visibility=True)
        original={p["source_line"]:p for p in entry["source_polygons"]}
        for p in polys:
            if p.get("source_line") is not None and p["source_line"] not in original:
                raise ValueError("Unknown original instance lineage")
            if p.get("source_line") is not None and p.get("source_class")!=original[p["source_line"]]["source_class"]:
                raise ValueError("Original source class lineage changed")
            if p.get("source_line") is None and p.get("source_class") is not None:
                raise ValueError("New instance cannot invent a source class")
    else:
        if decision.get("crop_sha256")!=entry["crop_sha256"] or decision.get("crop_bbox")!=entry["crop_bbox"]:
            raise ValueError("Crop changed after displayed proposal; regenerate/review a new version")


def import_reviews(path):
    verify_package(full=False)
    review=read_json(path)
    if review.get("package_hash")!=sha(OUT/"review_items.json"):
        raise ValueError("Wrong review package version")
    items={r["id"]:r for r in read_json(OUT/"review_items.json")}
    decisions=review.get("decisions",[])
    if not decisions or len({x.get("id") for x in decisions})!=len(decisions): raise ValueError("Empty/duplicate decisions")
    for decision in decisions:
        if decision.get("id") not in items: raise ValueError("Unknown review image")
        validate_decision(decision,items[decision["id"]])
    # Validate the whole input before creating the append-only snapshot.
    snapshot=OUT/"review_snapshots"/sha(path)[:16]
    if snapshot.exists(): raise FileExistsError("This review file was already imported")
    snapshot.mkdir(parents=True)
    (snapshot/"labels").mkdir(); (snapshot/"crops").mkdir()
    shutil.copyfile(path,snapshot/"human_decisions.json")
    accepted=[]; all_decisions=[]
    metadata=pd.read_csv(FROZEN/"a2_manifest.csv").set_index("L_ID")
    with zipfile.ZipFile(ROOT/"data/Single Larvae data.zip") as z:
        for d in decisions:
            e=items[d["id"]]
            all_decisions.append(dict(id=e["id"],track=e["track"],split=e["split"],reviewer=d["reviewer"],
                                      decision=d["decision"],reviewed_at=d["reviewed_at"]))
            if d["decision"]!="approve": continue
            if e["track"]=="A1":
                assert sha(ROOT/e["source_path"])==e["source_sha256"]
                assert sha(ROOT/e["source_label_path"])==e["source_label_sha256"]
                target=snapshot/"labels"/(e["id"]+".txt")
                raw=(ROOT/e["source_label_path"]).read_text().splitlines()
                target.write_text(polygon_text(d["polygons"],raw),encoding="utf-8")
            else:
                payload=z.read(e["archive_member"])
                assert hashlib.sha256(payload).hexdigest()==e["source_sha256"]
                with Image.open(io.BytesIO(payload)) as im:
                    crop,_=letterbox_crop(im,e["crop_bbox"])
                    assert hashlib.sha256(crop.tobytes()).hexdigest()==e["crop_pixel_sha256"]
                assert sha(OUT/e["crop_url"])==e["crop_sha256"]
                target=snapshot/"crops"/(e["id"]+".png")
                shutil.copyfile(OUT/e["crop_url"],target)
            accepted.append(dict(id=e["id"],track=e["track"],split=e["split"],reserved_group_split=e["reserved_group_split"],
                image_path=e.get("source_path",""),archive_path=e.get("archive_path",""),archive_member=e.get("archive_member",""),
                L_ID=e.get("L_ID",""),measured_weight_g=float(metadata.loc[e["L_ID"],"Weight"]) if e["track"]=="A2" else "",
                annotation_or_crop_version=POLICY["version"] if e["track"]=="A1" else e["method_version"],
                split_group_id=e["split_group_id"],source_sha256=e["source_sha256"],source_label_sha256=e.get("source_label_sha256",""),
                artifact_path=target.relative_to(snapshot).as_posix(),artifact_sha256=sha(target),
                reviewer=d["reviewer"],reviewed_at=d["reviewed_at"],decision="approve",policy_hash=e["policy_hash"],
                training_eligible=e["split"]=="train",metric_eligible=e["split"] in ["validation","test"]))
    pd.DataFrame(all_decisions).to_csv(snapshot/"decisions_manifest.csv",index=False)
    decision_map={d["id"]:d["decision"] for d in decisions}
    accepted_ids={r["id"] for r in accepted}
    pd.DataFrame([dict(id=e["id"],track=e["track"],split=e["split"],reserved_group_split=e["reserved_group_split"],
                      split_group_id=e["split_group_id"],source_sha256=e["source_sha256"],
                      status=decision_map.get(e["id"],"HARD_HOLD" if e["hard_hold"] else "PENDING_HUMAN"),
                      issues=e["issues"],training_eligible=e["id"] in accepted_ids and e["split"]=="train")
                  for e in items.values()]).to_csv(snapshot/"eligibility_manifest.csv",index=False)
    approved_a2={int(r["L_ID"]) for r in accepted if r["track"]=="A2"}
    coverage=[]
    dev=metadata[metadata.split.isin(["train","validation"])]
    for (split,batch),group in dev.groupby(["split","Batch_ID"]):
        weights=group[group.index.isin(approved_a2)].Weight
        coverage.append(dict(split=split,batch=batch,available_n=len(group),approved_fraction=len(weights)/len(group),**summarize(weights)))
    pd.DataFrame(coverage).to_csv(snapshot/"a2_approved_coverage_by_batch_weight.csv",index=False)
    shutil.copyfile(OUT/"annotation_policy.json",snapshot/"annotation_policy.json")
    shutil.copyfile(OUT/"a2_roi_config.json",snapshot/"a2_roi_config.json")
    if accepted:
        pd.DataFrame(accepted).to_csv(snapshot/"approved_working_manifest.csv",index=False)
        write_json(snapshot/"FREEZE.json",{"status":"HUMAN_ACCEPTED_SUBSET_ONLY","accepted":len(accepted),
            "review_package_receipt_sha256":sha(OUT/"PACKAGE_RECEIPT.json"),
            "review_file_sha256":sha(path),"input_freeze_sha256":sha(FROZEN/"FREEZE.json"),
            "files":{p.relative_to(snapshot).as_posix():sha(p) for p in sorted(snapshot.rglob("*")) if p.is_file()}})
    print(json.dumps({"snapshot":str(snapshot),"human_accepted":len(accepted),"frozen":bool(accepted)}),flush=True)


def review_assets():
    assert not (OUT/"PACKAGE_RECEIPT.json").exists()
    items=read_json(OUT/"a1_review_items.json")+read_json(OUT/"a2_working_review_items.json")
    assert len({e["id"] for e in items})==len(items)
    write_json(OUT/"review_items.json",items)
    (OUT/"review_data.js").write_text("window.REVIEW_DATA="+json.dumps({"package_hash":sha(OUT/"review_items.json"),"items":items},ensure_ascii=False)+";\n",encoding="utf-8")
    shutil.copyfile(ROOT/"model_a_review.html",OUT/"review.html")
    shutil.copyfile(ROOT/"model_a_review.js",OUT/"review.js")
    return items


def package():
    assert not (OUT/"PACKAGE_RECEIPT.json").exists(),"Use a new version instead of replacing a completed package"
    inputs()
    a1=pd.read_csv(OUT/"a1_working_manifest.csv")
    a2=pd.read_csv(OUT/"a2_working_manifest.csv")
    original=pd.read_csv(FROZEN/"a2_manifest.csv")
    assert len(a1)==321 and len(a2)==1114 and set(a2.split)<={"train","validation"}
    items=review_assets()
    rank={e["id"]:e["rank"] for e in items if e["track"]=="A1"}
    queue=a1.assign(review_rank=a1.review_id.map(rank)).sort_values("review_rank")
    csv("a1_unresolved_review_queue.csv",queue)
    # Every reservation appears in this ledger; test pixels are not processed.
    ledger=original[["L_ID","image_sha256","split","reserved_group_split","split_group_id","Batch_ID","eligibility_status"]].merge(
        a2[["L_ID","status","hold_reasons","crop_path","crop_sha256","hard_hold"]],on="L_ID",how="left",validate="one_to_one")
    ledger.loc[ledger.split=="test","status"]="RESERVED_TEST_NOT_PROCESSED"
    ledger.loc[ledger.split=="quarantine","status"]="FROZEN_QUARANTINE_NOT_PROCESSED"
    ledger["human_approved"]=False; ledger["training_eligible"]=False
    csv("a2_eligibility_ledger.csv",ledger)
    csv("a2_held_excluded_or_reserved.csv",ledger[ledger.status!="PENDING_HUMAN_REVIEW"])
    csv("a2_visual_comparison.csv",a2[a2.v2_agent_visual_status!="NOT_VISUALLY_REVIEWED"])
    csv("a2_subset_manifest.csv",a2[a2.v2_agent_visual_status!="NOT_VISUALLY_REVIEWED"])
    subset_ids=set(a2.loc[a2.v2_agent_visual_status!="NOT_VISUALLY_REVIEWED","review_id"])
    write_json(OUT/"a2_subset_review_items.json",[e for e in items if e["id"] in subset_ids])
    # No empty 'approved' manifests that could be mistaken for a finished dataset.
    write_json(OUT/"approval_status.json",{"a1_human_approved":0,"a2_human_approved":0,
        "training_ready_freeze_created":False,"reason":"No recorded human image decisions provided"})
    dev=original[original.split.isin(["train","validation"])].copy()
    assert dev.length_baseline_eligible.all()
    csv("a2_baseline_population.csv",dev[["L_ID","split","reserved_group_split","split_group_id","Batch_ID","Weight","Length","Width","width_valid","image_sha256"]].rename(columns={"Weight":"measured_weight_g"}))
    coverage=[]
    for (split,batch),g in dev.groupby(["split","Batch_ID"]):
        d=a2[a2.L_ID.isin(g.L_ID)]
        for name,weights in [("available_development",g.Weight),("screen_pending_not_approved",d[d.status=="PENDING_HUMAN_REVIEW"].measured_weight_g),
                            ("held_for_review",d[d.status=="HOLD"].measured_weight_g),("human_approved",[])]:
            coverage.append(dict(split=split,batch=batch,population=name,**summarize(weights)))
    csv("a2_coverage_by_batch_weight.csv",pd.DataFrame(coverage))
    baseline={"status":"DATA_READY_NO_FIT","mean_and_length":dev.groupby("split").size().to_dict(),
              "valid_width_matched":dev[dev.width_valid].groupby("split").size().to_dict(),
              "image_approved":0,"weight_unit":"g","length_unit":"mm","width_unit":"UNKNOWN",
              "protocol":"measured weight; wet/dry unknown; no pixel calibration",
              "fair_comparison":"Mean vs Length on full development; all morphometric models on identical valid-width IDs. Image comparisons only on exact approved image IDs shared by each compared baseline. Fit all transforms on train only; preserve groups; reserve final test."}
    write_json(OUT/"baseline_readiness.json",baseline)
    write_json(OUT/"environment.json",{"python":platform.python_version(),"numpy":np.__version__,"pandas":pd.__version__,"opencv":cv2.__version__,
        "randomness":"No stochastic fitting; deterministic pixel method","training_executed":False})
    for name in ["FINALIZATION_REPORT.md","README_FINALIZATION.md"]:
        shutil.copyfile(ROOT/name,OUT/("README.md" if name.startswith("README") else name))
    stats={"a1_images":len(a1),"a1_instances":len(pd.read_csv(OUT/"a1_instance_lineage.csv")),
        "a1_split":a1.groupby("split").size().to_dict(),"a1_proposal_changes":pd.read_csv(OUT/"a1_proposed_corrections.csv").groupby("type").size().to_dict(),
        "a2_development":len(a2),"a2_roi_found":int(a2.roi_found.sum()),"a2_status":a2.status.value_counts().to_dict(),
        "a2_hard_hold":int(a2.hard_hold.sum()),"a2_edge_flags":int(a2.source_edge_contact.sum()),"a2_shortcut_flags":int(a2.shortcut_suspected.sum()),
        "a2_visual_subset":a2[a2.v2_agent_visual_status!="NOT_VISUALLY_REVIEWED"].v2_agent_visual_status.value_counts().to_dict(),
        "a1_approved":0,"a2_approved":0,"decision":"NO-GO for A1/A2 image training; baseline data ready; no fit authorized in this task"}
    write_json(OUT/"readiness_summary.json",stats)
    inputs()
    names=["finalize_model_a.py","a2_preprocessing_v2.py","model_a_review.html","model_a_review.js","FINALIZATION_REPORT.md","README_FINALIZATION.md","test_model_a_finalization.py","test_model_a_review_browser.py"]
    write_json(OUT/"PACKAGE_RECEIPT.json",{"status":"REVIEW_PACKAGE_ONLY_NOT_TRAINING_READY_FREEZE","input_freeze_sha256":sha(FROZEN/"FREEZE.json"),
        "created_at":datetime.now(timezone.utc).isoformat(),"code":{n:sha(ROOT/n) for n in names},
        "outputs":{p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob("*")) if p.is_file() and "review_snapshots" not in p.parts}})
    print(json.dumps(stats,indent=2),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=["prepare","expand","preview","package","verify","import-reviews"])
    parser.add_argument("review_file",nargs="?")
    args=parser.parse_args()
    if args.command=="prepare": prepare()
    elif args.command=="expand":
        assert not (OUT/"PACKAGE_RECEIPT.json").exists()
        inputs(); build_a2(sample_only=False)
    elif args.command=="package": package()
    elif args.command=="preview": review_assets()
    elif args.command=="verify": verify_package(full=True); print("PASS: package, raw, frozen memberships and B1 integrity")
    else:
        if not args.review_file: parser.error("Review JSON file required")
        import_reviews(Path(args.review_file))


if __name__=="__main__": main()
