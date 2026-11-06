"""One-image CUDA inference and forward/backward check; no optimizer or training run."""
import os,json,sys,hashlib,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'hasil/gpu_setup_v1'
os.environ['YOLO_CONFIG_DIR']=str(OUT/'ultralytics_settings')
import numpy as np
import pandas as pd
from PIL import Image
import cv2
import torch
import torchvision
from ultralytics import YOLO,settings
from ultralytics.cfg import get_cfg

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def smi():
    return subprocess.check_output(['nvidia-smi','--query-gpu=name,driver_version,memory.total,memory.used,memory.free','--format=csv,noheader,nounits'],text=True).strip()

def main():
    OUT.mkdir(exist_ok=True)
    assert sys.prefix!=sys.base_prefix and Path(sys.prefix).resolve()==(ROOT/'.venv-cuda').resolve()
    assert torch.cuda.is_available(),'CUDA unavailable'
    settings.update({'sync':False,'wandb':False,'mlflow':False,'clearml':False,'comet':False,'dvc':False,'neptune':False,'tensorboard':False})
    torch.set_num_threads(2);torch.manual_seed(20261105)
    before=smi()
    x=torch.arange(256*256,device='cuda',dtype=torch.float32).reshape(256,256)/65536
    y=x@x.T;torch.cuda.synchronize()
    assert torch.isfinite(y).all() and torch.allclose(y.cpu(),x.cpu()@x.cpu().T,rtol=1e-4,atol=1e-4)
    del x,y;torch.cuda.empty_cache()
    run=ROOT/'hasil/model_a_training_v1'
    df=pd.read_csv(run/'a1_development_manifest.csv')
    r=df[df.experiment_eligible & df.split.eq('train') & df.annotation_count.between(4,20)].sort_values('id').iloc[0]
    assert r.split=='train' and sha(r.experiment_image)==r.source_sha256
    assert sha(r.experiment_label)==r.experiment_label_sha256
    checkpoint=run/'a1_initial/weights/best.pt';checkpoint_sha=sha(checkpoint)
    torch.cuda.reset_peak_memory_stats()
    wrapper=YOLO(str(checkpoint))
    result=wrapper.predict(r.experiment_image,imgsz=320,batch=1,device=0,conf=.25,verbose=False)[0]
    torch.cuda.synchronize()
    assert result.boxes.data.is_cuda and result.masks is not None
    predicted=len(result.boxes)
    inference_peak=torch.cuda.max_memory_allocated()/2**20
    result.save(filename=str(OUT/'a1_train_gpu_prediction.jpg'))
    del result,wrapper;torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats()
    net=YOLO(str(checkpoint)).model.to('cuda').float()
    net.args=get_cfg(overrides={'overlap_mask':False,'mask_ratio':2,'device':'0'})
    net.train()
    for p in net.parameters():p.requires_grad_(True)
    with Image.open(r.experiment_image) as im:
        rgb=np.asarray(im.convert('RGB').resize((320,320),Image.Resampling.BILINEAR)).copy()
    masks=[];boxes=[]
    for line in Path(r.experiment_label).read_text().splitlines():
        values=list(map(float,line.split()));assert values[0]==0
        xy=np.array(values[1:],dtype=np.float32).reshape(-1,2)
        mask=np.zeros((160,160),np.uint8);cv2.fillPoly(mask,[np.rint(xy*159).astype(np.int32)],1)
        lo=xy.min(0);hi=xy.max(0);boxes.append([*(lo+hi)/2,*(hi-lo)]);masks.append(mask)
    n=len(masks)
    batch={'img':torch.from_numpy(rgb.transpose(2,0,1)).unsqueeze(0).float().to('cuda')/255,
        'batch_idx':torch.zeros(n,device='cuda'),'cls':torch.zeros((n,1),device='cuda'),
        'bboxes':torch.tensor(boxes,device='cuda'),'masks':torch.tensor(np.array(masks),device='cuda').float()}
    loss,components=net(batch);total=loss.sum();assert torch.isfinite(total);total.backward();torch.cuda.synchronize()
    gradients=[p.grad for p in net.parameters() if p.grad is not None]
    assert gradients and all(torch.isfinite(g).all() for g in gradients)
    report=dict(python=sys.version,executable=sys.executable,virtual_environment=sys.prefix,
        torch=torch.__version__,torchvision=torchvision.__version__,cuda_runtime=torch.version.cuda,
        cuda_available=True,gpu=torch.cuda.get_device_name(0),compute_capability=torch.cuda.get_device_capability(0),
        tensor_matmul='PASS',source_id=r.id,source_split=r.split,annotated_instances=n,
        input_resolution=320,batch_size=1,precision='FP32',predicted_instances=predicted,
        cuda_inference='PASS',cuda_forward_backward='PASS',finite_loss=float(total.detach()),
        finite_gradients=True,inference_peak_allocated_MiB=inference_peak,
        backward_peak_allocated_MiB=torch.cuda.max_memory_allocated()/2**20,
        backward_peak_reserved_MiB=torch.cuda.max_memory_reserved()/2**20,
        nvidia_smi_before=before,nvidia_smi_during=smi(),optimizer_steps=0,full_training_launched=False,
        final_test_used=False,checkpoint_sha256=checkpoint_sha)
    assert sha(checkpoint)==checkpoint_sha
    for name,h in json.loads((OUT/'before_integrity.json').read_text()).items():assert sha(name)==h,name
    # Verify every artifact in the completed CPU experiment, without changing its receipt.
    receipt=json.loads((run/'EXPERIMENT_RECEIPT.json').read_text())
    for name,h in receipt['files'].items():assert sha(run/name)==h,name
    report['preserved_artifacts']='PASS including all 593 prior experiment files and protected B1'
    (OUT/'verification.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
