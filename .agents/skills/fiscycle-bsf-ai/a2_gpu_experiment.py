"""A2 GPU v2: bounded, resumable training and automatic development-only reporting."""
import os
os.environ.setdefault('MPLBACKEND','Agg')
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
os.environ['PYTHONDONTWRITEBYTECODE']='1'
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'hasil/model_a2_training_v2'
OLD=ROOT/'hasil/model_a_training_v1'
import argparse,json,hashlib,random,time,shutil,traceback,io
from datetime import datetime,timezone,timedelta
import numpy as np
import pandas as pd
from PIL import Image,ImageOps,ImageDraw
import torch
from torch import nn
from torch.utils.data import Dataset,DataLoader
from torchvision.transforms import functional as TF
from train_model_a import image_model,regression_plot

STATUS='EXPLORATORY_UNVERIFIED_LABELS'
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for b in iter(lambda:stream.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def save(path,value):
    path=Path(path);tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,indent=2,allow_nan=False,default=str)+'\n',encoding='utf-8');os.replace(tmp,path)
def now():return datetime.now(timezone(timedelta(hours=7))).isoformat()
def status(state,**kwargs):save(OUT/'status.json',dict(state=state,updated_at_wib=now(),pid=os.getpid(),**kwargs))
def scores(y,p):
    y=np.asarray(y,float);p=np.asarray(p,float);d=p-y;assert len(y)>0 and np.isfinite(d).all()
    denom=float(((y-y.mean())**2).sum())
    return dict(n=len(y),MAE_mg=float(abs(d).mean()),RMSE_mg=float(np.sqrt((d*d).mean())),bias_mg=float(d.mean()),R2=float(1-(d*d).sum()/denom) if denom else None)
def seed(value):
    random.seed(value);np.random.seed(value);torch.manual_seed(value);torch.cuda.manual_seed_all(value)
    torch.set_num_threads(2);torch.backends.cudnn.benchmark=False;torch.backends.cudnn.deterministic=True
    torch.use_deterministic_algorithms(True,warn_only=True)
def image_tensor(image,size,augment=False):
    im=image.convert('RGB')
    if im.size!=(512,512):raise ValueError('Expected existing v2 single-larva 512x512 letterboxed crop')
    im=im.resize((size,size),Image.Resampling.BILINEAR)
    if augment:
        if random.random()<.5:im=ImageOps.mirror(im)
        if random.random()<.5:im=ImageOps.flip(im)
        if random.random()<.5:im=im.transpose(random.choice([Image.Transpose.ROTATE_90,Image.Transpose.ROTATE_180,Image.Transpose.ROTATE_270]))
    return TF.normalize(TF.to_tensor(im),[.485,.456,.406],[.229,.224,.225])
class Crops(Dataset):
    def __init__(self,rows,size,augment=False):self.rows=rows.reset_index(drop=True);self.size=size;self.augment=augment
    def __len__(self):return len(self.rows)
    def __getitem__(self,i):
        r=self.rows.iloc[i]
        with Image.open(ROOT/r.artifact_path) as im:x=image_tensor(im,self.size,self.augment)
        return x,torch.tensor(float(r.measured_weight_g)*1000,dtype=torch.float32)
def data():
    df=pd.read_csv(OUT/'development_manifest.csv');good=df[df.experiment_eligible]
    return df,good[good.split=='train'].copy(),good[good.split=='validation'].copy()

