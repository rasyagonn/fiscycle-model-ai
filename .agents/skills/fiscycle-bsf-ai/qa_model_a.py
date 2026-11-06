"""Versioned pretraining QA. Frozen/raw/B1 files are read-only inputs.

Commands: python -B qa_model_a.py build | finalize | verify
build generates A1 overlays and screens A2 train/validation only, without fitting.
finalize incorporates explicit agent visual triage (never a human approval).
"""
from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import platform
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

import a2_preprocessing as prep

ROOT = Path(__file__).resolve().parent
FROZEN = ROOT / "hasil/model_a_preparation_v1"
OUT = ROOT / "hasil/model_a_pretraining_qa_v1"
FONT = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 17)
SMALL = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 13)


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8*1024*1024), b""):
            result.update(block)
    return result.hexdigest()


def json_write(name, obj):
    (OUT/name).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def save_csv(name, obj):
    obj.to_csv(OUT/name, index=False, lineterminator="\n")


def verify_frozen(full=False):
    freeze = json.loads((FROZEN/"FREEZE.json").read_text())
    assert sha(ROOT/"prepare_model_a.py") == freeze["script_sha256"]
    for name, expected in freeze["outputs"].items():
        assert sha(FROZEN/name) == expected, name
    for name, expected in json.loads((FROZEN/"protected_integrity.json").read_text()).items():
        assert sha(ROOT/name) == expected, name
    if full:
        for r in pd.read_csv(FROZEN/"source_integrity.csv").itertuples():
            assert sha(ROOT/r.path) == r.sha256, r.path
    return {"frozen_files_verified": len(freeze["outputs"]), "raw_sha256_verified": full,
            "b1_and_prior_audit_verified": True, "freeze_sha256": sha(FROZEN/"FREEZE.json"),
            "old_queue_equals_manifest": sha(FROZEN/"a1_review_queue.csv") == sha(FROZEN/"a1_manifest.csv")}


def polygons(path):
    records = []
    for index, line in enumerate(path.read_text().splitlines(), 1):
        values = line.split()
        cls = int(values[0])
        points = np.array(values[1:], dtype=float).reshape(-1, 2)
        assert cls in (0, 1) and len(points) >= 3 and np.isfinite(points).all()
        assert ((points >= 0) & (points <= 1)).all()
        records.append((index, cls, points))
    return records


def geometry(records):
    masks, bboxes, border, tiny, coarse = [], [], 0, 0, 0
    for _, _, points in records:
        pixel = np.round(points * 639).astype(np.int32)
        mask = np.zeros((640, 640), np.uint8)
        cv2.fillPoly(mask, [pixel], 1)
        masks.append(mask)
        bboxes.append(cv2.boundingRect(pixel))
        border += int(((points <= 2/640) | (points >= 1-2/640)).any())
        tiny += int(cv2.contourArea(pixel) < 64)
        coarse += int(len(points) <= 5)
    overlap, duplicate = 0, 0
    for i in range(len(masks)):
        x, y, w, h = bboxes[i]
        for j in range(i):
            xx, yy, ww, hh = bboxes[j]
            x0, y0, x1, y1 = max(x, xx), max(y, yy), min(x+w, xx+ww), min(y+h, yy+hh)
            if x0 >= x1 or y0 >= y1:
                continue
            intersection = int(np.count_nonzero(masks[i][y0:y1,x0:x1] & masks[j][y0:y1,x0:x1]))
            amin, amax = sorted([int(masks[i].sum()), int(masks[j].sum())])
            overlap += int(intersection / max(amin, 1) > .05)
            duplicate += int(intersection / max(amin+amax-intersection, 1) > .8)
    return dict(border_touch_polygons=border, tiny_polygons_under_64px=tiny,
                coarse_polygons_5_vertices_or_less=coarse, overlap_pairs_over_5pct=overlap,
                high_iou_pairs_over_80pct=duplicate)


def a1_overlay(image, records, row, filename):
    canvas = Image.new("RGB", (1280, 700), "white")
    canvas.paste(image, (0, 60))
    overlay = image.copy()
    draw = ImageDraw.Draw(overlay)
    for index, cls, points in records:
        coords = [tuple(x) for x in (points*639)]
        colour = (0, 190, 255) if cls == 0 else (255, 125, 0)
        draw.line(coords+[coords[0]], fill=colour, width=2)
        cx, cy = coords[0]
        draw.text((cx, cy), str(index), fill=colour, font=SMALL, stroke_width=1, stroke_fill="black")
    canvas.paste(overlay, (640, 60))
    d = ImageDraw.Draw(canvas)
    d.text((8, 3), f"{row.image_path.split('/')[-1]}", fill="black", font=SMALL)
    d.text((8, 25), f"RAW | split={row.split}; reserved={row.reserved_group_split}; {row.total_instances} polygons", fill="black", font=FONT)
    d.text((650, 25), "ANNOTATIONS | cyan=class_0; orange=class_1; numbers=line IDs", fill="black", font=SMALL)
    canvas.save(OUT/filename, quality=94)


