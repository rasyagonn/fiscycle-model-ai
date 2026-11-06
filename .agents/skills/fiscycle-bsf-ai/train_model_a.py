"""Bounded Model A experiments. Development partitions only; no final-test loader."""
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'hasil/model_a_training_v1'
os.environ.setdefault('YOLO_CONFIG_DIR',str(OUT/'ultralytics_settings'))
os.environ.setdefault('MPLBACKEND','Agg')
os.environ.setdefault('OMP_NUM_THREADS','4')
import argparse, json, random, time, shutil, platform, importlib.metadata
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd
from PIL import Image,ImageOps,ImageDraw
import torch
from torch import nn
from torch.utils.data import Dataset,DataLoader
from torchvision.models import mobilenet_v3_small,MobileNet_V3_Small_Weights
from torchvision.transforms import functional as TF
import finalize_model_a as f

SEED=20261105
STATUS='EXPLORATORY_UNVERIFIED_LABELS'
PREP=ROOT/'hasil/model_a_preparation_v1'
REVIEW=ROOT/'hasil/model_a_review_v3'
def save(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False,default=str)+'\n',encoding='utf-8')
def seed():
    random.seed(SEED);np.random.seed(SEED);torch.manual_seed(SEED)
    torch.set_num_threads(4)
def metrics(y,p):
    y=np.asarray(y);p=np.asarray(p);d=p-y
    assert np.isfinite(d).all()
    return dict(n=len(y),MAE_mg=float(np.abs(d).mean()),RMSE_mg=float(np.sqrt((d*d).mean())),bias_mg=float(d.mean()))
def check_groups(df):
    a=set(df.loc[df.split=='train','split_group_id']);b=set(df.loc[df.split=='validation','split_group_id'])
    assert not a&b and set(df.split)<= {'train','validation'}

