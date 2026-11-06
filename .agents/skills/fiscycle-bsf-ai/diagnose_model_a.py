"""Development-only diagnostics and reproducible standalone inference smoke checks."""
from train_model_a import ROOT,OUT,STATUS,save,seed,metrics,f
import argparse,json,io
from pathlib import Path
import numpy as np
import pandas as pd
from PIL import Image,ImageDraw,ImageFont
import torch
FONT=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',17)

def a1():
    seed()
    from ultralytics import YOLO
    dest=OUT/'a1_diagnostics';dest.mkdir(exist_ok=True)
    model=YOLO(str(OUT/'a1_initial/weights/best.pt'))
    result=model.val(data=str(OUT/'a1_dataset/data.yaml'),split='val',imgsz=320,batch=2,device='cpu',workers=0,
        overlap_mask=False,mask_ratio=2,plots=False,project=str(OUT),name='a1_validation',exist_ok=True,verbose=False)
    save(dest/'metrics.json',dict(status=STATUS,scope='development_validation_only',metrics=result.results_dict,
        precision_recall_note='Framework operating point; count diagnostics separately use confidence=0.25',
        incomplete_labels=True,primary_validation_groups=1))
    df=pd.read_csv(OUT/'a1_development_manifest.csv');df=df[df.experiment_eligible]
    va=df[df.split=='validation'];tr=df[df.split=='train'].sort_values('annotation_count',ascending=False).head(4)
    examined=pd.concat([va,tr],ignore_index=True);records=[];outputs={}
    for r in examined.itertuples():
        pred=model.predict(r.experiment_image,imgsz=320,conf=.25,device='cpu',verbose=False,max_det=300)[0]
        count=len(pred.boxes);record=dict(id=r.id,split=r.split,split_group_id=r.split_group_id,
            source_path=r.source_path,annotated_count=r.annotation_count,predicted_count=count,
            count_difference=count-r.annotation_count,absolute_count_difference=abs(count-r.annotation_count),
            known_annotation_issues=r.known_annotation_issues,confidence_threshold=.25)
        records.append(record);outputs[r.id]=pred
    counts=pd.DataFrame(records);counts.to_csv(dest/'instance_counts.csv',index=False)
    valcounts=counts[counts.split=='validation']
    save(dest/'count_summary.json',dict(validation_n=len(valcounts),annotated_total=int(valcounts.annotated_count.sum()),predicted_total=int(valcounts.predicted_count.sum()),
        count_MAE_vs_incomplete_annotations=float(valcounts.absolute_count_difference.mean()),count_bias=float(valcounts.count_difference.mean()),
        note='Differences from incomplete ground truth are not automatically false positives or true misses'))
    selected=pd.concat([valcounts.nlargest(6,'absolute_count_difference'),valcounts.nsmallest(3,'absolute_count_difference'),counts[counts.split=='train']]).drop_duplicates('id')
    index=[]
    for n,r in enumerate(selected.itertuples(),1):
        row=df.set_index('id').loc[r.id]
        original=Image.open(row.experiment_image).convert('RGB');gt=original.copy();draw=ImageDraw.Draw(gt)
        for j,p in enumerate(f.parse_labels(row.experiment_label),1):
            xy=[(x*640,y*640) for x,y in p['points']];draw.line(xy+[xy[0]],fill='#00ff77',width=2);draw.text(xy[0],str(j),fill='yellow')
        pred=Image.fromarray(outputs[r.id].plot()[...,::-1]);panel=Image.new('RGB',(1280,690),'white');panel.paste(gt,(0,50));panel.paste(pred,(640,50))
        d=ImageDraw.Draw(panel);d.text((8,5),f'{r.id} {r.split} | annotation {r.annotated_count} (incomplete)',font=FONT,fill='black');d.text((650,5),f'Prediction {r.predicted_count} at conf 0.25',font=FONT,fill='black')
        path=dest/f'{n:02}_{r.id}.jpg';panel.save(path,quality=92)
        index.append(dict(id=r.id,split=r.split,panel=path.name,annotation_count=r.annotated_count,predicted_count=r.predicted_count))
    pd.DataFrame(index).to_csv(dest/'preview_index.csv',index=False)
    queue=counts.sort_values('absolute_count_difference',ascending=False).head(12).copy()
    queue['review_action']='Inspect source and predicted masks: count disagreement is a triage signal, not correction truth'
    queue.to_csv(dest/'targeted_correction_queue.csv',index=False)
    print(json.dumps(f.read_json(dest/'metrics.json'),indent=2),flush=True)