def contact_sheets(items, stem, columns=2, per_page=4):
    paths = []
    for start in range(0, len(items), per_page):
        batch = items[start:start+per_page]
        canvas = Image.new("RGB", (columns*640, ((len(batch)+columns-1)//columns)*380), "#eeeeee")
        for index, (label, path) in enumerate(batch):
            with Image.open(OUT/path) as im:
                tile = im.copy()
                tile.thumbnail((640, 350))
                x, y = index % columns * 640, index // columns * 380
                canvas.paste(tile, (x, y+28))
                ImageDraw.Draw(canvas).text((x+5, y+3), label, fill="black", font=FONT)
        name = f"{stem}_{start//per_page+1:02}.jpg"
        canvas.save(OUT/name, quality=94)
        paths.append(name)
    return paths


def build_a1(a):
    (OUT/"a1_overlays").mkdir(exist_ok=True)
    rows = []
    for r in a.itertuples():
        assert sha(ROOT/r.image_path) == r.image_sha256 and sha(ROOT/r.label_path) == r.label_sha256
        records = polygons(ROOT/r.label_path)
        stats = geometry(records)
        suspected = "FLAG_POSSIBLE_MISSED_ANNOTATIONS" in r.eligibility_status
        reasons = []
        if r.reserved_group_split == "test":
            tier = 0; reasons.append("RESERVED_TEST_LABEL_REVIEW_ONLY")
        elif r.reserved_group_split == "validation":
            tier = 1; reasons.append("VALIDATION_LABEL_REVIEW")
        elif r.split == "excluded":
            tier = 2; reasons.append("KNOWN_EMPTY_POSITIVE_KEEP_EXCLUDED")
        elif suspected:
            tier = 3
        elif r.total_instances >= 30:
            tier = 4
        elif stats["overlap_pairs_over_5pct"] or stats["border_touch_polygons"]:
            tier = 5
        else:
            tier = 6
        if suspected: reasons.append("PRIOR_VISUAL_MISSED_ANNOTATION_SUSPECT")
        if r.total_instances >= 30: reasons.append("DENSE_SCENE")
        if stats["border_touch_polygons"]: reasons.append("BORDER_TRUNCATION_REVIEW")
        if stats["overlap_pairs_over_5pct"]: reasons.append("OVERLAP_OR_OCCLUSION_POLICY_REVIEW")
        if stats["coarse_polygons_5_vertices_or_less"]: reasons.append("COARSE_CONTOUR_REVIEW")
        if stats["tiny_polygons_under_64px"]: reasons.append("TINY_POLYGON_REVIEW")
        if stats["high_iou_pairs_over_80pct"]: reasons.append("POSSIBLE_DUPLICATE_POLYGON_REVIEW")
        reasons.append("CLASS_MEANING_UNKNOWN")
        score = (40*int(suspected) + 15*int(r.total_instances >= 30) +
                 10*int(stats["border_touch_polygons"] > 0) + 10*int(stats["overlap_pairs_over_5pct"] > 0) +
                 5*int(stats["tiny_polygons_under_64px"] > 0) + 5*int(r.class_0_count > 0 and r.class_1_count > 0))
        overlay = "a1_overlays/" + Path(r.image_path).stem + ".jpg"
        with Image.open(ROOT/r.image_path) as im:
            a1_overlay(im.convert("RGB"), records, r, overlay)
        rows.append({**r._asdict(), **stats, "priority_tier": tier, "risk_score": score,
                     "priority_reasons": "|".join(reasons), "overlay_path": overlay,
                     "review_status": "KEEP_EXCLUDED" if r.split == "excluded" else "HUMAN_REVIEW_PENDING",
                     "next_action": "KEEP_EXCLUDED_DO_NOT_TREAT_AS_NEGATIVE" if r.split == "excluded" else
                         "CHECK_ALL_VISIBLE_OBJECTS_BORDERS_OCCLUSIONS_POLYGONS_AND_CLASS_SCOPE",
                     "human_reviewer": "", "human_reviewed_at": "", "human_decision": "",
                     "human_missing_instances": "", "human_truncation_policy": "",
                     "human_overlap_policy": "", "approved_working_label_sha256": "",
                     "qa_training_approved": False, "qa_metric_approved": False})
    queue = pd.DataFrame(rows).sort_values(["priority_tier", "risk_score", "is_source_representative", "total_instances", "image_path"],
                                          ascending=[True, False, False, False, True]).reset_index(drop=True)
    queue.insert(0, "review_rank", np.arange(1,len(queue)+1))
    save_csv("a1_prioritized_review_queue.csv", queue)
    selection = []
    for split in ["test", "validation", "train"]:
        reps = queue[queue.split.eq(split) & queue.is_source_representative]
        # High-risk + evenly spaced representatives, independent of model predictions.
        indices = list(reps.head(6).index) + list(reps.iloc[np.linspace(0,len(reps)-1,6,dtype=int)].index)
        selection.extend(dict.fromkeys(indices))
    selection += list(queue[queue.split.eq("excluded")].index)
    selection += list(queue[queue.split.eq("quarantine") & queue.is_source_representative].index)
    sample = queue.loc[list(dict.fromkeys(selection))].copy()
    save_csv("a1_visual_triage_sample.csv", sample)
    contact_sheets([(f"rank {r.review_rank} | {r.split} | n={r.total_instances}", r.overlay_path)
                    for r in sample.itertuples()], "a1_contact")
    links = "\n".join(f'<li>#{r.review_rank} {html.escape(r.split)} — {html.escape(r.priority_reasons)}<br>'
                       f'<a href="{html.escape(r.overlay_path)}">{html.escape(Path(r.image_path).name)}</a></li>'
                       for r in queue.itertuples())
    (OUT/"a1_review_index.html").write_text('<!doctype html><meta charset="utf-8"><title>A1 annotation review</title>'
        '<h1>A1 annotation review — no model predictions</h1><p>Cyan: class_0; orange: class_1. Both meanings UNKNOWN. '
        'Review is not training approval. Open each image at full size; record human decisions in a versioned CSV copy.</p><ol>'+links+'</ol>', encoding="utf-8")
    return queue


def sample_a2(a):
    development = a[a.split.isin(["train", "validation"])].copy()
    ids = set()
    for _, g in development.groupby("Batch_ID"):
        g = g.sort_values("L_ID")
        ids.update(g.iloc[np.linspace(0,len(g)-1,3,dtype=int)].L_ID.tolist())
    for i in [1, 200, 600]:
        if i in set(development.L_ID): ids.add(i)
    return development, ids


def a2_preview(image, result, r, filename):
    canvas = Image.new("RGB", (1200, 560), "white")
    original = image.copy()
    original.thumbnail((680, 510))
    canvas.paste(original, (0, 45))
    d = ImageDraw.Draw(canvas)
    d.text((6, 5), f"ID {r.L_ID:04} | {r.split} | {r.Batch_ID} | ORIGINAL + proposed ROI", font=FONT, fill="black")
    d.text((700, 5), "UNAPPROVED ROI + letterbox", font=FONT, fill="black")
    if result["roi_found"]:
        ratio = original.width / image.width
        x0,y0,x1,y1 = result["crop_bbox"]
        d.rectangle((x0*ratio,45+y0*ratio,x1*ratio,45+y1*ratio), outline="red", width=3)
        crop, transform = prep.letterbox_crop(image, result["crop_bbox"])
        canvas.paste(crop, (688,45))
    else:
        transform = {}
        d.text((700,100), "ABSTAIN: no ROI", font=FONT, fill="red")
    canvas.save(OUT/filename, quality=95)
    return transform


def build_a2(a):
    (OUT/"a2_previews").mkdir(exist_ok=True)
    development, preview_ids = sample_a2(a)
    rows = []
    with zipfile.ZipFile(ROOT/"data/Single Larvae data.zip") as z:
        for count, r in enumerate(development.itertuples(), 1):
            prep.require_development_split(r.split)
            payload = z.read(r.archive_member)
            assert hashlib.sha256(payload).hexdigest() == r.image_sha256
            with Image.open(io.BytesIO(payload)) as im:
                im = im.convert("RGB")
                result = prep.propose_roi(im)
                record = dict(L_ID=r.L_ID, split=r.split, reserved_group_split=r.reserved_group_split,
                              split_group_id=r.split_group_id, Batch_ID=r.Batch_ID, EXIF_date=r.EXIF_date,
                              archive_path=r.archive_path, archive_member=r.archive_member,
                              image_sha256=r.image_sha256, decoded_pixel_sha256=r.pixel_sha256,
                              width=r.width, height=r.height, **result)
                record["body_bbox"] = json.dumps(result["body_bbox"])
                record["crop_bbox"] = json.dumps(result["crop_bbox"])
                record["preview_path"] = ""
                if r.L_ID in preview_ids:
                    filename = f"a2_previews/{r.L_ID:04}.jpg"
                    record.update(a2_preview(im, result, r, filename))
                    record["preview_path"] = filename
                rows.append(record)
            if count % 200 == 0:
                print(f"A2 QA candidates {count}/{len(development)} (train/validation only)", flush=True)
    frame = pd.DataFrame(rows)
    save_csv("a2_roi_candidates.csv", frame)
    sample = frame[frame.preview_path.ne("")].copy()
    save_csv("a2_preview_manifest.csv", sample)
    contact_sheets([(f"ID {r.L_ID:04} | {r.split} | {r.Batch_ID}",r.preview_path)
                    for r in sample.itertuples()], "a2_contact")
    json_write("a2_preprocessing_config.json", {"version": prep.VERSION, "parameters": prep.CONFIG,
        "scope": "Development splits only; no fitting; all ROI candidates need human approval",
        "sample_selection": "3 evenly spaced IDs per development batch + previously documented dev IDs 1,200,600; no Weight/Sex selection",
        "config_sha256": hashlib.sha256(json.dumps(prep.CONFIG,sort_keys=True).encode()).hexdigest()})
    # A blank working-review template is intentionally not an approval.
    template = sample[["L_ID","split","image_sha256","decoded_pixel_sha256","crop_bbox"]].copy()
    for col in ["reviewer_kind","reviewer_name","reviewed_at","whole_larva_visible","no_written_markings","background_acceptable","decision"]:
        template[col] = ""
    save_csv("a2_human_review_template.csv", template)
    return frame


def verify_outputs():
    verify_frozen(full=True)
    frozen1 = pd.read_csv(FROZEN/"a1_manifest.csv").set_index("image_path")
    queue = pd.read_csv(OUT/"a1_prioritized_review_queue.csv").set_index("image_path")
    assert set(queue.index) == set(frozen1.index) and queue.review_rank.is_unique
    for col in ["split","reserved_group_split","split_group_id","label_sha256","image_sha256"]:
        pd.testing.assert_series_equal(queue[col].sort_index(), frozen1[col].sort_index())
    assert not queue.qa_training_approved.any() and not queue.qa_metric_approved.any()
    test_ranks = queue.loc[queue.reserved_group_split.eq("test"),"review_rank"]
    val_ranks = queue.loc[queue.reserved_group_split.eq("validation"),"review_rank"]
    assert test_ranks.max() < val_ranks.min()
    for r in queue.itertuples():
        assert (OUT/r.overlay_path).is_file()
    a2 = pd.read_csv(OUT/"a2_roi_candidates.csv")
    frozen2 = pd.read_csv(FROZEN/"a2_manifest.csv").set_index("L_ID")
    expected = frozen2[frozen2.split.isin(["train","validation"])]
    assert set(a2.L_ID) == set(expected.index) and len(a2) == 1114
    for col in ["split","reserved_group_split","split_group_id","image_sha256"]:
        pd.testing.assert_series_equal(a2.set_index("L_ID")[col].sort_index(), expected[col].sort_index())
    assert not a2.training_approved.any()
    for r in a2[a2.roi_found].itertuples():
        x0,y0,x1,y1 = json.loads(r.crop_bbox)
        assert 0 <= x0 < x1 <= r.width and 0 <= y0 < y1 <= r.height
    for split in ["test","quarantine","excluded"]:
        try:
            prep.require_development_split(split)
        except ValueError:
            pass
        else:
            raise AssertionError("Test/other split not refused")
    blank = Image.new("RGB",(300,100),"white")
    assert not prep.propose_roi(blank)["roi_found"]
    boxed,t = prep.letterbox_crop(blank,[0,0,300,100])
    assert boxed.size==(512,512) and t["resized_width"]==512 and t["resized_height"]==171
    off_center = Image.new("RGB", (800,600), "white")
    draw = ImageDraw.Draw(off_center)
    draw.ellipse((30,40,200,110), fill=(150,110,60))
    draw.text((500,450), "ID 0123 F", fill="black", font=FONT)
    off_roi = prep.propose_roi(off_center)
    assert off_roi["roi_found"]
    x0,y0,x1,y1 = off_roi["crop_bbox"]
    assert x0<=30 and y0<=40 and x1>=200 and y1>=110 and x1<500
    try:
        prep.approved_crop(blank,split="train",image_sha256="x",approval={})
    except ValueError:
        pass
    else:
        raise AssertionError("Unapproved crop accepted")
    receipt = OUT/"QA_RECEIPT.json"
    if receipt.exists():
        receipt_data=json.loads(receipt.read_text())
        for name, expected_hash in receipt_data["outputs"].items():
            assert sha(OUT/name)==expected_hash, name
        for name, expected_hash in receipt_data["code_sha256"].items():
            assert sha(ROOT/name)==expected_hash, name
    print("PASS: frozen/raw/B1 integrity; memberships; prioritized queue; overlays; no A2 test processing; crop bounds; fail-closed approval",flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=["build","stress","finalize","verify"])
    args=parser.parse_args()
    if args.command=="verify":
        verify_outputs(); return
    OUT.mkdir(parents=True,exist_ok=True)
    if args.command=="finalize":
        finalize(); return
    if args.command=="stress":
        build_stress(); return
    assert not (OUT/"QA_RECEIPT.json").exists(), "Completed QA version: create a new version for changes"
    integrity=verify_frozen(full=True)
    json_write("input_integrity.json",integrity)
    a1=pd.read_csv(FROZEN/"a1_manifest.csv")
    a2=pd.read_csv(FROZEN/"a2_manifest.csv")
    print("Verified frozen/raw/B1 inputs. Building 321 A1 overlays...",flush=True)
    build_a1(a1)
    print("Building A2 development-only ROI candidates and previews...",flush=True)
    build_a2(a2)
    verify_frozen()
    print("Build complete. Inspect previews and record visual triage before finalize.",flush=True)


def build_stress():
    assert not (OUT/"QA_RECEIPT.json").exists()
    verify_frozen()
    all_rows=pd.read_csv(OUT/"a2_roi_candidates.csv")
    existing=set(pd.read_csv(OUT/"a2_preview_manifest.csv").L_ID)
    selected=[]
    for split in ["train","validation"]:
        for status in ["POSSIBLE_SOURCE_TRUNCATION","MULTIPLE_COMPONENTS_REVIEW"]:
            subset=all_rows[(all_rows.split==split) & (all_rows.automatic_status==status) & ~all_rows.L_ID.isin(existing)]
            subset=subset.sort_values(["competing_component_ratio","L_ID"],ascending=[False,True]).head(2)
            selected.extend(subset.L_ID.tolist())
    manifest=pd.read_csv(FROZEN/"a2_manifest.csv").set_index("L_ID")
    rows=[]
    with zipfile.ZipFile(ROOT/"data/Single Larvae data.zip") as z:
        for identity in selected:
            original=manifest.loc[identity]
            prep.require_development_split(original.split)
            payload=z.read(original.archive_member)
            assert hashlib.sha256(payload).hexdigest()==original.image_sha256
            with Image.open(io.BytesIO(payload)) as im:
                im=im.convert("RGB")
                result=prep.propose_roi(im)
                r=next(manifest.loc[[identity]].reset_index().itertuples())
                name=f"a2_previews/{identity:04}.jpg"
                a2_preview(im,result,r,name)
                record=all_rows[all_rows.L_ID==identity].iloc[0].to_dict()
                record["preview_path"]=name
                record["selection_reason"]="2 highest-competing flagged examples per split/status, excluding representative sample"
                rows.append(record)
    frame=pd.DataFrame(rows)
    save_csv("a2_stress_preview_manifest.csv",frame)
    contact_sheets([(f"ID {r.L_ID:04} | {r.split} | {r.automatic_status}",r.preview_path)
                    for r in frame.itertuples()],"a2_stress_contact")
    print(frame[["L_ID","split","automatic_status"]].to_string(index=False),flush=True)


def finalize():
    assert not (OUT/"QA_RECEIPT.json").exists(), "Completed QA version cannot be overwritten"
    observations=json.loads((OUT/"agent_visual_observations.json").read_text(encoding="utf-8"))
    queue=pd.read_csv(OUT/"a1_prioritized_review_queue.csv")
    selected1=pd.read_csv(OUT/"a1_visual_triage_sample.csv")
    v1=pd.DataFrame(observations["a1"]).rename(columns={"rank":"review_rank","status":"agent_visual_status","notes":"agent_visual_notes"})
    assert v1.review_rank.is_unique and set(v1.review_rank)==set(selected1.review_rank)
    queue=queue.merge(v1,on="review_rank",how="left",validate="one_to_one")
    queue["agent_visual_status"]=queue.agent_visual_status.fillna("NOT_VISUALLY_REVIEWED")
    queue["agent_visual_notes"]=queue.agent_visual_notes.fillna("")
    queue["reviewer_kind"]="AI_AGENT_TRIAGE_NOT_HUMAN_APPROVAL"
    queue["agent_correction_recommended"]=queue.agent_visual_status.eq("NEEDS_CORRECTION")
    for status,action in {
        "NEEDS_CORRECTION":"HUMAN_CORRECT_COVERAGE_OR_CONTOUR_ON_VERSIONED_WORKING_LABELS",
        "NEEDS_ADJUDICATION":"HUMAN_DECIDE_DUPLICATE_OCCLUSION_OR_VISIBILITY_POLICY",
        "NO_OBVIOUS_DEFECT_IN_TRIAGE":"HUMAN_FULL_RESOLUTION_COMPLETENESS_AND_CLASS_SCOPE_CHECK_STILL_REQUIRED",
    }.items():
        queue.loc[queue.agent_visual_status.eq(status),"next_action"]=action
    save_csv("a1_prioritized_review_queue.csv",queue)
    save_csv("a1_visual_findings.csv",queue[queue.agent_visual_status.ne("NOT_VISUALLY_REVIEWED")])
    save_csv("a1_correction_candidates.csv",queue[queue.agent_visual_status.isin(["NEEDS_CORRECTION","NEEDS_ADJUDICATION"])])
    save_csv("a1_readiness.csv",queue[["image_path","split","reserved_group_split","split_group_id",
        "agent_visual_status","agent_correction_recommended","qa_training_approved","qa_metric_approved","next_action"]])
    candidate=pd.read_csv(OUT/"a2_roi_candidates.csv")
    representative=pd.read_csv(OUT/"a2_preview_manifest.csv")
    stress=pd.read_csv(OUT/"a2_stress_preview_manifest.csv")
    previews=pd.concat([representative.assign(sample_role="representative"),stress.assign(sample_role="stress")],ignore_index=True)
    rows=[]
    for group in observations["a2"]:
        rows.extend(dict(L_ID=identity,agent_visual_status=group["status"],
                         agent_apparent_whole_body=group["apparent_whole_body"],agent_visual_notes=group["notes"])
                    for identity in group["ids"])
    v2=pd.DataFrame(rows)
    assert v2.L_ID.is_unique and set(v2.L_ID)==set(previews.L_ID)
    visual2=previews.merge(v2,on="L_ID",validate="one_to_one")
    visual2["human_approved"]=False
    save_csv("a2_visual_findings.csv",visual2)
    eligible=candidate[["L_ID","split","reserved_group_split","split_group_id","image_sha256","crop_bbox","automatic_status"]].merge(v2,on="L_ID",how="left",validate="one_to_one")
    eligible["agent_visual_status"]=eligible.agent_visual_status.fillna("NOT_VISUALLY_REVIEWED")
    eligible["training_approved"]=False
    eligible["action"]="HOLD_PENDING_HUMAN_WHOLE_BODY_AND_SHORTCUT_REVIEW"
    eligible.loc[eligible.agent_visual_status.eq("SOURCE_TRUNCATED"),"action"]="HOLD_SOURCE_TRUNCATED_CANNOT_RECONSTRUCT_BODY"
    eligible.loc[eligible.agent_visual_status.eq("WRONG_ROI_OBJECT_MISSING"),"action"]="REJECT_PROPOSAL_REVIEW_WORKING_ROI"
    save_csv("a2_crop_eligibility_working.csv",eligible)
    # Geometry/class checks are evidence, not biological relabelling.
    geometry_cols=["border_touch_polygons","tiny_polygons_under_64px","coarse_polygons_5_vertices_or_less",
                   "overlap_pairs_over_5pct","high_iou_pairs_over_80pct"]
    counts1={str(k):int(v) for k,v in queue.agent_visual_status.value_counts().items()}
    counts2={str(k):int(v) for k,v in visual2.agent_visual_status.value_counts().items()}
    flags={col:int(queue[col].gt(0).sum()) for col in geometry_cols}
    stats={"status":"RESEARCH_PROTOTYPE / NOT_FIELD_VALIDATED", "training_performed":False,
           "a1":{"images_screened":len(queue),"overlays":len(queue),"visual_triage_images":len(v1),
                 "visual_status_counts":counts1,"geometry_flagged_image_counts":flags,
                 "human_approved_train_images":0,"human_approved_metric_images":0,
                 "validation_images":61,"validation_primary_groups":1,"test_images":46,"test_primary_groups":2},
           "a2":{"development_images_screened":len(candidate),"representative_previews":len(representative),
                 "stress_previews":len(stress),"visual_status_counts":counts2,
                 "automated_status_counts":{str(k):int(v) for k,v in candidate.automatic_status.value_counts().items()},
                 "test_images_preprocessed":0,"human_approved_training_crops":0,
                 "final_test_primary_groups":1,"final_test_images":178,
                 "incidental_historical_test_sheet_exposure":observations["incidental_historical_a2_exposure"]}}
    json_write("qa_summary.json",stats)
    status1="\n".join(f"| {k} | {v} |" for k,v in counts1.items())
    status2="\n".join(f"| {k} | {v} |" for k,v in counts2.items())
    flag_table="\n".join(f"| {k} | {v} |" for k,v in flags.items())
    (OUT/"A1_QA_REPORT.md").write_text(f"""# A1 Annotation Pre-Training QA v1

5 November 2026 (WIB). **RESEARCH_PROTOTYPE / NOT_FIELD_VALIDATED**.
Tidak ada training, prediksi model, atau evaluasi performa pada test. Review test di sini
terbatas pada kualitas ground truth yang secara eksplisit diminta.

## Integritas dan investigasi antrean lama

SHA-256 seluruh 19 output frozen sesuai `FREEZE.json`; raw, audit terdahulu dan Model B1
juga diverifikasi. Split tetap train=204, validation=61, test=46, quarantine=8, excluded=2.
`a1_review_queue.csv` lama memang byte-identical dengan `a1_manifest.csv`, hash
`ee03dbb0c0fce26fc2c478a53e00c14a5423a969a0091670f0c7bcb2b110fab9`.
Penyebab pada script persiapan: keduanya ditulis dari DataFrame `a1` yang sama tanpa sort,
penilaian prioritas, atau field keputusan reviewer. Frozen tersebut dipertahankan utuh.

Antrean baru `a1_prioritized_review_queue.csv` berbeda: 321 baris, rank unik, priority tier,
risk score, alasan, geometry flags, status visual, aksi berikutnya dan kolom manusia kosong.
Urutan tier: semua reserved test; semua validation; known empty-positive excluded;
prior suspected missed; dense scene >=30; border/overlap; sisanya. Di dalam tier, skor
=40 suspected missed +15 dense +10 border +10 overlap +5 tiny +5 mixed class.
Tie: representative source dahulu, jumlah instance menurun, kemudian path. Ini urutan
kerja deterministik, bukan skor kebenaran biologis. Delapan quarantine tetap quarantine.

## Cakupan dan hasil

321 pasangan raw/overlay disediakan di `a1_overlays/`, resolusi paired 1280x700, melalui
`a1_review_index.html`. Gambar raw 640x640 dipertahankan pada sisi kiri; sisi kanan memuat
outline dan nomor baris label. Tidak ada perbaikan mask, object completion, atau rename kelas.
9 contact sheets merangkum 36 gambar: 11 test, 10 validation, 11 train, 2 excluded,
2 quarantine. Semua 36 diperiksa secara visual oleh AI agent; rank 6, 10, 58 juga
diperiksa melalui paired overlay ukuran penuh. **285 gambar belum ditriase visual
langsung pada task ini**, walaupun semuanya mendapat overlay dan screen otomatis.
Human approval: **0**. Sampel dipilih sengaja berdasarkan risiko/source, bukan sampel acak.

| Status AI visual triage | Gambar |
| --- | ---: |
{status1}

`NO_OBVIOUS_DEFECT_IN_TRIAGE` bukan label lengkap tersertifikasi. Lima contohnya rank
19,26,33,40,250; hanya rank250 merupakan train. Semua tetap menunggu full-resolution
review manusia dan persetujuan cakupan target. `a1_correction_candidates.csv` memuat
29 kasus untuk koreksi/adjudikasi manusia, termasuk yang tetap quarantine. Tidak ada
jumlah missing larvae yang ditebak atau dipakai sebagai label baru.

Temuan konkret:

- Rank1/test (`2023-10-13-11-17-05_jpg`) dan rank110/train
  (`image_1686225670032_png_jpg`) memperlihatkan banyak tubuh tanpa polygon.
- Rank48/validation (`2023-08-31-12-39-17_jpg`) memperlihatkan partial bodies pada
  tepi bawah tanpa anotasi; rank92/validation hanya memiliki dua polygon dalam scene
  yang berisi banyak tubuh terlihat. Validation belum layak dipakai mAP standar.
- Rank6/test (`image_1686312179706_png_jpg`) memiliki dua polygon pada satu apparent
  body. Ini **possible duplicate**, perlu adjudikasi; tidak otomatis menghapus salah satu.
- Rank10/test berisi bentuk mirip tubuh di balik mesh. Rank58/validation mempunyai
  banyak overlap. Kebijakan visible/amodal mask dan minimum visibility belum ditetapkan;
  tidak boleh mengarang kontur tubuh di balik occluder.
- Rank108/109 adalah dua positive images kosong label. Keduanya tetap excluded.
- Polygon sering kasar dan sebagian objek terpotong frame; format valid tidak menjamin
  batas biologis akurat, object completeness, atau satu polygon per larva.

## Screen geometry seluruh dataset

| Flag (jumlah gambar, dapat tumpang tindih) | Gambar |
| --- | ---: |
{flag_table}

Border: vertex dalam 2/640 dari tepi. Tiny: raster-contour area <64 pixel². Coarse: <=5
vertices. Overlap: intersection/min(instance area)>5%; high-IoU: intersection/union>80%,
diukur pada raster 640x640. Nilai ini untuk antrean, **bukan 54 overlap salah atau 13
duplicate terkonfirmasi**. Occlusion dapat sah. Structural checks dan checksum lolos;
tidak ada sertifikasi topology/biological-boundary baru.

## Class scope dan keputusan

Nama biologis class0/class1 tetap UNKNOWN. Pada sampel, kedua warna outline berada pada
objek yang tampak larviform, tetapi ini tidak memverifikasi species/stadium maupun aturan
inklusi dataset. **Penggabungan kelas belum diaktifkan.** Ini memperketat rekomendasi
awal di preparation report: class-agnostic `visible_bsf_larva` baru layak diusulkan
sebagai training default setelah ahli/sumber memastikan kedua ID termasuk cakupan target
BSF larval object yang sama. Jika tidak terkonfirmasi, pertahankan kelas anonim/ambiguity
dan tahan eksperimen; jangan menamainya prepupa, pupa, jantan atau betina.

**Training readiness saat ini: NO-GO** untuk fit segmentasi dengan label raw apa adanya.
0 gambar disahkan untuk training; bukan berarti semua 321 rusak, melainkan tidak ada
human sign-off. Test/validation completeness belum tersertifikasi, dan ada bukti
missing coverage pada keduanya. **Validation hanya satu primary split group (61 gambar)**;
test dua primary groups (46 gambar). Jumlah image/variant bukan jumlah unit biologis
independen. Kepadatan tinggi tidak tercakup pada validation. Jangan reshuffle split.

Langkah manusia berikutnya ada di `REVIEW_PROTOCOL.md`: review/correct pada working
label versi baru, dokumentasikan truncated/occluded policy, sahkan class scope dan
completeness validation/test. Tidak ada original annotation yang diubah oleh task ini.
""",encoding="utf-8")
    (OUT/"A2_PREPROCESSING_QA_REPORT.md").write_text(f"""# A2 Image Preprocessing QA v1

**RESEARCH_PROTOTYPE / NOT_FIELD_VALIDATED**. Tidak ada model dilatih atau final-test
performance dihitung. Target tetap measured individual **Weight (g)**; konversi mg
numerik tidak mengonfirmasi protokol wet-weight. Kalibrasi pixel-ke-mm belum valid.

## Metode dan isolasi data

Kode `../../a2_preprocessing.py`: warm-colour connected-component ROI hypothesis dari
RGB saja, pada longest-side1014 untuk screening, lalu bounding box dipetakan ke koordinat
full-resolution. Threshold, connected components, margin 8% long side (minimum24 native
pixels), serta padding512 disimpan di `a2_preprocessing_config.json`. Tidak ada learned
threshold, central-crop assumption, Weight/Sex/ID sebagai predictor, atau fitting.
Tidak ada threshold/margin disetel ulang sesudah melihat kegagalan preview.

Crop dibuat dari full-resolution raw, resize isotropik + neutral letterbox (maksimal
rounding satu pixel), tanpa rotasi, stretching, morfologi tubuh, inpainting atau foreground
mask otomatis. Ukuran, offset dan faktor resize tercatat untuk representative previews.
Aspect ratio terjaga, **skala piksel absolut antar-crop tidak terjaga**: crop variabel
dinormalisasi ke512. Ukuran output bukan mm atau proxy ukuran fisik yang sudah sah.
Pemilihan fixed-scale versus normalized crop kelak harus menjadi eksperimen train/val
yang eksplisit; jangan menganggap hal itu sudah terpecahkan oleh preprocessing ini.

Pipeline membaca hanya **1.114** gambar development: 924 train, 190 validation. Setiap
byte gambar dicocokkan SHA-256 dengan frozen manifest. ZIP dibaca satu JPEG sekali;
raw4056x3040 tetap utuh, tidak memuat seluruh arsip ke RAM. Test178 dan quarantine316
ditolak oleh guard preprocessing. Verifikasi checksum file raw bukan evaluasi gambar test.

Transparansi paparan historis: sebelum membership lembar lama diketahui, audit sheet
`../model_a_audit/single_detail_review.png` sempat ditampilkan dan berisi ID1102 yang kini
test, serta1371/1613 yang quarantine. **Jangan mengklaim complete visual blindness.**
Paparan dicatat di `agent_visual_observations.json`; tidak ada parameter dipilih/disetel
menggunakan contoh tersebut, tidak ada preprocessing baru atau prediksi test/quarantine,
dan tidak ada pergantian holdout untuk menutupi paparan. Keputusan baru memakai dev saja.

## Hasil otomatis versus inspeksi visual

Semua1.114 gambar menghasilkan kandidat ROI; ini **bukan 100% crop success**. Status
otomatis:1037 REVIEW_REQUIRED,68 MULTIPLE_COMPONENTS_REVIEW,9 POSSIBLE_SOURCE_TRUNCATION.
Flag edge berarti komponen proposal menyentuh sumber, bukan sembilan larva pasti terpotong.
Seluruh kandidat tetap `training_approved=False`. Raw bounds valid tidak membuktikan
body coverage. Template human review dan fungsi `approved_crop` menolak ekspor crop
training sebelum ada human review terikat exact ROI + source/pixel hash.

35 representative previews:3 ID tersebar per development batch, ditambah dev contoh1,
200,600; seleksi tidak memakai Weight/Sex. Ditambah8 stress cases dari flag otomatis
(dua per split/status), total43 visual triage. Ini sampel berstrata/purposeful, bukan
estimasi error-rate populasi. **1.071 kandidat lain belum diinspeksi visual pada task ini.**

| Status AI visual triage | Preview |
| --- | ---: |
{status2}

Temuan yang diukur/diamati:

- ID1,200,600 dan banyak contoh lain tampak mempertahankan kedua ujung tubuh serta
  mengeluarkan kartu ID.25 dari43 tidak memperlihatkan defect jelas pada skala preview;
  tetap bukan persetujuan manusia atau pembuktian seluruh rambut/appendage terjaga.
- ID107 mempertahankan tulisan0107 dan F;1474/1460 juga mempertahankan ID. **Tidak layak
  langsung digunakan** sebagai input weight model.107 bahkan hanya berstatus otomatis
  REVIEW_REQUIRED, sehingga flag otomatis saja tidak cukup mendeteksi shortcut.
- ID723,724,815,907,908,954,1000,1002,1041,1080 masih memuat ruler/tick marks dekat atau
  di belakang tubuh. Tight rectangle saja tidak menyelesaikan ini. Mask kerja yang
  diverifikasi atau penahanan sampel diperlukan; jangan menghapus tubuh/inpaint otomatis.
- ID773 adalah **wrong ROI**: crop berisi kartu dan foreground finger, larva tertinggal
  di luar crop. Largest warm component tidak dapat dianggap identitas larva.
- ID253 tampak sudah terpotong pada tepi atas sumber; preprocessing tidak dapat
  merekonstruksi bagian tubuh yang tidak ada. Tandai hold pada working eligibility,
  tetap simpan source dan reservasi train aslinya.
- ID1372 menyisakan card edge;1461/62 menyisakan residue/debris. Status background perlu
  review, bukan bukti Weight salah. Tidak dibuat klaim bebas seluruh shortcut.

41/43 preview tampak mengandung apparent whole body; dua pengecualian773/253. Angka ini
deskripsi triase tanpa mask ground truth, **bukan recall/akurasi crop**.25 apparent-clean
tidak sama dengan25 crop approved; jumlah human-approved tetap **0**.

## Kelayakan dan langkah manusia

**CONDITIONAL GO** untuk feasibility preprocessing dengan reviewer pada setiap working
ROI; **NO-GO** untuk otomatis memproses lalu melatih image model pada semua kandidat.
Belum ada crop yang disahkan. `a2_crop_eligibility_working.csv` mengikat hasil ke reservasi
frozen tanpa mengubah split. Manusia harus mengonfirmasi whole-body/morphology, bebas
written IDs/sex, dan background acceptable, serta menolak sumber terpotong.
`approved_crop` hanya menerapkan keputusan reviewer; bukan detektor tulisan atau jaminan
semantik. Sampel yang ditahan kelak harus dilaporkan sebagai perubahan coverage, bukan
diam-diam diganti batch/splitnya. Jangan buang seluruh ruler-heavy cohort lalu mengklaim
generalisasi dataset penuh tanpa audit selection bias.

Morphometric baseline Length→Weight dapat menjadi eksperimen terkontrol pertama pada
924 train/190 validation, setelah otorisasi task training terpisah. Length+Width memiliki
905 train/190 validation positif; unit Width tetap UNKNOWN dan perlu konfirmasi untuk
interpretasi fisik. Fitting scaler/model hanya train; pemilihan hanya validation.
Test tetap disegel untuk evaluasi terpisah setelah model selection.

**A2 final test hanya satu primary split group/batch B011 (178 gambar, dua tanggal).**
Tidak mendukung estimasi generalisasi antar-batch luas atau menghitung178 sampel biologis
independen. Shared session, ancestry, nuisance background, near-duplicate yang belum
terdeteksi, 316 quarantine, domain shift kamera lapangan dan no-local-BSF-data tetap risiko.
Pipeline A1→A2 tidak tervalidasi; belum ada ground truth biomass gabungan.
""",encoding="utf-8")
    (OUT/"READINESS_DECISION.md").write_text("""# Keputusan pre-training QA

Status: RESEARCH_PROTOTYPE / NOT_FIELD_VALIDATED. Tidak ada model dilatih, API dibuat,
frozen split diganti, source annotation diperbaiki, atau Model B1 diubah.

| Jalur | Keputusan sekarang | Syarat langkah berikutnya |
| --- | --- | --- |
| A1 raw-label segmentation | **NO-GO** | 0 training images human-approved. Koreksi coverage, duplicate/occlusion/truncation policy, class scope; sahkan validation/test working labels. |
| A2 automatic image training | **NO-GO** | Wrong ROI, source truncation, ID/sex/ruler shortcuts terbukti pada preview; 0 crop human-approved. |
| A2 supervised crop feasibility | **CONDITIONAL GO** | Proposal+preview siap; reviewer memeriksa exact ROI/hash, seluruh tubuh dan shortcut, mengisi working approval. Tidak ada NN training pada task ini. |
| A2 Length→measured Weight baseline | **GO untuk task eksperimen berikutnya** | Tabel frozen siap:924 train/190 validation. Fit train saja, select validation, test178 belum dievaluasi. |
| A2 Length+Width baseline | **CONDITIONAL GO** |905 train/190 validation Width positif; unit Width perlu konfirmasi. Bandingkan model pada intersection populasi yang sama. |
| Combined A1→A2 | **NO-GO** | Belum ada validasi crop transfer, correspondence berat individual, calibration atau biomass. |

Temuan A1:321 overlay,36 triase visual (26 perlu koreksi,3 adjudikasi,5 tanpa defect
jelas pada skala triase,2 tetap excluded),285 belum ditriase visual langsung. Lima
apparent-clean tetap bukan human approval. Validation61 hanya **satu primary group**;
test46 dua kelompok, high-density validation tidak tersedia.

Temuan A2:1.114 kandidat dev otomatis,35 representative+8 stress preview diperiksa;
25 tanpa defect jelas,3 ID/sex retention,10 ruler retention,3 background-review,
1 wrong ROI,1 source truncation.1.071 kandidat belum ditriase visual. Final test178 hanya
**satu primary group**. Jumlah image bukan jumlah batch/individu biologis independen.

Yang masih memerlukan manusia:

1. A1: buka antrean/overlay full size; putuskan object scope class0/1, anotasi semua
   target sesuai aturan visibilitas, tangani duplicate/border/occlusion, simpan working
   labels versi baru dengan identitas source dan reservasi tetap. Approve coverage
   validation/test sebelum mAP. Tidak ada biological labels yang diinventarisasi otomatis.
2. A2: periksa seluruh crop yang akan dipakai, terutama daftar shortcut/failure; source253
   tidak dapat dilengkapi oleh crop. Isi approval manusia terikat sumber/bbox/pixel hash.
   Konfirmasi unit Width, Weight measurement protocol, dan calibration dari sumber/ahli.
3. Lanjut pertama dengan baseline Length→Weight di train/validation setelah task training
   diotorisasi. Jangan menggunakan neural image model atau membuka final test untuk
   memilih preprocessing sampai working data lolos review. Tidak perlu reshuffle data.

Integritas: freeze19 output, raw646 file, audit lama dan B1 dicocokkan SHA-256 sebelum
dan sesudah QA. Antrean lama identik manifest memang terverifikasi; antrean prioritas
baru tersimpan terpisah. `QA_RECEIPT.json` menyimpan hash kode dan seluruh output QA.
Paparan insidental ID1102 dari contact sheet audit lama dicatat secara terbuka pada
laporan A2; jangan mengklaim complete visual blindness. Tidak ada model/test metrics.

Reproduksi: `python -B .agents/skills/fiscycle-bsf-ai/qa_model_a.py verify` dari root.
`build` dan `stress` menghasilkan artefak development tanpa fitting. `finalize` memakai
observasi visual yang tercatat, bukan generasi ulang keputusan manusia. Versi selesai
menolak overwrite; perbaikan berikutnya harus memakai versi working baru.
""",encoding="utf-8")
    verify_outputs()
    receipt={"status":"COMPLETE_PRETRAINING_QA_NO_TRAINING", "date_wib":"2026-11-05",
             "input_freeze_sha256":sha(FROZEN/"FREEZE.json"),
             "code_sha256":{p:sha(ROOT/p) for p in ["qa_model_a.py","a2_preprocessing.py"]},
             "environment":{"python":platform.python_version(),"pandas":pd.__version__,"numpy":np.__version__,
                            "opencv":cv2.__version__,"pillow":Image.__version__},
             "outputs":{p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob("*")) if p.is_file()},
             "human_approvals":0,"models_fitted":0}
    json_write("QA_RECEIPT.json",receipt)
    print(json.dumps(stats,indent=2,ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