def prepare():
    assert not (OUT/'dataset_receipt.json').exists(),'Prepared version already exists'
    OUT.mkdir(parents=True,exist_ok=True)
    print('Verifying frozen inputs and raw hashes...',flush=True)
    f.verify_package(full=True)
    receipt=f.read_json(REVIEW/'FREEZE.json')
    for name,h in receipt['files'].items():assert f.sha(REVIEW/name)==h,name
    old=pd.read_csv(REVIEW/'eligibility_manifest.csv',keep_default_na=False).set_index('id')
    items=[e for e in f.read_json(f.OUT/'review_items.json') if e['split'] in ['train','validation']]
    rows=[]
    for e in items:
        if e['track']!='A1':continue
        r=old.loc[e['id']].to_dict();r['id']=e['id'];reasons=[]
        polys=f.parse_labels(f.OUT/e['mapped_label_path'])
        for p in polys:
            # Closing vertex equals first: remove redundant closing coordinate only, not instance.
            while len(p['points'])>3 and p['points'][-1]==p['points'][0]:p['points'].pop()
        try:f.validate_polygons(polys,enforce_visibility=True)
        except ValueError as exc:reasons.append('INVALID_OR_BELOW_VISIBILITY_FLOOR:'+str(exc))
        if r.get('individual_decision')=='reject':reasons.append('EXPLICIT_HUMAN_REJECT')
        if not polys:reasons.append('EMPTY_POSITIVE_LABEL')
        r.update(experiment_eligible=not reasons,experiment_exclusion='|'.join(reasons),
            experiment_status=STATUS,known_annotation_issues=e['issues'],annotation_count=len(polys))
        if not reasons:
            split='train' if e['split']=='train' else 'val'
            image=OUT/'a1_dataset/images'/split/(e['id']+'.jpg')
            label=OUT/'a1_dataset/labels'/split/(e['id']+'.txt')
            image.parent.mkdir(parents=True,exist_ok=True);label.parent.mkdir(parents=True,exist_ok=True)
            assert f.sha(ROOT/e['source_path'])==e['source_sha256']
            shutil.copyfile(ROOT/e['source_path'],image)
            label.write_text(f.polygon_text(polys,(ROOT/e['source_label_path']).read_text().splitlines()))
            r.update(experiment_image=str(image),experiment_label=str(label),experiment_label_sha256=f.sha(label))
        rows.append(r)
    a1=pd.DataFrame(rows);check_groups(a1)
    a1.to_csv(OUT/'a1_development_manifest.csv',index=False)
    data=dict(path=(OUT/'a1_dataset').as_posix(),train='images/train',val='images/val',names={0:'visible_bsf_larva'})
    import yaml
    (OUT/'a1_dataset/data.yaml').write_text(yaml.safe_dump(data))
    # A separate tiny train subset; validation still uses only frozen development validation.
    for split,count in [('train',12),('val',8)]:
        source=OUT/'a1_dataset/images'/split
        selected=sorted(source.glob('*.jpg'))[:count]
        (OUT/f'a1_sanity_{split}.txt').write_text('\n'.join(str(p) for p in selected)+'\n')
    (OUT/'a1_sanity.yaml').write_text(yaml.safe_dump(dict(path=str(OUT),train=str(OUT/'a1_sanity_train.txt'),val=str(OUT/'a1_sanity_val.txt'),names={0:'visible_bsf_larva'})))
    full=pd.read_csv(PREP/'a2_manifest.csv');dev=full[full.split.isin(['train','validation'])].copy()
    assert len(dev)==1114;check_groups(dev)
    # Morphometric references do not depend on crop approval.
    dev.to_csv(OUT/'a2_tabular_development.csv',index=False)
    a2=old.reset_index();a2=a2[(a2.track=='A2')&a2.split.isin(['train','validation'])].copy()
    a2['experiment_eligible']=a2.status.eq('APPROVED_CONDITIONAL_RESEARCH')
    a2['experiment_status']=STATUS
    a2['experiment_exclusion']=np.where(a2.experiment_eligible,'',a2.hold_reasons)
    for r in a2[a2.experiment_eligible].itertuples():
        assert f.sha(ROOT/r.artifact_path)==r.artifact_sha256
        assert abs(float(r.measured_weight_g)-float(dev.set_index('L_ID').loc[int(float(r.L_ID)),'Weight']))<1e-10
    check_groups(a2);a2.to_csv(OUT/'a2_development_manifest.csv',index=False)
    save(OUT/'dataset_receipt.json',dict(status=STATUS,seed=SEED,recorded_at=datetime.now(timezone(timedelta(hours=7))).isoformat(),
        source_split_freeze=f.sha(PREP/'FREEZE.json'),review_v3_freeze=f.sha(REVIEW/'FREEZE.json'),
        a1_counts=a1[a1.experiment_eligible].groupby('split').size().to_dict(),a2_counts=a2[a2.experiment_eligible].groupby('split').size().to_dict(),
        a1_policy='Keep maximum development set with valid visible geometry; include incomplete/unreviewed labels; exclude explicit rejects. Preserve each mapped source instance, no speculative duplicate removal. Unannotated larvae can be trained as background.',
        a2_policy='Primary uses v3 AI-screened/recorded-review clean subset, no target-based crop selection. Known failures and suspected shortcuts retained in exclusion ledger.',
        approval_fields_modified=False,test_used=False,quarantine_used=False,
        files={name:f.sha(OUT/name) for name in ['a1_development_manifest.csv','a2_development_manifest.csv','a2_tabular_development.csv','a1_dataset/data.yaml']},
        protected_b1=f.read_json(PREP/'protected_integrity.json')))
    save(OUT/'environment.json',dict(python=platform.python_version(),platform=platform.platform(),torch=torch.__version__,
        cuda_available=torch.cuda.is_available(),device='cpu',threads=4,seed=SEED,
        packages={n:importlib.metadata.version(n) for n in ['torch','torchvision','ultralytics','numpy','pandas','scikit-learn','Pillow','matplotlib']},
        hardware_note='NVIDIA RTX 2050 4GB present; installed torch is CPU build; system RAM 7.7GB, about 1GB available at inspection'))
    print(json.dumps(f.read_json(OUT/'dataset_receipt.json')['a1_counts']),flush=True)

