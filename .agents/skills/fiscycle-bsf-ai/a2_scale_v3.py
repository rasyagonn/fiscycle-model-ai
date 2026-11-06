"""One controlled native-pixel-canvas A2 experiment; reuse frozen v2 training engine."""
from pathlib import Path
import os,json,math,io,zipfile,random,time,hashlib
import numpy as np
import pandas as pd
from PIL import Image,ImageOps,ImageDraw,ImageFont
import torch
from torchvision.transforms import functional as TF
import a2_gpu_experiment as engine
ROOT=Path(__file__).resolve().parent
V2=ROOT/'hasil/model_a2_training_v2'
OUT=ROOT/'hasil/model_a2_training_v3'
read,save,sha,scores=engine.read,engine.save,engine.sha,engine.scores
FONT=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',15)

def fixed_canvas(image,roi,canvas_size,output_size=224):
    """Geometry/pixels only. Preserve all old ROI pixels, pad outside it, one fixed resize."""
    im=image.convert('RGB');x0,y0,x1,y1=map(int,roi)
    if not (0<=x0<x1<=im.width and 0<=y0<y1<=im.height):raise ValueError('ROI outside source')
    w,h=x1-x0,y1-y0
    if max(w,h)>canvas_size:raise ValueError('FULL_ROI_EXCEEDS_TRAIN_SELECTED_CANVAS')
    left=(x0+x1)//2-canvas_size//2;top=(y0+y1)//2-canvas_size//2
    ox,oy=x0-left,y0-top
    canvas=Image.new('RGB',(canvas_size,canvas_size),(127,127,127))
    patch=im.crop((x0,y0,x1,y1));canvas.paste(patch,(ox,oy))
    assert canvas.crop((ox,oy,ox+w,oy+h)).tobytes()==patch.tobytes()
    result=canvas.resize((output_size,output_size),Image.Resampling.BILINEAR)
    return result,dict(source_width=im.width,source_height=im.height,roi_bbox=[x0,y0,x1,y1],
        source_canvas_bbox=[left,top,left+canvas_size,top+canvas_size],roi_offset=[ox,oy],
        padding_ltrb=[ox,oy,canvas_size-ox-w,canvas_size-oy-h],
        source_boundary_padding_ltrb=[max(0,-left),max(0,-top),max(0,left+canvas_size-im.width),max(0,top+canvas_size-im.height)],
        native_roi_width=w,native_roi_height=h,native_roi_long_side=max(w,h),scale_factor=output_size/canvas_size,
        retained_native_roi_pixels=w*h,roi_pixels_preserved_before_resize=True,
        outside_roi_policy='neutral127; no new source context',pixel_to_mm=None)

def tensor(image,size,augment=False):
    im=image.convert('RGB')
    if im.size!=(size,size):raise ValueError('Expected v3 fixed-scale prepared224x224 image')
    if augment:
        if random.random()<.5:im=ImageOps.mirror(im)
        if random.random()<.5:im=ImageOps.flip(im)
        if random.random()<.5:im=im.transpose(random.choice([Image.Transpose.ROTATE_90,Image.Transpose.ROTATE_180,Image.Transpose.ROTATE_270]))
    return TF.normalize(TF.to_tensor(im),[.485,.456,.406],[.229,.224,.225])