def prepare():
    OUT.mkdir(exist_ok=True)
    if (OUT/'config.json').exists():return
    assert torch.cuda.is_available()
    receipt=read(OLD/'EXPERIMENT_RECEIPT.json')
    # Check immutable prior experiment outputs and code, not a new image audit.
    protected={str(OLD/name):h for name,h in receipt['files'].items()}
    protected.update({str(ROOT/name):h for name,h in receipt['code'].items()})
    prep=ROOT/'hasil/model_a_preparation_v1'
    protected.update({str(ROOT/name):h for name,h in read(prep/'protected_integrity.json').items()})
    protected.update({str(prep/name):h for name,h in read(prep/'FREEZE.json')['outputs'].items()})
    protected[str(prep/'FREEZE.json')]=sha(prep/'FREEZE.json')
    for name,h in protected.items():assert sha(name)==h,name
    df=pd.read_csv(OLD/'a2_development_manifest.csv');frozen=pd.read_csv(prep/'a2_manifest.csv').set_index('L_ID')
    assert set(df.split)=={'train','validation'} and len(df)==1114
    assert not set(df[df.split=='train'].split_group_id)&set(df[df.split=='validation'].split_group_id)
    for r in df.itertuples():
        source=frozen.loc[int(r.L_ID)]
        assert r.split==source.split and r.split_group_id==source.split_group_id
        assert abs(r.measured_weight_g-source.Weight)<1e-12
        if r.experiment_eligible:
            assert sha(ROOT/r.artifact_path)==r.artifact_sha256
            with Image.open(ROOT/r.artifact_path) as im:im.load();assert im.size==(512,512)
    shutil.copyfile(OLD/'a2_development_manifest.csv',OUT/'development_manifest.csv')
    tr=df[df.experiment_eligible & df.split.eq('train')];va=df[df.experiment_eligible & df.split.eq('validation')]
    assert len(tr)>0 and len(va)>0
    cfg=dict(version='model_a2_training_v2',status=STATUS,architecture='MobileNetV3 Small / 576-128-1 head',
        pretrained='ImageNet1K_V1 cached official weights',input_size=224,batch_size=8,max_epochs=30,head_epochs=5,patience=7,
        seed=20261106,device='cuda:0',amp=True,amp_initial_scale=128,workers=0,loss='MSE on train-standardized target',
        loss_reason='Retain v1 MSE for a controlled GPU/224px run; all legitimate weight extremes remain included.',
        target_mean_mg=float((tr.measured_weight_g*1000).mean()),target_std_mg=float((tr.measured_weight_g*1000).std(ddof=0)),
        normalization='ImageNet RGB constants; target mean/std train only',head_lr=.001,fine_head_lr=.0002,fine_backbone_lr=.00005,
        weight_decay=.001,augmentation='flips and 90-degree rotations only',batchnorm='frozen running statistics',
        selection='lowest eligible development-validation MAE',train_n=len(tr),validation_n=len(va),
        eligibility='Inherit v3/v1 technically screened subset unchanged; exclude known crop failures and retained markings; no target/residual filtering.',
        crop_contract='Pre-cropped single-larva v2 512x512 letterbox; no arbitrary multi-larva photo support',
        target_name='predicted_measured_weight_mg',wet_dry_protocol='UNKNOWN',physical_pixel_calibration='UNVERIFIED',
        existing_checkpoint_note='CPU v1 finished but has no optimizer/RNG state and uses160px. New224px protocol is a new run, not a restart of a compatible interrupted run.',
        manifest_sha256=sha(OUT/'development_manifest.csv'),trainer_sha256=sha(__file__),pretrained_sha256=sha(OLD/'pretrained/mobilenet_v3_small-047dcff4.pth'))
    coverage=[]
    for (split,batch),g in df.groupby(['split','Batch_ID']):
        a=g[g.experiment_eligible]
        coverage.append(dict(split=split,batch=batch,available=len(g),eligible=len(a),excluded=len(g)-len(a),coverage=len(a)/len(g),
            available_weight_min_mg=float(g.measured_weight_g.min()*1000),available_weight_max_mg=float(g.measured_weight_g.max()*1000),
            eligible_weight_min_mg=float(a.measured_weight_g.min()*1000) if len(a) else None,
            eligible_weight_max_mg=float(a.measured_weight_g.max()*1000) if len(a) else None))
    pd.DataFrame(coverage).to_csv(OUT/'coverage_by_batch.csv',index=False)
    df.assign(weight_range=pd.cut(df.measured_weight_g*1000,[-np.inf,180,240,np.inf])).groupby(['split','weight_range','experiment_eligible'],observed=True).size().rename('n').to_csv(OUT/'coverage_by_weight.csv')
    df[~df.experiment_eligible].groupby(['split','experiment_exclusion']).size().rename('n').to_csv(OUT/'exclusions.csv')
    save(OUT/'protected_hashes.json',protected);save(OUT/'config.json',cfg)
    import importlib.metadata as meta,sys
    save(OUT/'environment.json',dict(python=sys.version,executable=sys.executable,gpu=torch.cuda.get_device_name(0),cuda=torch.version.cuda,
        packages={n:meta.version(n) for n in ['torch','torchvision','numpy','pandas','Pillow','scikit-learn']}))
    status('PREPARED',train_images=len(tr),validation_images=len(va))