def baselines():
    from sklearn.dummy import DummyRegressor
    from sklearn.linear_model import LinearRegression,Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    import joblib
    df=pd.read_csv(OUT/'a2_tabular_development.csv');tr=df[df.split=='train'];va=df[df.split=='validation']
    chosen=pd.read_csv(OUT/'a2_development_manifest.csv');ids=set(chosen.loc[chosen.experiment_eligible & chosen.split.eq('validation'),'L_ID'].astype(int))
    dest=OUT/'a2_baselines';dest.mkdir(exist_ok=True);all_metrics={};pred=va[['L_ID','Batch_ID','split_group_id','Length']].copy();pred['measured_weight_mg']=va.Weight*1000
    for name,model in [('mean',DummyRegressor(strategy='mean')),('length_linear',LinearRegression()),('length_ridge',make_pipeline(StandardScaler(),Ridge(alpha=1.0)))]:
        model.fit(tr[['Length']],tr.Weight*1000);p=model.predict(va[['Length']]);pred[name]=p
        joblib.dump(model,dest/(name+'.joblib'))
        all_metrics[name]={}
        for scope,mask in [('full_validation',np.ones(len(va),bool)),('image_eligible_validation',va.L_ID.isin(ids).to_numpy())]:
            all_metrics[name][scope]=metrics((va.Weight*1000).to_numpy()[mask],p[mask])
        all_metrics[name]['by_batch']={b:metrics(g.measured_weight_mg,g[name]) for b,g in pred.groupby('Batch_ID')}
    for name in all_metrics:
        for scope in ['full_validation','image_eligible_validation']:
            all_metrics[name][scope]['MAE_improvement_vs_mean_pct']=100*(1-all_metrics[name][scope]['MAE_mg']/all_metrics['mean'][scope]['MAE_mg'])
    pred.to_csv(dest/'validation_predictions.csv',index=False);save(dest/'metrics.json',all_metrics)
    regression_plot(pred.measured_weight_mg,pred.length_linear,dest/'length_diagnostics.png')
    save(dest/'config.json',dict(train_n=len(tr),validation_n=len(va),features=['Length'],weight_conversion='g * 1000 = mg',ridge_alpha=1,scaler_fit='train_only',status=STATUS))
    print(json.dumps(all_metrics,indent=2),flush=True)

def regression_plot(y,p,path):
    import matplotlib.pyplot as plt
    y=np.asarray(y);p=np.asarray(p);fig,ax=plt.subplots(1,3,figsize=(12,3.5))
    ax[0].scatter(y,p,s=10);lo=min(y.min(),p.min());hi=max(y.max(),p.max());ax[0].plot([lo,hi],[lo,hi],'k--');ax[0].set(xlabel='Measured mg',ylabel='Predicted mg')
    ax[1].scatter(y,p-y,s=10);ax[1].axhline(0,color='k');ax[1].set(xlabel='Measured mg',ylabel='Error mg')
    ax[2].hist(p-y,bins=20);ax[2].set(xlabel='Error mg',ylabel='Count');fig.tight_layout();fig.savefig(path,dpi=140);plt.close(fig)

def a1_train(sanity=False):
    seed()
    from ultralytics import YOLO
    from ultralytics import settings
    settings.update({'sync':False,'wandb':False,'mlflow':False,'clearml':False,'comet':False,'dvc':False,'neptune':False,'tensorboard':False})
    name='a1_sanity' if sanity else 'a1_initial'
    assert not (OUT/name/'weights/best.pt').exists(),'Do not overwrite trained run'
    model=YOLO(str(OUT/'pretrained/yolo11n-seg.pt'))
    model.train(data=str(OUT/('a1_sanity.yaml' if sanity else 'a1_dataset/data.yaml')),
        project=str(OUT),name=name,exist_ok=True,epochs=1 if sanity else 25,patience=7,
        imgsz=320,batch=2,device='cpu',workers=0,cache=False,seed=SEED,deterministic=True,
        optimizer='AdamW',lr0=0.001,lrf=0.05,weight_decay=0.0005,warmup_epochs=1,
        overlap_mask=False,mask_ratio=2,amp=False,mosaic=0.0,mixup=0.0,copy_paste=0.0,
        degrees=10,translate=0.05,scale=0.15,fliplr=0.5,flipud=0.5,hsv_h=0.01,hsv_s=0.15,hsv_v=0.15,
        plots=True,save=True,verbose=False,save_period=-1,close_mosaic=0,freeze=10 if sanity else None)
    loaded=YOLO(str(OUT/name/'weights/best.pt'))
    image=next((OUT/'a1_dataset/images/val').glob('*.jpg'))
    result=loaded.predict(str(image),imgsz=320,conf=0.05,device='cpu',verbose=False)[0]
    result.save(filename=str(OUT/name/'reload_prediction.jpg'))
    save(OUT/name/'sanity_checks.json',dict(reloaded=True,instances=len(result.boxes),has_masks=result.masks is not None,
        source=str(image),training_losses_finite=bool(np.isfinite(pd.read_csv(OUT/name/'results.csv').select_dtypes('number')).all().all()),status='DIAGNOSTIC_ONLY' if sanity else STATUS))
    if sanity:
        low=loaded.predict(str(image),imgsz=320,conf=0.001,device='cpu',verbose=False)[0]
        assert low.masks is not None and len(low.masks)>0,'Sanity mask-output check failed'
        low.save(filename=str(OUT/name/'low_threshold_mask_diagnostic.jpg'))
        checks=f.read_json(OUT/name/'sanity_checks.json')
        checks.update(mask_output_check_passed=True,diagnostic_confidence=0.001,diagnostic_mask_count=len(low.masks),
            note='Low-threshold output check is diagnostic only, not useful detection quality')
        save(OUT/name/'sanity_checks.json',checks)

