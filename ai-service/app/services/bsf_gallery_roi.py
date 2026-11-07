"""Pixel-only, untrained ROI ranking. Outputs are proposals requiring human review."""
import math
import cv2
import numpy as np
from PIL import Image


VERSION = "a2_roi_v2_ranked"
CONFIG = {"max_side":1014, "red_blue_min":30, "red_green_min":8,
          "saturation_min":40, "value_min":35, "value_max":240,
          "min_area_fraction":.001, "max_area_fraction":.075,
          "min_fill":.25, "max_aspect":7, "margin_fraction":.10,
          "min_margin_native":32, "output_size":512,
          "shortcut_line_min_px":24, "shortcut_dark_max":105}


def shortcut_screen(image, box, body_mask=None):
    """Flag straight dark lines / ink-like components; never certify text absence."""
    crop=image.crop(tuple(box)).convert("RGB")
    ratio=min(1.,512/max(crop.size))
    crop=crop.resize((max(1,round(crop.width*ratio)),max(1,round(crop.height*ratio))))
    rgb=np.asarray(crop)
    chroma=rgb.max(2).astype(int)-rgb.min(2).astype(int)
    dark=((rgb.max(2)<CONFIG["shortcut_dark_max"]) & (chroma<35)).astype(np.uint8)*255
    if body_mask is not None:
        bm=np.asarray(Image.fromarray(body_mask).resize(crop.size,Image.Resampling.NEAREST))
        bm=cv2.dilate(bm,np.ones((9,9),np.uint8))
        dark[bm>0]=0
    lines=cv2.HoughLinesP(dark,1,np.pi/180,threshold=15,
                          minLineLength=CONFIG["shortcut_line_min_px"],maxLineGap=3)
    n,_,stats,_=cv2.connectedComponentsWithStats(dark,8)
    ink=sum(5<=int(s[4])<=200 for s in stats[1:])
    return {"straight_dark_lines":0 if lines is None else len(lines),"ink_components":ink,
            "shortcut_suspected":bool(lines is not None or ink>=8)}


def propose_roi(image):
    """No metadata argument: neither IDs nor measured targets determine coordinates."""
    image=image.convert("RGB")
    width,height=image.size
    scale=min(1.,CONFIG["max_side"]/max(width,height))
    small=image.resize((round(width*scale),round(height*scale)),Image.Resampling.BILINEAR)
    rgb=np.asarray(small)
    signed=rgb.astype(np.int16)
    hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
    mask=((signed[:,:,0]-signed[:,:,2]>CONFIG["red_blue_min"]) &
          (signed[:,:,0]-signed[:,:,1]>CONFIG["red_green_min"]) &
          (hsv[:,:,1]>CONFIG["saturation_min"]) & (hsv[:,:,2]>CONFIG["value_min"]) &
          (hsv[:,:,2]<CONFIG["value_max"])).astype(np.uint8)
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    n,labels,stats,_=cv2.connectedComponentsWithStats(mask,8)
    options=[]
    for i in range(1,n):
        x,y,w,h,area=map(int,stats[i])
        fraction=area/(mask.shape[0]*mask.shape[1])
        fill=area/(w*h)
        aspect=max(w,h)/max(1,min(w,h))
        if not (CONFIG["min_area_fraction"]<=fraction<=CONFIG["max_area_fraction"] and
                fill>=CONFIG["min_fill"] and aspect<=CONFIG["max_aspect"]):
            continue
        edge=x<=1 or y<=1 or x+w>=mask.shape[1]-1 or y+h>=mask.shape[0]-1
        # Prefer complete interior components over skin/objects touching source edge.
        # Area score saturates; an oversized foreground object cannot win by size alone.
        score=min(fraction,.03)/.03 + fill - .2*abs(math.log(aspect/2.5)) - 4*int(edge)
        options.append(dict(component=i,bbox=[x,y,x+w,y+h],area=area,area_fraction=fraction,
                            fill=fill,aspect=aspect,source_edge_contact=bool(edge),score=score))
    options.sort(key=lambda o:(-o["score"],o["component"]))
    result={"method":VERSION,"roi_found":bool(options),"crop_bbox":None,"body_bbox":None,
            "source_edge_contact":False,"shortcut_suspected":False,"straight_dark_lines":0,
            "ink_components":0,"training_approved":False,"status":"HOLD_NO_CANDIDATE",
            "candidates":options,"selected_score":None,"score_gap":None}
    if not options:
        return result
    best=options[0]
    x0,y0,x1,y1=best["bbox"]
    native=[math.floor(x0/scale),math.floor(y0/scale),min(width,math.ceil(x1/scale)),min(height,math.ceil(y1/scale))]
    margin=max(CONFIG["min_margin_native"],round(max(native[2]-native[0],native[3]-native[1])*CONFIG["margin_fraction"]))
    box=[max(0,native[0]-margin),max(0,native[1]-margin),min(width,native[2]+margin),min(height,native[3]+margin)]
    full_mask=cv2.resize((labels==best["component"]).astype(np.uint8),(width,height),interpolation=cv2.INTER_NEAREST)
    screen=shortcut_screen(image,box,full_mask[box[1]:box[3],box[0]:box[2]])
    result.update(crop_bbox=box,body_bbox=native,selected_score=best["score"],
                  source_edge_contact=best["source_edge_contact"],**screen,
                  score_gap=best["score"]-options[1]["score"] if len(options)>1 else None)
    result["status"]=("HOLD_POSSIBLE_SOURCE_TRUNCATION" if best["source_edge_contact"] else
                      "HOLD_SHORTCUT_SCREEN" if screen["shortcut_suspected"] else "PENDING_HUMAN_REVIEW")
    return result