def configure(model,cfg,phase):
    for p in model.features.parameters():p.requires_grad=False
    if phase=='finetune':
        for p in model.features[-3:].parameters():p.requires_grad=True
    for p in model.classifier.parameters():p.requires_grad=True
def optimizer(model,cfg):
    return torch.optim.AdamW([{'params':model.classifier.parameters(),'lr':cfg['head_lr']},
        {'params':model.features.parameters(),'lr':cfg['fine_backbone_lr']}],weight_decay=cfg['weight_decay'])
def rng_state(gen):return dict(python=random.getstate(),numpy=np.random.get_state(),torch=torch.get_rng_state(),cuda=torch.cuda.get_rng_state_all(),loader=gen.get_state())
def restore_rng(r,gen):
    random.setstate(r['python']);np.random.set_state(r['numpy']);torch.set_rng_state(r['torch']);torch.cuda.set_rng_state_all(r['cuda']);gen.set_state(r['loader'])
def checkpoint(path,obj):
    tmp=path.with_suffix('.tmp');torch.save(obj,tmp)
    if path.name=='last.pt' and path.exists():shutil.copyfile(path,OUT/'last.previous.pt')
    os.replace(tmp,path)
def load_last(cfg):
    for name in ['last.pt','last.previous.pt']:
        p=OUT/name
        if p.exists():
            try:obj=torch.load(p,map_location='cpu',weights_only=False)
            except (OSError,RuntimeError,EOFError) as exc:print('Invalid checkpoint:',name,type(exc).__name__,flush=True);continue
            assert obj['config']==cfg,'Checkpoint config mismatch; use a new version'
            return obj
    if any((OUT/n).exists() for n in ['last.pt','last.previous.pt']):raise RuntimeError('No valid resumable checkpoint; refusing silent restart')
    return None
def evaluate(model,rows,cfg):
    model.eval();ys=[];ps=[]
    with torch.inference_mode():
        for x,y in DataLoader(Crops(rows,cfg['input_size']),batch_size=cfg['batch_size'],num_workers=0):
            # FP32 validation/inference agreement; AMP is used for training only.
            p=model(x.to('cuda')).float().flatten()*cfg['target_std_mg']+cfg['target_mean_mg']
            ys.extend(y.tolist());ps.extend(p.cpu().tolist())
    return np.array(ys),np.array(ps)