class Crops(Dataset):
    def __init__(self,df,augment=False):self.df=df.reset_index(drop=True);self.augment=augment
    def __len__(self):return len(self.df)
    def __getitem__(self,i):
        r=self.df.iloc[i]
        with Image.open(ROOT/r.artifact_path) as im:im=im.convert('RGB').resize((160,160),Image.Resampling.BILINEAR)
        if self.augment:
            if random.random()<0.5:im=ImageOps.mirror(im)
            if random.random()<0.5:im=ImageOps.flip(im)
            im=im.transpose([Image.Transpose.ROTATE_90,Image.Transpose.ROTATE_180,Image.Transpose.ROTATE_270][random.randrange(3)]) if random.random()<0.5 else im
        x=TF.normalize(TF.to_tensor(im),[.485,.456,.406],[.229,.224,.225])
        return x,torch.tensor(float(r.measured_weight_g)*1000,dtype=torch.float32)

def image_model(pretrained=False):
    m=mobilenet_v3_small(weights=None)
    if pretrained:m.load_state_dict(torch.load(OUT/'pretrained/mobilenet_v3_small-047dcff4.pth',map_location='cpu',weights_only=True))
    m.classifier=nn.Sequential(nn.Linear(576,128),nn.Hardswish(),nn.Dropout(.2),nn.Linear(128,1))
    return m

