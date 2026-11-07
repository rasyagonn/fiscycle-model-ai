---
language:
- id
- en
tags:
- fiscycle
- research-prototype
- not-field-validated
---

# Fiscycle Smart BSF A2 v3 — experimental image-to-measured-Weight regression

## Purpose and architecture
Frozen MobileNetV3 Small backbone, regression head 576→128→1, Hardswish and dropout 0.2. `best.pt` contains model state plus frozen config/target normalization. Output `predicted_measured_weight_mg` is estimated measured Weight of one larva. Wet/dry protocol remains unconfirmed.

## Exact preprocessing
Retain the entire eligible ROI at original native-pixel size. Center on a 2048×2048 source-pixel canvas, neutral RGB 127 padding; do not introduce new source context outside the clean ROI. Reject ROI larger than the canvas. Perform ONE bilinear resize to 224×224, then tensor/ImageNet normalization (mean 0.485/0.456/0.406, std 0.229/0.224/0.225). Invert prediction with frozen target_mean_mg/target_std_mg from checkpoint config. Preserve source geometry and reject unsuitable/truncated/shortcut-contaminated crops. No generic full-image resizing or aspect distortion. Pixels are not calibrated physical millimeters.

## Saved evaluation
On the SAME 152 validation IDs (two primary groups): v3 MAE 17.288405 mg, RMSE 22.555757 mg, bias −3.423078 mg, R² 0.819658. V2 MAE 37.856160 mg. V3 trains 455 images versus v2 456 due to one held shortcut-risk crop; this is not a preprocessing-only causal experiment.

Released final test: 178 images from ONE primary group; automatic ROI accepted 130 and rejected 48. Descriptive MAE 19.140898 mg, RMSE 23.555634 mg and bias +3.057749 mg apply ONLY to the 130 accepted predictions. Prediction coverage 130/178 = 73.0337%. Strict reviewed-ROI test n=0, unavailable. Do not claim MAE 19.14 mg on all 178 images.

## Intended use and limitations
RESEARCH_PROTOTYPE / NOT_FIELD_VALIDATED. Camera distance, zoom, scale and domain are not calibrated across arbitrary photos. Validation MAE does not guarantee per-image error. A1→A2 is experimental and analyzed-visible mass is not total batch biomass. A2 is not automatically compatible with B1 mean wet-weight inputs. Test is released/not blind; no tuning/retraining occurred in packaging.

## Attribution and distribution
Quentin Geissmann, Zenodo DOI 10.5281/zenodo.13359376, CC BY 4.0 dataset attribution. No raw training/test photos, IDs or labels in this repository. Model artifact redistribution/license remains subject to owner/dependency review; begin PRIVATE.

## Version and checksums

Model version: `model_a2_training_v3`. Packaging: `3.0.0-rc1`. HF revision is pending upload; the local pinned registry will be populated with the actual commit SHA, never a fabricated hash or changing main. `checksums.json` covers every package file except itself.

- `hasil/model_a2_training_v3/best.pt`: `2813ae2e45deaa5eea689e131fba639a20f122ef6474156530ea7cf24f33952b`
- `hasil/model_a2_training_v3/preprocessing_config.json`: `b81170ba47b6babe78a39f52b0cdc9abb5f8f8a0b4ec04070b55b3f9d335ac9e`
- `hasil/model_a2_training_v3/COMPLETE.json`: `0131c9e6a0caf8c65ba81043e41a3efa7a4a32fcee21b76ad6b37b97559ace09`