def sanity(cfg,tr):
    if (OUT/'sanity.json').exists():assert read(OUT/'sanity.json')['passed'];return
    status('SANITY_RUNNING');seed(cfg['seed'])
    model=image_model(pretrained=True).cuda();configure(model,cfg,'head');model.eval()
    opt=optimizer(model,cfg);scaler=torch.amp.GradScaler('cuda',init_scale=cfg['amp_initial_scale'])
    x,y=next(iter(DataLoader(Crops(tr.head(8),cfg['input_size']),batch_size=8)));x=x.cuda();y=(y.cuda()-cfg['target_mean_mg'])/cfg['target_std_mg']
    with torch.no_grad():initial=float(nn.functional.mse_loss(model(x).flatten(),y))
    for step in range(32):
        opt.zero_grad(set_to_none=True)
        with torch.autocast('cuda',dtype=torch.float16):loss=nn.functional.mse_loss(model(x).flatten(),y)
        assert torch.isfinite(loss);scaler.scale(loss).backward();scaler.unscale_(opt)
        assert all(torch.isfinite(p.grad).all() for p in model.parameters() if p.grad is not None)
        scaler.step(opt);scaler.update()
    with torch.no_grad():final=float(nn.functional.mse_loss(model(x).flatten(),y))
    assert final<initial,'Tiny-subset loss failed to decrease'
    gen=torch.Generator().manual_seed(cfg['seed'])
    obj=dict(model=model.state_dict(),optimizer=opt.state_dict(),scaler=scaler.state_dict(),scheduler=None,config=cfg,rng=rng_state(gen))
    checkpoint(OUT/'sanity.pt',obj)
    reloaded=torch.load(OUT/'sanity.pt',map_location='cpu',weights_only=False)
    clone=image_model().cuda();configure(clone,cfg,'head');clone.load_state_dict(reloaded['model']);clone.eval()
    with torch.no_grad():assert torch.allclose(model(x),clone(x),atol=1e-5)
    # Check one equivalent optimizer update after restoring optimizer + scaler, not just weights.
    other=optimizer(clone,cfg);other.load_state_dict(reloaded['optimizer']);other_scaler=torch.amp.GradScaler('cuda',init_scale=cfg['amp_initial_scale']);other_scaler.load_state_dict(reloaded['scaler'])
    for m,o,s in [(model,opt,scaler),(clone,other,other_scaler)]:
        o.zero_grad(set_to_none=True)
        with torch.autocast('cuda',dtype=torch.float16):loss=nn.functional.mse_loss(m(x).flatten(),y)
        s.scale(loss).backward();s.unscale_(o);s.step(o);s.update()
    assert all(torch.allclose(a,b,atol=1e-6) for a,b in zip(model.parameters(),clone.parameters()))
    save(OUT/'sanity.json',dict(passed=True,device=str(x.device),steps=32,initial_MSE=initial,final_MSE=final,
        finite_gradients=True,serialization=True,optimizer_resume_equivalence=True,peak_allocated_MiB=torch.cuda.max_memory_allocated()/2**20))

