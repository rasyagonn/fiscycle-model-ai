---
language:
- id
- en
tags:
- fiscycle
- research-prototype
- not-field-validated
---

# Fiscycle Smart BSF A1 — visible larva instance segmentation

## Purpose and architecture
Frozen YOLO11n-seg selected checkpoint `a1_initial/weights/best.pt`. Inference resolution 320, confidence default 0.25, maximum 300 detections. Input JPEG/PNG/WebP becomes oriented RGB. Output masks map to source-image pixels, with detector confidence and visible detected instance count.

## Labels and preprocessing
Original source class IDs 0 and 1 have unresolved biological meanings. The runtime working class is `visible_bsf_larva`; this engineering mapping is not a biological equivalence claim. Preserve existing preprocessing and original-pixel mapping.

## Saved evaluation
Training: 166 eligible images; validation: 61 images from ONE primary group, labels not certified complete. Mask precision 0.838122, recall 0.957738, mAP50 0.927715, mAP50–95 0.725596: provisional against available annotations. Released final gallery execution: 46 test photos, 30 SUCCESS, 15 PARTIAL, 1 REJECTED/zero detections, zero technical failures. These statuses are not segmentation accuracy; certified final-test mAP is unavailable.

## Intended use and limitations
RESEARCH_PROTOTYPE / NOT_FIELD_VALIDATED. Incomplete labels, dense overlap, truncation and boundary objects limit counts and masks. Reaching 300 detections is a capacity warning, not a verified population. Confidence is not calibrated probability. Do not call visible-count output total population or batch biomass. Test images have already been evaluated/released and are no longer blind; no further tuning is authorized here.

## Attribution and distribution
Training imagery: Quentin Geissmann, Zenodo v1, DOI 10.5281/zenodo.13359376, CC BY 4.0. Ultralytics software/model licensing must be reviewed for intended deployment (AGPL-3.0/available commercial terms); dataset licensing alone does not determine model/code licensing. Begin PRIVATE. No raw images or annotations are included in this model package.

## Version and checksums

Model version: `a1_initial`. Packaging: `3.0.0-rc1`. HF revision is pending upload; the local pinned registry will be populated with the actual commit SHA, never a fabricated hash or changing main. `checksums.json` covers every package file except itself.

- `hasil/model_a_training_v1/a1_initial/weights/best.pt`: `b3fe49e24ca70bbd82505ba70b333f6a9fc9a21e83ca6672d81a12ec88658534`