def a2_train(sanity=False,improve=False):
    seed();name='a2_sanity' if sanity else ('a2_improved' if improve else 'a2_initial');dest=OUT/name
    assert not (dest/'best.pt').exists(),'Do not overwrite trained run'
    dest.mkdir(exist_ok=True)
    df=pd.read_csv(OUT/'a2_development_manifest.csv');df=df[df.experiment_eligible]
    tr=df[df.split=='train'];va=df[df.split=='validation']
    if sanity:tr=tr.head(16);va=va.head(8)
    model=image_model(pretrained=True)
    for p in model.features.parameters():p.requires_grad=False
    if improve:
        initial=torch.load(OUT/'a2_initial/best.pt',map_location='cpu',weights_only=False)
        model.load_state_dict(initial['state_dict'])
        for p in model.features[-3:].parameters():p.requires_grad=True
    mean=float((tr.measured_weight_g*1000).mean());std=float((tr.measured_weight_g*1000).std(ddof=0))
    opt=torch.optim.AdamW(filter(lambda p:p.requires_grad,model.parameters()),lr=0.0002 if improve else 0.001,weight_decay=.001)
    epochs=1 if sanity else (12 if improve else 20);patience=5
    config=dict(status=STATUS,architecture='mobilenet_v3_small',pretrained='ImageNet1K_V1',input_size=160,
        seed=SEED,epochs=epochs,patience=patience,train_n=len(tr),validation_n=len(va),target_mean_mg=mean,target_std_mg=std,
        output='predicted_measured_weight_mg',normalization_mean=[.485,.456,.406],normalization_std=[.229,.224,.225],
        mode='fine_tune_last_3_feature_blocks' if improve else 'frozen_backbone_trained_regression_head',
        augmentation='flips_and_90_degree_rotations' if improve else 'none',batch_size=16,learning_rate=0.0002 if improve else .001,
        pixel_scale='UNVERIFIED',wet_dry_protocol='UNKNOWN',early_stop='validation_MAE',test_used=False)
    save(dest/'config.json',config)
    trainloader=DataLoader(Crops(tr,augment=improve),batch_size=16,shuffle=True,num_workers=0,generator=torch.Generator().manual_seed(SEED))
    valloader=DataLoader(Crops(va),batch_size=16,shuffle=False,num_workers=0)
    best=float('inf');stale=0;history=[];finite_grad=False
    for ep in range(epochs):
        start=time.time();model.train();model.features.eval() # Freeze batch statistics on small shifted batches.
        loss_sum=0
        for x,y in trainloader:
            opt.zero_grad();z=model(x).flatten();loss=nn.functional.mse_loss(z,(y-mean)/std)
            assert torch.isfinite(loss);loss.backward()
            grads=[p.grad for p in model.parameters() if p.requires_grad and p.grad is not None]
            assert grads and all(torch.isfinite(g).all() for g in grads)
            finite_grad=True;nn.utils.clip_grad_norm_(model.parameters(),5);opt.step();loss_sum+=float(loss.detach())*len(x)
        model.eval();ys=[];ps=[]
        with torch.inference_mode():
            for x,y in valloader:ys.extend(y.tolist());ps.extend((model(x).flatten()*std+mean).tolist())
        scores=metrics(ys,ps);row=dict(epoch=ep+1,train_normalized_MSE=loss_sum/len(tr),seconds=time.time()-start,**scores);history.append(row)
        checkpoint=dict(state_dict=model.state_dict(),config=config,epoch=ep+1,validation=scores)
        torch.save(checkpoint,dest/'last.pt')
        if scores['MAE_mg']<best:
            best=scores['MAE_mg'];stale=0;torch.save(checkpoint,dest/'best.pt')
        else:stale+=1
        pd.DataFrame(history).to_csv(dest/'learning_curve.csv',index=False)
        print(name,json.dumps(row),flush=True)
        if stale>=patience:break
    reload=torch.load(dest/'best.pt',map_location='cpu',weights_only=False);model.load_state_dict(reload['state_dict']);model.eval();ps=[]
    with torch.inference_mode():
        for x,y in valloader:ps.extend((model(x).flatten()*std+mean).tolist())
    pred=va[['id','L_ID','Batch_ID','split_group_id','artifact_path','measured_weight_g']].copy();pred['measured_weight_mg']=pred.measured_weight_g*1000;pred['predicted_measured_weight_mg']=ps;pred['error_mg']=pred.predicted_measured_weight_mg-pred.measured_weight_mg
    pred.to_csv(dest/'validation_predictions.csv',index=False)
    save(dest/'metrics.json',dict(overall=metrics(pred.measured_weight_mg,ps),by_batch={b:metrics(g.measured_weight_mg,g.predicted_measured_weight_mg) for b,g in pred.groupby('Batch_ID')},best_epoch=reload['epoch'],completed_epochs=len(history),status=STATUS))
    regression_plot(pred.measured_weight_mg,ps,dest/'regression_diagnostics.png')
    import matplotlib.pyplot as plt
    hist=pd.DataFrame(history);fig,axes=plt.subplots(1,2,figsize=(9,3))
    axes[0].plot(hist.epoch,hist.train_normalized_MSE);axes[0].set(xlabel='Epoch',ylabel='Train normalized MSE')
    axes[1].plot(hist.epoch,hist.MAE_mg);axes[1].set(xlabel='Epoch',ylabel='Validation MAE mg')
    fig.tight_layout();fig.savefig(dest/'learning_curve.png',dpi=140);plt.close(fig)
    save(dest/'sanity_checks.json',dict(finite_gradients=finite_grad,checkpoint_reloaded=True,image_weight_binding_verified=True,predictions_finite=bool(np.isfinite(ps).all())))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','baselines','a1_sanity','a1_train','a2_sanity','a2_train','a2_improve'])
    args=parser.parse_args();seed()
    if args.stage=='prepare':prepare()
    elif args.stage=='baselines':baselines()
    elif args.stage.startswith('a1'):a1_train(args.stage=='a1_sanity')
    else:a2_train(args.stage=='a2_sanity',args.stage=='a2_improve')