def run():
    OUT.mkdir(exist_ok=True)
    # Windows OS-held lock is released on interruption, unlike a stale PID file.
    import msvcrt
    lock=(OUT/'run.lock').open('a+b');lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:raise RuntimeError('This experiment is already running')
    try:
        if (OUT/'COMPLETE.json').exists():print('Already complete; no retraining');return
        prepare();cfg=read(OUT/'config.json')
        assert sha(__file__)==cfg['trainer_sha256'],'Trainer changed; use a new experiment version'
        assert sha(OUT/'development_manifest.csv')==cfg['manifest_sha256']
        assert torch.cuda.is_available()
        q=torch.ones(32,device='cuda');assert float((q@q).cpu())==32
        df,tr,va=data();sanity(cfg,tr);seed(cfg['seed']);torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats()
        model=image_model(pretrained=True).cuda();opt=optimizer(model,cfg);scaler=torch.amp.GradScaler('cuda',init_scale=cfg['amp_initial_scale'])
        gen=torch.Generator().manual_seed(cfg['seed']);state=load_last(cfg)
        start=0;best=float('inf');best_epoch=0;stale=0;history=[]
        if state:
            model.load_state_dict(state['model']);opt.load_state_dict(state['optimizer']);scaler.load_state_dict(state['scaler'])
            start=state['epoch'];best=state['best_metric'];best_epoch=state['best_epoch'];stale=state['stale'];history=state['history'];restore_rng(state['rng'],gen)
        loader=DataLoader(Crops(tr,cfg['input_size'],True),batch_size=cfg['batch_size'],shuffle=True,num_workers=0,generator=gen)
        for ep in range(start,cfg['max_epochs']):
            if ep>=cfg['head_epochs'] and stale>=cfg['patience']:break
            phase='head' if ep<cfg['head_epochs'] else 'finetune';configure(model,cfg,phase)
            if ep==cfg['head_epochs']:
                opt.param_groups[0]['lr']=cfg['fine_head_lr'];opt.param_groups[1]['lr']=cfg['fine_backbone_lr'];stale=0
            status('TRAINING',epochs_completed=ep,phase=phase,train_images=len(tr),validation_images=len(va),best_MAE_mg=best if np.isfinite(best) else None)
            model.train();model.features.eval();total=0;beg=time.time()
            for x,y in loader:
                x=x.cuda();y=(y.cuda()-cfg['target_mean_mg'])/cfg['target_std_mg'];opt.zero_grad(set_to_none=True)
                with torch.autocast('cuda',dtype=torch.float16):loss=nn.functional.mse_loss(model(x).flatten(),y)
                assert torch.isfinite(loss);scaler.scale(loss).backward();scaler.unscale_(opt)
                grads=[p.grad for p in model.parameters() if p.grad is not None];assert grads and all(torch.isfinite(g).all() for g in grads)
                nn.utils.clip_grad_norm_(model.parameters(),5);scaler.step(opt);scaler.update();total+=float(loss.detach())*len(x)
            y,p=evaluate(model,va,cfg);m=scores(y,p)
            row=dict(epoch=ep+1,phase=phase,train_normalized_MSE=total/len(tr),validation_normalized_MSE=float(np.mean(((p-y)/cfg['target_std_mg'])**2)),seconds=time.time()-beg,**m)
            history.append(row);improved=m['MAE_mg']<best
            if improved:best=m['MAE_mg'];best_epoch=ep+1;stale=0
            elif phase=='finetune':stale+=1
            obj=dict(model=model.state_dict(),optimizer=opt.state_dict(),scaler=scaler.state_dict(),scheduler=None,epoch=ep+1,
                best_metric=best,best_epoch=best_epoch,stale=stale,history=history,config=cfg,architecture=cfg['architecture'],rng=rng_state(gen),validation=m)
            if improved:checkpoint(OUT/'best.pt',obj)
            checkpoint(OUT/'last.pt',obj);pd.DataFrame(history).to_csv(OUT/'history.csv',index=False)
            print(json.dumps(row),flush=True)
        status('FINALIZING',epochs_completed=len(history),best_epoch=best_epoch,best_MAE_mg=best)
        finish(cfg,df,tr,va,history)
    except Exception as exc:
        status('FAILED',error=repr(exc),resume='Run the same run command; last valid full checkpoint is reused')
        (OUT/'error.txt').write_text(traceback.format_exc(),encoding='utf-8');raise
    finally:
        lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1);lock.close()

def predict_measured_weight(image,checkpoint_path=None,device='cpu'):
    """Requires a pre-cropped single-larva v2 letterboxed 512x512 image, NOT raw multi-larva photos."""
    try:
        if isinstance(image,Image.Image):im=image.copy();im.load()
        else:
            with Image.open(image) as source:source.load();im=source.copy()
        x=image_tensor(im,224).unsqueeze(0)
    except (OSError,ValueError,TypeError) as exc:raise ValueError('Invalid/unreadable image or incompatible crop; supply a v2 512x512 single-larva crop') from exc
    obj=torch.load(checkpoint_path or OUT/'best.pt',map_location='cpu',weights_only=False) # trusted local full checkpoint
    cfg=obj['config'];assert cfg['input_size']==224
    model=image_model().to(device);model.load_state_dict(obj['model']);model.eval()
    with torch.inference_mode():value=float(model(x.to(device)).item()*cfg['target_std_mg']+cfg['target_mean_mg'])
    if not np.isfinite(value):raise ValueError('Nonfinite model output')
    return dict(predicted_measured_weight_mg=value,model_version=cfg['version'],status=[STATUS,'RESEARCH_PROTOTYPE','NOT_FIELD_VALIDATED'],
        input_contract=cfg['crop_contract'],limitations=['Wet/dry protocol unknown','No physical pixel-scale calibration','No A1-to-A2 domain validation','No supported prediction confidence interval'])