def a2():
    candidates=['a2_initial']+(['a2_improved'] if (OUT/'a2_improved/metrics.json').exists() else [])
    scores={name:f.read_json(OUT/name/'metrics.json') for name in candidates}
    selected=min(candidates,key=lambda k:scores[k]['overall']['MAE_mg'])
    save(OUT/'selected_models.json',dict(a1='a1_initial',a2=selected,selection='Development validation only; lowest A2 MAE, A1 framework best checkpoint',final_test_used=False))
    dest=OUT/'a2_diagnostics';dest.mkdir(exist_ok=True)
    pred=pd.read_csv(OUT/selected/'validation_predictions.csv')
    ref=pd.read_csv(OUT/'a2_baselines/validation_predictions.csv')
    matched=pred.merge(ref[['L_ID','mean','length_linear','length_ridge']],on='L_ID',validate='one_to_one')
    assert len(matched)==len(pred)==152
    comparison={k:metrics(matched.measured_weight_mg,matched[k]) for k in ['mean','length_linear','length_ridge','predicted_measured_weight_mg']}
    # Fair training-distribution reference: recompute mean from same eligible image train population.
    dev=pd.read_csv(OUT/'a2_development_manifest.csv');tr=dev[dev.experiment_eligible & dev.split.eq('train')]
    matched['eligible_train_mean']=float((tr.measured_weight_g*1000).mean())
    comparison['eligible_train_mean']=metrics(matched.measured_weight_mg,matched.eligible_train_mean)
    for k in comparison:comparison[k]['MAE_improvement_vs_full_train_mean_pct']=100*(1-comparison[k]['MAE_mg']/comparison['mean']['MAE_mg'])
    matched.to_csv(dest/'matched_validation_predictions.csv',index=False)
    save(dest/'comparison.json',dict(selected=selected,same_validation_n=152,models=comparison,candidates=scores,
        length_comparison='Reference benchmark with manually measured Length, not input-equivalent to image-only regression'))
    bins=pd.cut(matched.measured_weight_mg,[-np.inf,180,240,np.inf],labels=['<180','180-240','>240'])
    save(dest/'error_by_measured_weight_range.json',{str(b):metrics(g.measured_weight_mg,g.predicted_measured_weight_mg) for b,g in matched.groupby(bins,observed=True)})
    chosen=pd.concat([pred.assign(abs_error=pred.error_mg.abs()).nlargest(8,'abs_error'),pred.assign(abs_error=pred.error_mg.abs()).nsmallest(4,'abs_error')]).drop_duplicates('id')
    for start in range(0,len(chosen),6):
        page=Image.new('RGB',(1152,650),'#eeeeee');draw=ImageDraw.Draw(page)
        for i,r in enumerate(chosen.iloc[start:start+6].itertuples()):
            x=(i%3)*384;y=(i//3)*325
            with Image.open(ROOT/r.artifact_path) as im:page.paste(im.resize((256,256)),(x,y+60))
            draw.text((x+4,y+2),f'{r.id} {r.Batch_ID}',font=FONT,fill='black')
            draw.text((x+4,y+22),f'true {r.measured_weight_mg:.1f} pred {r.predicted_measured_weight_mg:.1f} mg',font=FONT,fill='black')
            draw.text((x+4,y+42),f'error {r.error_mg:+.1f} mg',font=FONT,fill='black')
        page.save(dest/f'error_examples_{start//6+1:02}.jpg',quality=95)
    chosen.to_csv(dest/'targeted_review_cases.csv',index=False)
    print(json.dumps(comparison,indent=2),flush=True)

def smoke():
    seed()
    from model_a_inference import predict_larvae,predict_measured_weight
    a=pd.read_csv(OUT/'a1_development_manifest.csv');r=a[a.experiment_eligible & a.split.eq('validation')].iloc[0]
    first=predict_larvae(r.experiment_image)
    assert first['visible_instance_count']==len(first['instances'])
    assert first['visible_instance_count']>0
    assert all(len(i['polygon_xy'])>=3 and 0<=i['confidence']<=1 for i in first['instances'])
    b=pd.read_csv(OUT/'a2_development_manifest.csv');s=b[b.experiment_eligible & b.split.eq('validation')].iloc[0]
    second=predict_measured_weight(ROOT/s.artifact_path,preprocessed=True)
    assert np.isfinite(second['predicted_measured_weight_mg'])
    selection=f.read_json(OUT/'selected_models.json')['a2'];pred=pd.read_csv(OUT/selection/'validation_predictions.csv').set_index('id')
    assert abs(second['predicted_measured_weight_mg']-pred.loc[s.id,'predicted_measured_weight_mg'])<0.01
    blank=predict_measured_weight(Image.new('RGB',(640,480),'white'))
    assert blank['predicted_measured_weight_mg'] is None
    # Raw-photo preprocessing branch: read exactly one development image from immutable ZIP.
    import zipfile
    meta=pd.read_csv(OUT/'a2_tabular_development.csv').set_index('L_ID').loc[int(s.L_ID)]
    with zipfile.ZipFile(ROOT/meta.archive_path) as z:
        with Image.open(io.BytesIO(z.read(meta.archive_member))) as im:raw=predict_measured_weight(im.copy())
    assert raw['predicted_measured_weight_mg'] is not None
    assert abs(raw['predicted_measured_weight_mg']-second['predicted_measured_weight_mg'])<0.01
    save(OUT/'inference_smoke_test.json',dict(passed=True,a1_sample=r.id,a1=first,a2_sample=s.id,a2=second,raw_photo_branch=raw,empty_image_abstention=blank))
    print('PASS: standalone A1 polygons/count, A2 finite prediction matching validation, raw-photo ROI branch, blank-photo abstention')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['a1','a2','smoke']);args=p.parse_args()
    globals()[args.stage]()