def prepare():
    OUT.mkdir(exist_ok=True)
    if (OUT/'preprocessing_receipt.json').exists():print('Preparation already complete');return
    assert not (OUT/'best.pt').exists()
    engine.seed(read(V2/'config.json')['seed'])
    receipt=read(V2/'COMPLETE.json');cfg=read(V2/'config.json')
    assert sha(ROOT/'a2_gpu_experiment.py')==receipt['code_sha256']
    assert sha(V2/'config.json')==receipt['config_sha256']
    for n,h in receipt['checkpoint_hashes'].items():assert sha(V2/n)==h,n
    # Hash frozen reservations without reading reserved image pixels or target labels.
    protected=read(V2/'protected_hashes.json')
    protected.update({str(p):sha(p) for p in V2.rglob('*') if p.is_file()})
    for name,h in protected.items():assert sha(name)==h,name
    source=pd.read_csv(V2/'development_manifest.csv');assert sha(V2/'development_manifest.csv')==cfg['manifest_sha256']
    good=source[source.experiment_eligible].copy();tr=good[good.split=='train'];va=good[good.split=='validation']
    assert len(tr)==456 and len(va)==152 and set(good.split)=={'train','validation'}
    assert not set(tr.split_group_id)&set(va.split_group_id)
    old=read(ROOT/'hasil/model_a_training_v1/dataset_receipt.json')
    assert sha(ROOT/'hasil/model_a_preparation_v1/FREEZE.json')==old['source_split_freeze']
    geometry=pd.read_csv(ROOT/'hasil/model_a_finalization_v1/a2_working_manifest.csv').set_index('review_id')
    meta=pd.read_csv(ROOT/'hasil/model_a_training_v1/a2_tabular_development.csv').set_index('L_ID')
    train_sides=[max(np.diff(np.array(json.loads(geometry.loc[i,'crop_bbox'])).reshape(2,2),axis=0).flatten()) for i in tr.id]
    canvas=2**math.ceil(math.log2(max(train_sides)))
    prep=dict(method='fixed_native_pixel_canvas_v1',canvas_size=canvas,cnn_size=224,padding_rgb=[127,127,127],
        selection='Smallest power of two >= maximum old ROI side among456 TRAIN IDs only',train_max_roi_side=int(max(train_sides)),
        target_used_for_canvas=False,validation_used_for_canvas=False,source_to_cnn_scale=224/canvas,
        geometry_policy='Retain whole old ROI at native pixel size; centre it on constant source-pixel canvas; pad outside old ROI to avoid exposing new ID/ruler pixels; one bilinear resize',
        limitation='No new context outside old clean ROI; residual defects inside that ROI may remain. Pixel scale is not calibrated physical size.')
    save(OUT/'preprocessing_config.json',prep)
    # Reproduce control on all152 original validation IDs, without fitting any model.
    obj=torch.load(V2/'best.pt',map_location='cpu',weights_only=False)
    model=engine.image_model().cuda();model.load_state_dict(obj['model'])
    y,p=engine.evaluate(model,va,cfg)
    stored=pd.read_csv(V2/'validation_predictions.csv').set_index('id').loc[va.id]
    difference=float(np.max(np.abs(p-stored.predicted_measured_weight_mg.to_numpy())))
    assert difference<.1,'Baseline prediction mismatch'
    measured=scores(y,p)
    for k in ['MAE_mg','RMSE_mg','bias_mg','R2']:assert abs(measured[k]-receipt['metrics'][k])<.01,k
    save(OUT/'v2_reproduction.json',dict(checkpoint_loaded=True,checkpoint_sha256=sha(V2/'best.pt'),original_152_metrics=measured,max_prediction_difference_mg=difference,baseline_retrained=False))
    stored.reset_index().to_csv(OUT/'v2_original_validation_predictions.csv',index=False)
    del model,obj;torch.cuda.empty_cache()
    print('v2 reproduced; building fixed-scale development crops',flush=True)
    (OUT/'prepared').mkdir(exist_ok=True);rows=[];geometries=[];archives={}
    try:
        for row in good.to_dict('records'):
            key=row['id'];g=geometry.loc[key];m=meta.loc[int(row['L_ID'])]
            assert m.split==row['split'] and m.split_group_id==row['split_group_id']
            assert abs(float(m.Weight)-row['measured_weight_g'])<1e-12
            roi=json.loads(g.crop_bbox);side=max(roi[2]-roi[0],roi[3]-roi[1])
            row['representation_a_path']=row['artifact_path'];row['representation_a_sha256']=row['artifact_sha256']
            row['matched_exclusion']=''
            if side>canvas:
                row['experiment_eligible']=False;row['matched_exclusion']='FULL_ROI_EXCEEDS_TRAIN_SELECTED_CANVAS';rows.append(row);continue
            assert sha(ROOT/row['artifact_path'])==row['artifact_sha256']
            archive=ROOT/m.archive_path
            if str(archive) not in archives:archives[str(archive)]=zipfile.ZipFile(archive)
            raw=archives[str(archive)].read(m.archive_member)
            assert hashlib.sha256(raw).hexdigest()==row['source_sha256']==m.image_sha256==g.image_sha256
            with Image.open(io.BytesIO(raw)) as im:b,info=fixed_canvas(im,roi,canvas)
            path=OUT/'prepared'/(key+'.png');b.save(path)
            row.update(artifact_path=path.relative_to(ROOT).as_posix(),artifact_sha256=sha(path),
                archive_path=m.archive_path,archive_member=m.archive_member,native_roi_long_side=side,
                native_roi_area=(roi[2]-roi[0])*(roi[3]-roi[1]),scale_factor=224/canvas)
            info.update(id=key,split=row['split'],source_sha256=row['source_sha256'],archive_path=m.archive_path,archive_member=m.archive_member,prepared_sha256=row['artifact_sha256'])
            geometries.append(info);rows.append(row)
    finally:
        for z in archives.values():z.close()
    df=pd.DataFrame(rows);df.to_csv(OUT/'development_manifest.csv',index=False)
    save(OUT/'geometry.json',geometries)
    included=df[df.experiment_eligible];assert len(included[included.split=='train'])==456
    assert included[included.split=='validation'].shape[0]>0
    # Geometry-only selection of representative previews: shortest/longest ROI per dev batch.
    representatives=[]
    for _,g in included.groupby(['split','Batch_ID']):representatives.extend([g.nsmallest(1,'native_roi_long_side').iloc[0],g.nlargest(1,'native_roi_long_side').iloc[0]])
    selected=pd.DataFrame(representatives).drop_duplicates('id');selected[['id','split','Batch_ID','native_roi_long_side']].to_csv(OUT/'preview_index.csv',index=False)
    (OUT/'previews').mkdir(exist_ok=True)
    for start in range(0,len(selected),6):
        page=Image.new('RGB',(1024,900),'white');draw=ImageDraw.Draw(page)
        for i,r in enumerate(selected.iloc[start:start+6].itertuples()):
            x=(i%2)*512;y0=(i//2)*300
            with Image.open(ROOT/r.representation_a_path) as im:page.paste(im.resize((224,224),Image.Resampling.BILINEAR),(x,y0+60))
            with Image.open(ROOT/r.artifact_path) as im:page.paste(im,(x+256,y0+60))
            draw.text((x+4,y0+4),f'{r.id} {r.split} {r.Batch_ID} ROI {r.native_roi_long_side}px',font=FONT,fill='black')
            draw.text((x+4,y0+28),'A: normalized ROI      B: fixed native scale',font=FONT,fill='black')
        page.save(OUT/'previews'/f'{start//6+1:02}.jpg',quality=95)
    coverage=[]
    for (split,batch),g in df.groupby(['split','Batch_ID']):
        matched=g[g.experiment_eligible]
        coverage.append(dict(split=split,batch=batch,original_n=len(g),matched_n=len(matched),excluded_n=len(g)-len(matched),
            min_weight_mg=float(matched.measured_weight_g.min()*1000) if len(matched) else None,
            max_weight_mg=float(matched.measured_weight_g.max()*1000) if len(matched) else None))
    pd.DataFrame(coverage).to_csv(OUT/'coverage_by_batch.csv',index=False)
    df.assign(weight_range=pd.cut(df.measured_weight_g*1000,[-np.inf,180,240,280,np.inf])).groupby(['split','weight_range','experiment_eligible'],observed=True).size().rename('n').to_csv(OUT/'coverage_by_weight.csv')
    # All training hyperparameters and train-only target normalization inherited verbatim.
    new=dict(cfg);new.update(version='model_a2_training_v3',manifest_sha256=sha(OUT/'development_manifest.csv'),
        validation_n=int((included.split=='validation').sum()),adapter_sha256=sha(__file__),preprocessing_sha256=sha(OUT/'preprocessing_config.json'),
        crop_contract='Raw single-larva source plus reviewed source-coordinate ROI, or a prepared v3 fixed-scale224x224 image',
        existing_checkpoint_note='Reuse v2 control without retraining. Experimental input representation only; native pixel scale is not physical scale.')
    save(OUT/'config.json',new);save(OUT/'protected_hashes.json',protected)
    save(OUT/'preprocessing_receipt.json',dict(train_n=int((included.split=='train').sum()),validation_n=int((included.split=='validation').sum()),
        excluded_ids=df.loc[~df.experiment_eligible,['id','matched_exclusion']].to_dict('records'),
        preserved_full_old_roi_count=len(geometries),new_context_exposed=False,fixed_scale=224/canvas,
        files={n:sha(OUT/n) for n in ['preprocessing_config.json','development_manifest.csv','geometry.json','config.json','preview_index.csv','v2_reproduction.json']}))
    save(OUT/'status.json',dict(state='AWAITING_PREVIEW_CHECK',train_n=len(tr),validation_n=len(va)))
    print('Prepared',len(included),'matched crops and',len(selected),'preview cases',flush=True)

def apply_visual_review():
    """Apply documented development-only visual holds before any training; preserve pre-review drafts."""
    assert not (OUT/'best.pt').exists() and not (OUT/'last.pt').exists()
    review=read(OUT/'visual_preprocessing_check.json')
    assert review['decision']=='GO_WITH_DOCUMENTED_TRAIN_EXCLUSION'
    df=pd.read_csv(OUT/'development_manifest.csv');excluded=review['excluded_ids']
    assert set(excluded).issubset(set(df.id))
    for name in ['development_manifest.csv','config.json','preprocessing_receipt.json']:
        path=OUT/name;draft=path.with_name(path.stem+'.pre_review'+path.suffix)
        if not draft.exists():draft.write_bytes(path.read_bytes())
    df['matched_exclusion']=df['matched_exclusion'].fillna('').astype('string')
    for ident,reason in excluded.items():
        assert df.loc[df.id.eq(ident),'split'].item()=='train'
        df.loc[df.id.eq(ident),'experiment_eligible']=False
        df.loc[df.id.eq(ident),'matched_exclusion']=reason
    df.to_csv(OUT/'development_manifest.csv',index=False)
    good=df[df.experiment_eligible]
    cfg=read(OUT/'config.json');cfg.update(train_n=int(good.split.eq('train').sum()),validation_n=int(good.split.eq('validation').sum()),
        manifest_sha256=sha(OUT/'development_manifest.csv'),adapter_sha256=sha(__file__),
        controlled_comparison_exception='V3 excludes train A2_0972 after actual preview showed ruler ticks touching body. V2 trained456; v3 trains455. Same152 validation IDs and all hyperparameters, including original456-train target normalization. No v2 retraining; result cannot isolate preprocessing alone.')
    save(OUT/'config.json',cfg)
    receipt=read(OUT/'preprocessing_receipt.json');receipt.update(train_n=cfg['train_n'],validation_n=cfg['validation_n'],
        excluded_ids=df.loc[~df.experiment_eligible,['id','matched_exclusion']].to_dict('records'),
        controlled_comparison_exception=cfg['controlled_comparison_exception'])
    receipt['files'].update({name:sha(OUT/name) for name in receipt['files']})
    receipt['files']['visual_preprocessing_check.json']=sha(OUT/'visual_preprocessing_check.json')
    save(OUT/'preprocessing_receipt.json',receipt)
    coverage=[]
    for (split,batch),g in df.groupby(['split','Batch_ID']):
        matched=g[g.experiment_eligible]
        coverage.append(dict(split=split,batch=batch,original_n=len(g),matched_n=len(matched),excluded_n=len(g)-len(matched),
            min_weight_mg=float(matched.measured_weight_g.min()*1000) if len(matched) else None,
            max_weight_mg=float(matched.measured_weight_g.max()*1000) if len(matched) else None))
    pd.DataFrame(coverage).to_csv(OUT/'coverage_by_batch.csv',index=False)
    df.assign(weight_range=pd.cut(df.measured_weight_g*1000,[-np.inf,180,240,280,np.inf])).groupby(['split','weight_range','experiment_eligible'],observed=True).size().rename('n').to_csv(OUT/'coverage_by_weight.csv')
    save(OUT/'status.json',dict(state='READY_FOR_SANITY',train_n=cfg['train_n'],validation_n=cfg['validation_n'],excluded_ids=list(excluded)))
    print('Visual correction applied before training:',cfg['train_n'],cfg['validation_n'])

def verify_ready():
    cfg=read(OUT/'config.json');receipt=read(OUT/'preprocessing_receipt.json')
    assert cfg['adapter_sha256']==sha(__file__)
    assert read(OUT/'visual_preprocessing_check.json')['decision'] in ['GO','GO_WITH_DOCUMENTED_TRAIN_EXCLUSION']
    for name,h in receipt['files'].items():assert sha(OUT/name)==h,name
    for r in pd.read_csv(OUT/'development_manifest.csv').query('experiment_eligible').itertuples():assert sha(ROOT/r.artifact_path)==r.artifact_sha256

def predict_measured_weight(image,roi_box=None,prepared=False,device='cpu'):
    try:
        if isinstance(image,Image.Image):im=image.copy()
        else:
            with Image.open(image) as src:src.load();im=src.copy()
        if not prepared:
            if roi_box is None:raise ValueError('Raw source requires a reviewed source-coordinate ROI; no automatic re-localization')
            im,_=fixed_canvas(im,roi_box,read(OUT/'preprocessing_config.json')['canvas_size'])
        x=tensor(im,224).unsqueeze(0).to(device)
    except (OSError,ValueError,TypeError) as exc:raise ValueError('Invalid source/ROI or prepared v3 image') from exc
    cp=torch.load(OUT/'best.pt',map_location='cpu',weights_only=False);cfg=cp['config']
    model=engine.image_model().to(device);model.load_state_dict(cp['model']);model.eval()
    with torch.inference_mode():value=float(model(x).item()*cfg['target_std_mg']+cfg['target_mean_mg'])
    assert np.isfinite(value)
    return dict(predicted_measured_weight_mg=value,model_version=cfg['version'],status=[engine.STATUS,'RESEARCH_PROTOTYPE','NOT_FIELD_VALIDATED'],
        preprocessing='fixed-native-pixel-canvas, outside old ROI neutral padded',pixel_to_mm=None,
        limitations=['No wet/dry protocol confirmation','No arbitrary multi-larva or A1 crop support','No confidence interval'])

def finish(cfg,df,tr,va,history):
    cp=torch.load(OUT/'best.pt',map_location='cpu',weights_only=False);model=engine.image_model().cuda();model.load_state_dict(cp['model'])
    y,p=engine.evaluate(model,va,cfg)
    pred=va[['id','L_ID','Batch_ID','split_group_id','native_roi_long_side','native_roi_area']].copy()
    pred['measured_weight_mg']=y;pred['v3_prediction_mg']=p
    control=pd.read_csv(OUT/'v2_original_validation_predictions.csv')[['id','predicted_measured_weight_mg']].rename(columns={'predicted_measured_weight_mg':'v2_prediction_mg'})
    pred=pred.merge(control,on='id',validate='one_to_one');assert len(pred)==len(va)
    for version in ['v2','v3']:pred[version+'_error_mg']=pred[version+'_prediction_mg']-pred.measured_weight_mg
    pred['paired_absolute_error_change_mg']=abs(pred.v3_error_mg)-abs(pred.v2_error_mg)
    pred.to_csv(OUT/'validation_predictions.csv',index=False)
    def compare(g):return {v:scores(g.measured_weight_mg,g[v+'_prediction_mg']) for v in ['v2','v3']}
    ranges={'below180':pred.measured_weight_mg<180,'180_to240':pred.measured_weight_mg.between(180,240),'above240':pred.measured_weight_mg>240,'at_least280':pred.measured_weight_mg>=280}
    groups={str(k):compare(g) for k,g in pred.groupby('split_group_id')}
    delta=pred.paired_absolute_error_change_mg
    group_deltas=pred.groupby('split_group_id').paired_absolute_error_change_mg.mean()
    metrics=dict(overall=compare(pred),original_152_v2=read(OUT/'v2_reproduction.json')['original_152_metrics'],
        by_weight_range={name:compare(pred[mask]) for name,mask in ranges.items() if mask.any()},
        by_batch={str(k):compare(g) for k,g in pred.groupby('Batch_ID')},by_primary_group=groups,
        paired=dict(mean_absolute_error_change_mg=float(delta.mean()),median_change_mg=float(delta.median()),
            improved_images=int((delta<0).sum()),worsened_images=int((delta>0).sum()),
            primary_group_mean_changes=group_deltas.to_dict(),group_change_range_mg=[float(group_deltas.min()),float(group_deltas.max())],
            uncertainty='Only two primary validation groups; descriptive paired differences, no image-iid confidence interval or significance claim'),
        native_roi_size_error_correlation={v:float(pred.native_roi_long_side.corr(pred[v+'_error_mg'])) for v in ['v2','v3']},
        validation_n=len(pred),primary_groups=pred.split_group_id.nunique(),best_epoch=cp['epoch'],completed_epochs=len(history),
        training_duration_seconds=float(sum(r['seconds'] for r in history)),
        peak_allocated_MiB=torch.cuda.max_memory_allocated()/2**20,peak_reserved_MiB=torch.cuda.max_memory_reserved()/2**20,
        gpu=torch.cuda.get_device_name(0),controlled_comparison_exception=cfg.get('controlled_comparison_exception'),status=engine.STATUS,final_test_used=False)
    small=metrics['by_weight_range'].get('below180');heavy=metrics['by_weight_range'].get('above240')
    metrics['decision']=dict(primary_MAE_improved=metrics['overall']['v3']['MAE_mg']<metrics['overall']['v2']['MAE_mg'],
        heavy_MAE_improved=heavy['v3']['MAE_mg']<heavy['v2']['MAE_mg'] if heavy else None,
        heavy_absolute_bias_improved=abs(heavy['v3']['bias_mg'])<abs(heavy['v2']['bias_mg']) if heavy else None,
        small_MAE_change_mg=small['v3']['MAE_mg']-small['v2']['MAE_mg'] if small else None,
        materiality='No prespecified material-degradation threshold; report exact small-larva change without inventing a cutoff')
    save(OUT/'metrics.json',metrics)
    pd.DataFrame(metrics['overall']).T.to_csv(OUT/'metrics_comparison.csv')
    engine.regression_plot(y,p,OUT/'v3_regression_diagnostics.png')
    import matplotlib.pyplot as plt
    h=pd.DataFrame(history);fig,ax=plt.subplots(1,2,figsize=(10,3))
    ax[0].plot(h.epoch,h.train_normalized_MSE,label='train');ax[0].plot(h.epoch,h.validation_normalized_MSE,label='validation');ax[0].legend()
    ax[1].scatter(pred.measured_weight_mg,delta,s=12);ax[1].axhline(0,color='black');ax[1].set(xlabel='Measured weight mg',ylabel='Absolute error v3 minus v2 mg')
    fig.tight_layout();fig.savefig(OUT/'learning_and_paired_errors.png');plt.close(fig)
    top=pred.assign(abs_error=abs(pred.v3_error_mg)).nlargest(8,'abs_error');top.to_csv(OUT/'targeted_review.csv',index=False)
    probe=va.iloc[0];result=predict_measured_weight(ROOT/probe.artifact_path,prepared=True)
    assert abs(result['predicted_measured_weight_mg']-float(pred.set_index('id').loc[probe.id,'v3_prediction_mg']))<.1
    geo={g['id']:g for g in read(OUT/'geometry.json')}[probe.id]
    with zipfile.ZipFile(ROOT/geo['archive_path']) as z:
        with Image.open(io.BytesIO(z.read(geo['archive_member']))) as im:raw=predict_measured_weight(im,roi_box=geo['roi_bbox'])
    assert abs(result['predicted_measured_weight_mg']-raw['predicted_measured_weight_mg'])<1e-5
    try:predict_measured_weight(Image.new('RGB',(512,512)),prepared=True)
    except ValueError:pass
    else:raise AssertionError('Normalized v2 crop must not silently enter v3 inference')
    save(OUT/'inference_smoke.json',dict(passed=True,raw_prepared_match=True,v2_crop_rejected=True,development_id=probe.id,result=result))
    for name,hsh in read(OUT/'protected_hashes.json').items():assert sha(name)==hsh,name
    a=metrics['overall']['v2'];b=metrics['overall']['v3'];prep=read(OUT/'preprocessing_config.json')
    subgroup_lines=['| Range / batch | n | v2 MAE | v3 MAE | v2 bias | v3 bias |','|---|---:|---:|---:|---:|---:|']
    for name,comp in {**metrics['by_weight_range'],**metrics['by_batch']}.items():
        aa,bb=comp['v2'],comp['v3']
        subgroup_lines.append(f"| {name} | {bb['n']} | {aa['MAE_mg']:.3f} | {bb['MAE_mg']:.3f} | {aa['bias_mg']:.3f} | {bb['bias_mg']:.3f} |")
    subgroup_table='\n'.join(subgroup_lines)
    report=f'''# A2 v2 versus v3 — controlled native pixel-scale experiment

## Experiment Integrity
Frozen reservations verified; matched train={len(tr)}, validation={len(va)}, validation primary groups={metrics['primary_groups']}. No test/quarantine image or target was used. V2 weights reloaded and all152 original validation predictions reproduced; no v2 retraining. Prior artifacts/A1/B1 hashes PASS. Exact IDs, source image hashes, crop hashes and exclusions are in development_manifest.csv and preprocessing_receipt.json. Full original152 baseline is retained separately; paired comparison uses identical eligible validation IDs.

Comparison limitation: {cfg.get('controlled_comparison_exception','None')}. This is a targeted experiment with a documented population exception, not a perfectly isolated preprocessing-only comparison.

## Preprocessing
Canvas={prep['canvas_size']} native pixels square, chosen as the smallest power of two covering maximum TRAIN ROI side={prep['train_max_roi_side']}px, with no Weight or validation-based canvas selection. Existing source ROI centred at native size; every source pixel inside it preserved before resizing. Outside that old ROI is constant127 padding, including any canvas area outside the photo. This prevents new ID/ruler/background exposure. One bilinear conversion to224px, fixed scale={prep['source_to_cnn_scale']}. No body reconstruction, rotation/stretch or physical calibration. Body retention is conditional on the existing ROI being complete; all old ROI pixels retained geometrically. Representative actual visual findings: visual_preprocessing_check.json. Source context inside ROI and existing defects remain; this is not a certified body mask. Geometry/padding edges may themselves encode ROI size. This comparison changes representation/padding/relative occupancy, not proof of a single biological mechanism.

## Training
MobileNetV3 Small pretrained ImageNet, same regression head, seed, optimizer, MSE, target train mean/std,224px,batch8,AMP scale128,5 head epochs then last3 blocks, frozen BN, max30/patience7 as v2. No scheduler. Completed {len(history)} epochs; best {cp['epoch']}; measured epoch duration sum {metrics['training_duration_seconds']:.1f}s. Best/last/previous checkpoints include full optimizer, scaler, epoch/best/stale/history and RNG state. Only condition B trained; a new version reuses the frozen v2 engine in memory without editing its file. Same run command resumes compatible checkpoint.

## Validation
| Matched validation | MAE mg | RMSE mg | Bias mg | R² |
|---|---:|---:|---:|---:|
| v2 control | {a['MAE_mg']:.3f} | {a['RMSE_mg']:.3f} | {a['bias_mg']:.3f} | {a['R2']:.4f} |
| v3 fixed scale | {b['MAE_mg']:.3f} | {b['RMSE_mg']:.3f} | {b['bias_mg']:.3f} | {b['R2']:.4f} |

Paired mean absolute-error change (negative improves)={delta.mean():.3f}mg; median={delta.median():.3f}mg. Group mean changes={json.dumps(group_deltas.to_dict())}. With only two independent validation groups, no image-independent confidence interval or reliable significance conclusion is claimed. Weight ranges <180,180–240,>240,≥280 and batch/group metrics are in metrics.json. Largest errors in targeted_review.csv; plots in v3_regression_diagnostics.png and learning_and_paired_errors.png. No automatic claims of expert visual review of model failures.

{subgroup_table}

Native ROI side versus signed error correlations: {json.dumps(metrics['native_roi_size_error_correlation'])}. These are associations, not causal evidence. Padding/background occupancy changes with native ROI dimensions and may remain a shortcut. No new source background was exposed.

## Decision
Heavy-larva MAE improved: {metrics['decision']['heavy_MAE_improved']}; heavy absolute bias improved: {metrics['decision']['heavy_absolute_bias_improved']}. Small-larva MAE change (v3 minus v2): {metrics['decision']['small_MAE_change_mg']}mg. No prespecified materiality threshold; do not equate a tiny improvement with biological significance.

Primary lower-MAE criterion: {'PASS' if b['MAE_mg']<a['MAE_mg'] else 'FAIL'}. Absolute overall bias improved: {abs(b['bias_mg'])<abs(a['bias_mg'])}. Heavy-larva and small-larva tradeoffs must be read together in metrics.json, not hidden by an aggregate gain. Numerical change does not establish scientific significance, causal scale learning, field validity or calibrated millimeters. If gains are consistent across weight ranges/groups, next priority is calibration and independent cohorts; if gains are weak/inconsistent, recover usable batch coverage and verify scale/crop quality before changing architecture. All outcomes/checkpoints retained; no automatic additional experiment.

## Use
From repository root: `.agents/skills/fiscycle-bsf-ai/.venv-cuda/Scripts/python.exe -B .agents/skills/fiscycle-bsf-ai/a2_scale_v3.py run` resumes or exits if complete. `status` reports the persistent state. `predict IMAGE --prepared` accepts only a v3 prepared224px image. For a full single-larva source use `predict IMAGE --roi X0 Y0 X1 Y1` with source-coordinate ROI reviewed for body completeness/shortcut absence. A v2 normalized crop cannot recover native scale and is rejected. Inference smoke passed raw versus prepared agreement. Research status and measured-weight naming remain explicit; no A1 integration or confidence intervals.
'''
    (OUT/'COMPARISON_REPORT.md').write_text(report,encoding='utf-8')
    save(OUT/'COMPLETE.json',dict(completed_at=engine.now(),status=engine.STATUS,metrics=metrics['overall'],best_epoch=cp['epoch'],epochs_completed=len(history),
        protected_integrity='PASS',inference_smoke='PASS',adapter_sha256=sha(__file__),
        files={n:sha(OUT/n) for n in ['best.pt','last.pt','config.json','preprocessing_config.json','development_manifest.csv','metrics.json','validation_predictions.csv','COMPARISON_REPORT.md']}))
    engine.status('COMPLETED',epochs_completed=len(history),best_epoch=cp['epoch'],metrics=metrics['overall'])

def install_engine():
    engine.OUT=OUT;engine.prepare=verify_ready;engine.image_tensor=tensor;engine.finish=finish

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','sanity','run','status','predict']);p.add_argument('image',nargs='?');p.add_argument('--prepared',action='store_true');p.add_argument('--roi',type=int,nargs=4);a=p.parse_args()
    if a.command=='prepare':prepare()
    elif a.command=='status':print(json.dumps(read(OUT/'status.json'),indent=2))
    elif a.command=='predict':print(json.dumps(predict_measured_weight(a.image,a.roi,a.prepared),indent=2))
    else:
        install_engine();verify_ready()
        if a.command=='run':engine.run()
        else:
            cfg=read(OUT/'config.json');_,tr,_=engine.data();engine.sanity(cfg,tr)