def finish(cfg,df,tr,va,history):
    obj=torch.load(OUT/'best.pt',map_location='cpu',weights_only=False);model=image_model().cuda();model.load_state_dict(obj['model'])
    y,p=evaluate(model,va,cfg);pred=va[['id','L_ID','Batch_ID','split_group_id','artifact_path','ai_visual_finding']].copy()
    pred['measured_weight_mg']=y;pred['predicted_measured_weight_mg']=p;pred['error_mg']=p-y
    refs=pd.read_csv(OLD/'a2_baselines/validation_predictions.csv')
    matched=pred.merge(refs[['L_ID','mean','length_linear','length_ridge']],on='L_ID',validate='one_to_one');assert len(matched)==len(va)
    matched['eligible_train_mean']=cfg['target_mean_mg']
    comparison={k:scores(matched.measured_weight_mg,matched[k]) for k in ['predicted_measured_weight_mg','mean','eligible_train_mean','length_linear','length_ridge']}
    metrics=dict(overall=scores(y,p),baselines_same_IDs=comparison,by_batch={b:scores(g.measured_weight_mg,g.predicted_measured_weight_mg) for b,g in pred.groupby('Batch_ID')},
        by_primary_group={b:scores(g.measured_weight_mg,g.predicted_measured_weight_mg) for b,g in pred.groupby('split_group_id')},
        by_weight_range={str(b):scores(g.measured_weight_mg,g.predicted_measured_weight_mg) for b,g in pred.groupby(pd.cut(pred.measured_weight_mg,[-np.inf,180,240,np.inf]),observed=True)},
        best_epoch=obj['epoch'],epochs_completed=len(history),status=STATUS,final_test_used=False,
        peak_allocated_MiB=torch.cuda.max_memory_allocated()/2**20,peak_reserved_MiB=torch.cuda.max_memory_reserved()/2**20)
    matched.to_csv(OUT/'validation_predictions.csv',index=False);save(OUT/'metrics.json',metrics)
    pd.DataFrame(comparison).T.to_csv(OUT/'metrics_comparison.csv')
    regression_plot(y,p,OUT/'regression_diagnostics.png')
    import matplotlib.pyplot as plt
    hist=pd.DataFrame(history);fig,axes=plt.subplots(1,2,figsize=(9,3))
    axes[0].plot(hist.epoch,hist.train_normalized_MSE,label='train');axes[0].plot(hist.epoch,hist.validation_normalized_MSE,label='validation');axes[0].legend();axes[0].set(xlabel='Epoch',ylabel='Normalized MSE')
    axes[1].plot(hist.epoch,hist.MAE_mg);axes[1].set(xlabel='Epoch',ylabel='Validation MAE mg');fig.tight_layout();fig.savefig(OUT/'learning_curves.png');plt.close(fig)
    largest=pred.assign(absolute_error_mg=abs(pred.error_mg)).nlargest(8,'absolute_error_mg')
    largest['review_request']='Check whole-body crop, background and source-weight linkage; large residual alone is not proof of incorrect label'
    largest.to_csv(OUT/'targeted_review.csv',index=False)
    sheet=Image.new('RGB',(1024,580),'white');draw=ImageDraw.Draw(sheet)
    for i,r in enumerate(largest.itertuples()):
        x=(i%4)*256;z=(i//4)*290
        with Image.open(ROOT/r.artifact_path) as im:sheet.paste(im.resize((224,224)),(x,z+55))
        draw.text((x+4,z+4),f'{r.id} {r.Batch_ID}\ntrue {r.measured_weight_mg:.1f} pred {r.predicted_measured_weight_mg:.1f}\nerror {r.error_mg:+.1f} mg',fill='black')
    sheet.save(OUT/'largest_error_previews.jpg',quality=95)
    # Locked, post-selection sensitivity check. Never used for checkpoint selection or eligibility revision.
    suspected=df[(~df.experiment_eligible)&df.split.eq('validation')&df.ai_visual_finding.fillna('').str.contains('STAIN|CARD|RULER|INK')&df.artifact_path.notna()].sort_values('id').head(12)
    shortcut=dict(primary_clean=scores(y,p),note='Risk strata/batches differ: association is not causal shortcut attribution; diagnostic cases excluded from training and model selection')
    if len(suspected):
        sy,sp=evaluate(model,suspected,cfg);s=suspected[['id','Batch_ID','artifact_path','ai_visual_finding']].copy();s['measured_weight_mg']=sy;s['predicted_measured_weight_mg']=sp;s['error_mg']=sp-sy;s.to_csv(OUT/'suspected_shortcut_diagnostic.csv',index=False);shortcut['suspected_validation']=scores(sy,sp)
    entries={e['id']:e for e in read(ROOT/'hasil/model_a_finalization_v1/review_items.json') if e['track']=='A2' and e['split'] in ['train','validation']}
    scale=[]
    for r in pred.itertuples():
        box=entries[r.id]['crop_bbox'];scale.append(dict(id=r.id,native_crop_area_px=(box[2]-box[0])*(box[3]-box[1]),measured_weight_mg=r.measured_weight_mg,error_mg=r.error_mg))
    scale=pd.DataFrame(scale);scale.to_csv(OUT/'native_scale_diagnostic.csv',index=False)
    shortcut['native_area_weight_correlation_validation']=float(scale.native_crop_area_px.corr(scale.measured_weight_mg))
    shortcut['scale_limit']='ROI normalization discards absolute native scale; correlation does not establish calibrated size or a cause of error'
    save(OUT/'shortcut_diagnostics.json',shortcut)
    example=va.iloc[0];smoke=predict_measured_weight(ROOT/example.artifact_path,device='cpu')
    assert abs(smoke['predicted_measured_weight_mg']-p[0])<.1
    for bad in [OUT/'does_not_exist.png',Image.new('RGB',(100,100))]:
        try:predict_measured_weight(bad)
        except ValueError:pass
        else:raise AssertionError('Invalid input accepted')
    save(OUT/'inference_smoke.json',dict(passed=True,example_id=example.id,cpu_gpu_agreement_tolerance_mg=.1,invalid_inputs_rejected=True,result=smoke))
    for name,h in read(OUT/'protected_hashes.json').items():assert sha(name)==h,name
    m=metrics['overall'];gap=hist.iloc[-1].validation_normalized_MSE-hist.iloc[-1].train_normalized_MSE
    report=f'''# A2 GPU training v2 — completed exploratory experiment

## A2 Training Status
Actual status: COMPLETED. Architecture: MobileNetV3 Small / ImageNet1K_V1, scalar regression head. Device: CUDA RTX2050, AMP training, FP32 validation. Completed epochs: {len(history)}, best epoch: {obj['epoch']}. Train: {len(tr)}; validation: {len(va)}. Best checkpoint: best.pt; resumable last.pt and last.previous.pt preserve optimizer, GradScaler, RNG, phase/history/config, best score and epoch. No scheduler used. Resume checks enforce identical code/config/manifest. Tiny-subset loss decrease and optimizer-state reload equivalence passed before main training.

## Performance (provisional, exact same validation IDs)
MAE {m['MAE_mg']:.3f}mg; RMSE {m['RMSE_mg']:.3f}mg; bias {m['bias_mg']:.3f}mg; R² {m['R2']:.4f}. R² is descriptive on these two development groups, not independent biological replication; negative R² means worse squared error than predicting the validation mean.
Mean reference MAE {comparison['mean']['MAE_mg']:.3f}mg; Length MAE {comparison['length_linear']['MAE_mg']:.3f}mg. Those references were fitted on924 frozen training rows and evaluated here on the exact eligible IDs; eligible_train_mean uses the image model's own training population. Length is measured manually and unavailable to image-only inference. No Weight/Length/Width/Sex/ID/batch inputs enter the CNN.

## Diagnostics
Largest eight errors: targeted_review.csv and largest_error_previews.jpg. No extra human inspection is falsely claimed by this automatic report. Review suspected wrong-object/body-cutting/background cases only where evidence warrants it; residuals alone do not label images incorrect. Signed errors and per-weight-range, batch and primary-group metrics are in metrics.json. Latest train/validation normalized MSE gap={gap:.4f}; a positive gap is compatible with overfitting or distribution shift, not proof of either. Weak performance near the mean can indicate underfitting/range compression; inspect regression_diagnostics.png rather than asserting morphology was learned.
Shortcut checks: compare visually-screened eligible crops to up to12 flagged validation crops after checkpoint selection; neither cohort equivalence nor causal background attribution is established. Native crop-area correlations are diagnostics only. No pixel-to-mm conversion or calibrated scale claim. Selection and preprocessing stayed fixed throughout this run.

## Eligibility and limitations
Reused the largest existing subset that passed technical/visual triage without unresolved known failures or retained shortcut flags: {len(tr)}/924 train, {len(va)}/190 validation. Held counts and batch/weight-range coverage are in exclusions.csv, coverage_by_batch.csv and coverage_by_weight.csv. Unverified does not mean forbidden, but existing concrete risk flags were not silently cleared. No new blanket approvals or full audit. Historical CPU A2 remains available; it has no complete optimizer resume state and used160px, so this is a distinct224px experiment. Only the frozen development groups were used.178 final-test and316 quarantine rows stayed out. Final test has one primary group; images are not independent cohorts. Labels/crops not fully human-certified; wet/dry protocol UNKNOWN. No field validation or A1→A2 integration.

## Reproducibility
From repository root (PowerShell):
```powershell
& .\\.agents\\skills\\fiscycle-bsf-ai\\.venv-cuda\\Scripts\\python.exe -B .\\.agents\\skills\\fiscycle-bsf-ai\\a2_gpu_experiment.py run
& .\\.agents\\skills\\fiscycle-bsf-ai\\.venv-cuda\\Scripts\\python.exe -B .\\.agents\\skills\\fiscycle-bsf-ai\\a2_gpu_experiment.py predict PATH_TO_512_CROP
```
The same run command resumes an interrupted compatible last checkpoint; a completed run exits without restarting. Inference requires a pre-cropped single-larva v2 512x512 letterboxed image and rejects unreadable/wrong-size inputs. It returns predicted_measured_weight_mg, version and research status, without confidence intervals. Ground-truth metadata is never an inference argument.

## Decision
Demonstrated: actual GPU optimization, finite gradients, full checkpoint resume mechanics, provisional validation and standalone inference. Not demonstrated: final-test generalization, reliable crop semantics for arbitrary inputs, physical calibration, production readiness or robust shortcut independence. Highest-priority next controlled experiment: preserve native image scale while retaining the same clean development IDs and screening out markings; compare to normalized ROI under the same protocol without using final test. No automatic follow-up training is launched.
'''
    (OUT/'TRAINING_REPORT.md').write_text(report,encoding='utf-8')
    save(OUT/'COMPLETE.json',dict(completed_at=now(),status=STATUS,metrics=m,best_epoch=obj['epoch'],epochs_completed=len(history),
        protected_integrity='PASS',inference_smoke='PASS',code_sha256=sha(__file__),config_sha256=sha(OUT/'config.json'),
        checkpoint_hashes={n:sha(OUT/n) for n in ['best.pt','last.pt','last.previous.pt'] if (OUT/n).exists()}))
    status('COMPLETED',epochs_completed=len(history),best_epoch=obj['epoch'],metrics=m)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','sanity','run','status','predict']);p.add_argument('image',nargs='?');args=p.parse_args()
    if args.command=='prepare':prepare()
    elif args.command=='sanity':prepare();cfg=read(OUT/'config.json');_,tr,_=data();sanity(cfg,tr)
    elif args.command=='run':run()
    elif args.command=='status':print(json.dumps(read(OUT/'status.json') if (OUT/'status.json').exists() else {'state':'NOT_STARTED'},indent=2))
    else:print(json.dumps(predict_measured_weight(args.image),indent=2))
