"""Exact saved gallery inference method; extracted without scientific changes."""
import math
from fastapi import HTTPException
from app.services.bsf_models import STATUS
from app.services.bsf_intelligence import decode_image
from app.services.bsf_photo import analyze_photo
from app.services.bsf_gallery_roi import propose_roi
VERSION = "bsf_gallery_v1"


class GalleryInference:
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

