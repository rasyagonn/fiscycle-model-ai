"""Standalone exploratory A1/A2 inference. No API and no A1 -> A2 integration."""
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
RUN=ROOT/'hasil/model_a_training_v1'
os.environ.setdefault('YOLO_CONFIG_DIR',str(RUN/'ultralytics_settings'))
import json
from functools import lru_cache
from PIL import Image
import torch
from torch import nn
from torchvision.models import mobilenet_v3_small
from torchvision.transforms import functional as TF

STATUS=['RESEARCH_PROTOTYPE','NOT_FIELD_VALIDATED','EXPLORATORY_UNVERIFIED_LABELS']
def _image(value):
    if isinstance(value,Image.Image):return value.convert('RGB')
    with Image.open(value) as im:return im.convert('RGB')

@lru_cache(maxsize=2)
def _a1(checkpoint):
    from ultralytics import YOLO
    return YOLO(checkpoint)

def predict_larvae(image,confidence=0.25,checkpoint=None):
    """Predict visible instances. Confidence is detector score, not calibrated probability."""
    path=Path(checkpoint) if checkpoint else RUN/'a1_initial/weights/best.pt'
    im=_image(image)
    result=_a1(str(path)).predict(im,imgsz=320,conf=confidence,device='cpu',max_det=300,verbose=False)[0]
    polygons=result.masks.xy if result.masks is not None else []
    instances=[dict(polygon_xy=p.tolist(),confidence=float(c),class_name='visible_bsf_larva') for p,c in zip(polygons,result.boxes.conf.tolist())]
    return dict(instances=instances,visible_instance_count=len(instances),detection_limit_reached=len(result.boxes)>=300,
        max_detections=300,model_version='a1_training_v1/'+path.parent.parent.name,
        status=STATUS,confidence_threshold=confidence,coordinates='original_image_pixels',
        limitations=['Incomplete development labels; count and masks provisional','Biological equivalence of source class IDs 0/1 unverified','No total biomass or A1-to-A2 integration validated'])

@lru_cache(maxsize=2)
def _a2(checkpoint):
    obj=torch.load(checkpoint,map_location='cpu',weights_only=True)
    model=mobilenet_v3_small(weights=None)
    model.classifier=nn.Sequential(nn.Linear(576,128),nn.Hardswish(),nn.Dropout(.2),nn.Linear(128,1))
    model.load_state_dict(obj['state_dict']);model.eval()
    return model,obj['config']

def predict_measured_weight(single_larva_image,preprocessed=False,checkpoint=None):
    """Raw single-larva photo -> v2 pixel-only ROI, or explicitly supplied v2 letterboxed crop.

    Automatic ROI checks can miss bad crops. Do not pass A1 multi-larva crops as validated input.
    """
    if checkpoint:path=Path(checkpoint)
    else:
        selection=RUN/'selected_models.json'
        name=json.loads(selection.read_text())['a2'] if selection.exists() else 'a2_initial'
        path=RUN/name/'best.pt'
    im=_image(single_larva_image);quality={'preprocessed_input':preprocessed,'expert_verified':False}
    if preprocessed:
        if im.size!=(512,512):raise ValueError('preprocessed=True requires the v2 512x512 letterboxed crop')
    else:
        from a2_preprocessing_v2 import propose_roi
        from a2_preprocessing import letterbox_crop
        roi=propose_roi(im)
        quality.update(roi_found=roi['roi_found'],source_edge_contact=roi['source_edge_contact'],shortcut_suspected=roi['shortcut_suspected'],crop_bbox=roi['crop_bbox'])
        if not roi['roi_found'] or roi['source_edge_contact'] or roi['shortcut_suspected']:
            return dict(predicted_measured_weight_mg=None,status=STATUS+['ABSTAIN_CROP_REVIEW_REQUIRED'],crop_quality=quality,model_version='a2_training_v1/'+path.parent.name)
        im,_=letterbox_crop(im,roi['crop_bbox'],512)
    model,cfg=_a2(str(path));im=im.resize((cfg['input_size'],cfg['input_size']),Image.Resampling.BILINEAR)
    x=TF.normalize(TF.to_tensor(im),cfg['normalization_mean'],cfg['normalization_std']).unsqueeze(0)
    with torch.inference_mode():prediction=float(model(x).item()*cfg['target_std_mg']+cfg['target_mean_mg'])
    return dict(predicted_measured_weight_mg=prediction,model_version='a2_training_v1/'+path.parent.name,status=STATUS,
        crop_quality=quality,limitations=['Measured weight protocol wet/dry UNKNOWN','No physical pixel-scale calibration','Studio/tray images only; no field validation','No supported per-prediction confidence interval'])

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('model',choices=['a1','a2']);p.add_argument('image');p.add_argument('--preprocessed',action='store_true');args=p.parse_args()
    torch.set_num_threads(4)
    result=predict_larvae(args.image) if args.model=='a1' else predict_measured_weight(args.image,preprocessed=args.preprocessed)
    print(json.dumps(result))
