"""Read-only Model A source audit; writes derived evidence under hasil/model_a_audit.

No training, automatic label repair, or archive extraction. Full JPEG decoding is
performed one image at a time. Contact sheets are diagnostic scientific figures.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import openpyxl
import pandas as pd
from PIL import Image
from scipy.fft import dctn

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
OUT = ROOT / 'hasil' / 'model_a_audit'
IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.webp'}


def json_save(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str,
                                      allow_nan=False), encoding='utf-8')


def stats(values):
    s = pd.Series(values, dtype=float).dropna()
    if s.empty:
        return {'count': 0}
    q = s.quantile([.01, .05, .25, .5, .75, .95, .99])
    low, high = q[.25] - 1.5*(q[.75]-q[.25]), q[.75]+1.5*(q[.75]-q[.25])
    return dict(count=len(s), min=float(s.min()), max=float(s.max()), mean=float(s.mean()),
                median=float(s.median()), std=float(s.std()) if len(s)>1 else None,
                percentiles={str(k):float(v) for k,v in q.items()},
                nonpositive=int(s.le(0).sum()), iqr_outliers=int(((s<low)|(s>high)).sum()))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inspect_image(name, blob, dataset):
    rec = dict(dataset=dataset, path=name, bytes=len(blob), sha256=sha(blob), error=None)
    preview = None
    try:
        with Image.open(io.BytesIO(blob)) as im:
            im.load()  # Decode every pixel; header-only inspection is insufficient.
            rec.update(width=im.width, height=im.height, mode=im.mode,
                       channels=len(im.getbands()), format=im.format,
                       pixel_sha256=sha(im.tobytes()))
            exif=im.getexif()
            rec.update(exif_datetime=str(exif.get(306, '')), camera_make=str(exif.get(271,'')),
                       camera_model=str(exif.get(272,'')), dpi=str(im.info.get('dpi','')))
            gray=np.asarray(im.convert('L').resize((32,32)),dtype=float)
            coeff=dctn(gray,norm='ortho')[:8,:8].ravel()
            bits=coeff > np.median(coeff[1:])
            rec['phash']=format(int(''.join('1' if b else '0' for b in bits),2),'016x')
            preview=im.convert('RGB')
            preview.thumbnail((480,360))
    except Exception as exc:
        rec['error']=f'{type(exc).__name__}: {exc}'
    return rec,preview


def groups(records, field):
    buckets=defaultdict(list)
    for r in records:
        if r.get(field): buckets[r[field]].append(r['path'])
    return [names for names in buckets.values() if len(names)>1]


def image_summary(records):
    return dict(count=len(records), bytes=sum(r['bytes'] for r in records),
                file_size_bytes=stats([r['bytes'] for r in records]),
                resolutions=dict(Counter(f"{r.get('width')}x{r.get('height')}" for r in records)),
                modes=dict(Counter(r.get('mode') for r in records)),
                formats=dict(Counter(r.get('format') for r in records)),
                channels=dict(Counter(r.get('channels') for r in records)),
                errors=[r for r in records if r['error']],
                byte_duplicate_groups=groups(records,'sha256'),
                pixel_duplicate_groups=groups(records,'pixel_sha256'),
                filename_duplicates=[k for k,v in Counter(Path(r['path']).name for r in records).items() if v>1],
                camera_models=dict(Counter(r.get('camera_model','') for r in records)),
                dpi=dict(Counter(r.get('dpi','') for r in records)))


def contact_sheet(samples, name, labels=False):
    fig,axes=plt.subplots((len(samples)+3)//4,4,figsize=(16,3.4*((len(samples)+3)//4)),squeeze=False)
    for ax in axes.ravel(): ax.axis('off')
    for ax,(rec,im,polygons) in zip(axes.ravel(),samples):
        ax.imshow(im)
        if labels:
            for cls,xy in polygons:
                pts=np.asarray(xy)*[im.width,im.height]
                ax.plot(*np.vstack([pts,pts[0]]).T,linewidth=.6,color='lime' if cls==1 else 'red')
        ax.set_title(Path(rec['path']).name[:45],fontsize=7)
    fig.tight_layout()
    fig.savefig(OUT/name,dpi=130)
    plt.close(fig)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    original=[p for p in DATA.rglob('*') if p.is_file()]
    before={str(p.relative_to(ROOT)):(p.stat().st_size,p.stat().st_mtime_ns) for p in original}
    inventory=[dict(path=k,bytes=v[0],extension=Path(k).suffix.lower()) for k,v in before.items()]
    pd.DataFrame(inventory).to_csv(OUT/'source_inventory.csv',index=False)
    summary={'audit_time_utc':datetime.now(timezone.utc).isoformat(),'python':sys.version,
             'scope':'DATASET_AUDIT_ONLY_NO_TRAINING','local_files':len(original),
             'local_bytes':sum(v[0] for v in before.values())}
    wbpath=DATA/'Larvae--size-data.xlsx'
    summary['workbook_md5']=hashlib.md5(wbpath.read_bytes()).hexdigest()
    wb=openpyxl.load_workbook(wbpath,read_only=True,data_only=True)
    formulas=openpyxl.load_workbook(wbpath,read_only=True,data_only=False)
    sheets={}
    for ws in wb:
        cells=[{'excel_row':i,'cells':list(row)} for i,row in enumerate(ws.values,1) if any(v is not None for v in row)]
        sheets[ws.title]={'max_row':ws.max_row,'max_column':ws.max_column,'nonempty_rows':len(cells),
                          'rows':cells,'formulas':[{'cell':c.coordinate,'formula':c.value} for row in formulas[ws.title] for c in row if c.data_type=='f']}
    json_save('workbook_sheets.json',sheets)
    df=pd.read_excel(wbpath,sheet_name='Larva Data')
    df.insert(0,'excel_row',np.arange(2,len(df)+2))
    df.to_csv(OUT/'metadata_audit.csv',index=False)
    summary['metadata']={'rows':len(df),'columns':list(df.columns[1:]),
                         'nulls':{k:int(v) for k,v in df.isna().sum().items()},
                         'unique_ids':int(df.L_ID.nunique()),'duplicate_ids':df[df.L_ID.duplicated(False)].L_ID.tolist(),
                         'sex_counts':df.Sex.fillna('MISSING').value_counts().to_dict(),
                         'batch_counts':df.Batch_ID.fillna('MISSING').value_counts().to_dict(),
                         'date_counts':{str(k):int(v) for k,v in df.Date.value_counts().items()}}
    desc={col:stats(pd.to_numeric(df[col],errors='coerce')) for col in ['Weight','Length','Width']}
    summary['target_statistics']=desc
    valid=df.loc[df[['Weight','Length','Width']].gt(0).all(axis=1),['Weight','Length','Width']]
    summary['correlations_positive_complete_rows']={'n':len(valid),'pearson':valid.corr().to_dict(),
                                                    'spearman':valid.corr(method='spearman').to_dict()}
    summary['weight_length_correlation_all_rows']={'n':len(df),'pearson':df.Weight.corr(df.Length),
                                                  'spearman':df.Weight.corr(df.Length,method='spearman')}
    issues=[]
    for col in ['Weight','Length','Width']:
        s=pd.to_numeric(df[col],errors='coerce'); q1,q3=s.quantile([.25,.75]); iqr=q3-q1
        for idx in df.index[s.isna()|s.le(0)|(s<q1-1.5*iqr)|(s>q3+1.5*iqr)]:
            reason='MISSING' if pd.isna(s[idx]) else 'NONPOSITIVE' if s[idx]<=0 else 'IQR_REVIEW_ONLY'
            issues.append(dict(excel_row=int(df.at[idx,'excel_row']),L_ID=df.at[idx,'L_ID'],field=col,value=df.at[idx,col],reason=reason))
    pd.DataFrame(issues).to_csv(OUT/'measurement_flags.csv',index=False)
    multi=[]; annotations=[]; issues=[]; samples=[]; polygons_by_name={}
    imagefiles=sorted((DATA/'BSF_Larvae_v1/Images').glob('*'))
    labelfiles=sorted((DATA/'BSF_Larvae_v1/Labels').glob('*'))
    selected=set(np.linspace(0,len(imagefiles)-1,16,dtype=int).tolist())
    try:
        from shapely.geometry import Polygon
    except ImportError:
        Polygon=None
    for i,p in enumerate(imagefiles):
        rec,preview=inspect_image(str(p.relative_to(ROOT)),p.read_bytes(),'multi')
        rec['base_name']=p.stem.split('.rf.')[0]
        rec['candidate_timestamp_token']=next(iter(re.findall(r'image_(\d{13})',p.name)),'')
        multi.append(rec)
        label=DATA/'BSF_Larvae_v1/Labels'/f'{p.stem}.txt'
        polygons=[]
        if label.exists():
            seen=set()
            for ln,line in enumerate(label.read_text(encoding='utf-8-sig').splitlines(),1):
                if not line.strip():continue
                a=dict(image=p.name,label=label.name,line=ln,valid=True,reason='',class_id=None,vertices=0)
                try:
                    vals=np.asarray([float(t) for t in line.split()]); cls=vals[0]
                    if not np.isfinite(vals).all() or cls<0 or cls!=int(cls):raise ValueError('nonfinite_or_invalid_class')
                    a['class_id']=int(cls)
                    if len(vals)<7 or (len(vals)-1)%2:raise ValueError('not_polygon_class_plus_xy_pairs')
                    xy=vals[1:].reshape(-1,2); a['vertices']=len(xy)
                    if (xy<0).any() or (xy>1).any():raise ValueError('coordinate_out_of_bounds')
                    if len(np.unique(xy,axis=0))<3:raise ValueError('fewer_than_three_distinct_vertices')
                    area=abs(np.dot(xy[:,0],np.roll(xy[:,1],1))-np.dot(xy[:,1],np.roll(xy[:,0],1)))/2
                    a['normalized_area']=float(area)
                    if area<=1e-12:raise ValueError('zero_area')
                    if Polygon is not None and not Polygon(xy).is_valid:raise ValueError('invalid_polygon_topology')
                    key=tuple(vals)
                    if key in seen:raise ValueError('duplicate_polygon_in_image')
                    seen.add(key);polygons.append((int(cls),xy.tolist()))
                except Exception as exc:
                    a['valid']=False;a['reason']=str(exc);issues.append(a)
                annotations.append(a)
        rec['label_count']=sum(1 for a in annotations if a['image']==p.name)
        polygons_by_name[p.name]=polygons
        if i in selected and preview is not None:samples.append((rec,preview,polygons))
    pd.DataFrame(multi).to_csv(OUT/'multi_images.csv',index=False)
    pd.DataFrame(annotations).to_csv(OUT/'annotations.csv',index=False)
    contact_sheet(samples,'multi_samples_overlay.png',labels=True)
    summary['multi']=image_summary(multi)
    summary['multi'].update(labels=len(labelfiles),instances=len(annotations),
        class_counts=dict(Counter(a['class_id'] for a in annotations)),
        instances_per_image=stats([r['label_count'] for r in multi]),
        zero_labels=[r['path'] for r in multi if r['label_count']==0],
        missing_labels=sorted(set(p.stem for p in imagefiles)-set(p.stem for p in labelfiles)),
        orphan_labels=sorted(set(p.stem for p in labelfiles)-set(p.stem for p in imagefiles)),
        invalid_annotations=issues,polygon_topology_checked=Polygon is not None,
        basename_duplicate_groups=groups(multi,'base_name'))
    print('Multi complete',len(multi),len(annotations),'invalid',len(issues),flush=True)
    single=[];samples=[]
    archive=DATA/'Single Larvae data.zip'
    with archive.open('rb') as f: summary['single_archive_md5']=hashlib.file_digest(f,'md5').hexdigest()
    with zipfile.ZipFile(archive) as z:
        members=[i for i in z.infolist() if not i.is_dir()]
        pd.DataFrame([dict(path=i.filename,bytes=i.file_size,compressed_bytes=i.compress_size,crc32=i.CRC) for i in members]).to_csv(OUT/'archive_inventory.csv',index=False)
        summary['archive']={'members':len(members),'bytes_on_disk':archive.stat().st_size,
                            'uncompressed_bytes':sum(i.file_size for i in members),'extensions':dict(Counter(Path(i.filename).suffix for i in members)),
                            'metadata_files':[i.filename for i in members if Path(i.filename).suffix.lower() not in IMAGE_EXT]}
        imgs=[i for i in members if Path(i.filename).suffix.lower() in IMAGE_EXT]
        selected=set(np.linspace(0,len(imgs)-1,16,dtype=int).tolist())
        for i,member in enumerate(imgs):
            try:
                rec,preview=inspect_image(member.filename,z.read(member),'single')
            except Exception as exc:
                rec={'dataset':'single','path':member.filename,'bytes':member.file_size,'error':str(exc)};preview=None
            rec['filename_id']=int(Path(member.filename).stem) if Path(member.filename).stem.isdigit() else None
            single.append(rec)
            if i in selected and preview is not None:samples.append((rec,preview,[]))
            if (i+1)%100==0:print('Single decoded',i+1,'/',len(imgs),flush=True)
    pd.DataFrame(single).to_csv(OUT/'single_images.csv',index=False)
    contact_sheet(samples,'single_samples.png')
    summary['single']=image_summary(single)
    mapping=pd.DataFrame(single).merge(df,left_on='filename_id',right_on='L_ID',how='outer',indicator=True,validate='one_to_one')
    mapping.to_csv(OUT/'image_metadata_mapping.csv',index=False)
    matched=mapping[mapping['_merge']=='both'].copy()
    dates=pd.to_datetime(matched.exif_datetime,format='%Y:%m:%d %H:%M:%S',errors='coerce')
    date_equal=dates.dt.date==pd.to_datetime(matched.Date).dt.date
    summary['mapping']={'rule':'int(image filename stem) == exact L_ID; unique both sides; not Excel row order',
        'counts':mapping['_merge'].value_counts().to_dict(),
        'unmatched_image_ids':mapping.loc[mapping['_merge']=='left_only','filename_id'].tolist(),
        'unmatched_metadata_ids':mapping.loc[mapping['_merge']=='right_only','L_ID'].tolist(),
        'exif_date_available':int(dates.notna().sum()),'date_matches':int(date_equal.sum()),
        'date_mismatches':matched.loc[dates.notna()&~date_equal,['path','L_ID','Date','exif_datetime']].to_dict('records')}
    pair_records=[]
    for dataset,records in [('multi',multi),('single',single)]:
        good=[r for r in records if r.get('phash')]
        for i,a in enumerate(good):
            ah=int(a['phash'],16)
            for b in good[i+1:]:
                dist=(ah^int(b['phash'],16)).bit_count()
                if dist<=4:
                    pair_records.append(dict(dataset=dataset,left=a['path'],right=b['path'],phash_hamming=dist,
                                              identical_pixels=a['pixel_sha256']==b['pixel_sha256']))
    pd.DataFrame(pair_records,columns=['dataset','left','right','phash_hamming','identical_pixels']).to_csv(OUT/'near_duplicate_candidates.csv',index=False)
    summary['near_duplicate_screen']={'method':'64-bit DCT pHash Hamming <=4; candidates only, not identity proof',
                                     'counts':dict(Counter(p['dataset'] for p in pair_records))}
    fig,axs=plt.subplots(2,3,figsize=(12,7))
    for ax,col in zip(axs[0],['Weight','Length','Width']):
        ax.hist(df[col].dropna(),bins=35);ax.set_title(col+' (raw; including zero widths)')
    for ax,(x,y) in zip(axs[1],[('Length','Weight'),('Width','Weight'),('Length','Width')]):
        ax.scatter(valid[x],valid[y],s=3,alpha=.3);ax.set_xlabel(x);ax.set_ylabel(y)
    fig.tight_layout();fig.savefig(OUT/'target_distributions.png',dpi=140);plt.close(fig)
    after={str(p.relative_to(ROOT)):(p.stat().st_size,p.stat().st_mtime_ns) for p in original}
    summary['source_sizes_and_mtimes_unchanged']=before==after
    json_save('audit_summary.json',summary)
    print('Audit complete:',OUT,flush=True)


def supplemental():
    """Geometry/leakage diagnostics from cached evidence, without decoding all images again."""
    df=pd.read_csv(OUT/'metadata_audit.csv')
    m=pd.read_csv(OUT/'multi_images.csv')
    s=pd.read_csv(OUT/'single_images.csv')
    ann=pd.read_csv(OUT/'annotations.csv')
    def crossings(xy):
        # Inclusive segment-intersection screen. This is not a full geometry library.
        p=np.asarray(xy,dtype=float)
        if np.allclose(p[0],p[-1],rtol=0,atol=1e-12):p=p[:-1]
        a=p[:,None,:];b=np.roll(p,-1,axis=0)[:,None,:]
        c=p[None,:,:];d=np.roll(p,-1,axis=0)[None,:,:]
        def cross(u,v):return u[...,0]*v[...,1]-u[...,1]*v[...,0]
        o1=cross(b-a,c-a);o2=cross(b-a,d-a)
        o3=cross(d-c,a-c);o4=cross(d-c,b-c)
        box=np.all(np.maximum(np.minimum(a,b),np.minimum(c,d))<=np.minimum(np.maximum(a,b),np.maximum(c,d))+1e-12,axis=-1)
        hit=(o1*o2<=1e-20)&(o3*o4<=1e-20)&box
        i,j=np.indices(hit.shape)
        hit &= (j>i+1)&~((i==0)&(j==len(p)-1))
        return int(hit.sum()),int((np.linalg.norm(np.roll(p,-1,axis=0)-p,axis=1)<1e-12).sum())
    geo=[]
    for p in sorted((DATA/'BSF_Larvae_v1/Labels').glob('*.txt')):
        for line_no,line in enumerate(p.read_text().splitlines(),1):
            if not line.strip():continue
            values=np.asarray([float(t) for t in line.split()])
            if len(values)<7 or (len(values)-1)%2:continue
            n,z=crossings(values[1:].reshape(-1,2))
            if n or z:geo.append({'label':p.name,'line':line_no,'intersecting_nonadjacent_edge_pairs':n,'zero_length_edges':z})
    pd.DataFrame(geo,columns=['label','line','intersecting_nonadjacent_edge_pairs','zero_length_edges']).to_csv(OUT/'polygon_geometry_flags.csv',index=False)
    result={'geometry_screen':{'polygons_screened':len(ann),'flagged_polygons':len(geo),
        'images_with_flags':len(set(r['label'] for r in geo)),
        'method':'nonadjacent segment intersection and zero-length edge screen; review required, no repair'},
        'multi_basename_groups':int(m.base_name.nunique()),
        'multi_repeated_basename_group_count':int(m.groupby('base_name').size().gt(1).sum()),
        'multi_unique_basename_class_counts':ann[ann.image.isin(m.drop_duplicates('base_name').path.map(lambda x:Path(x).name))].class_id.value_counts().to_dict(),
        'metadata_positive_length_width_weight_rows':int(df[['Length','Width','Weight']].gt(0).all(axis=1).sum()),
        'width_zero_ids':df.loc[df.Width.eq(0),'L_ID'].tolist(),
        'metadata_rows_per_batch_date':df.fillna({'Batch_ID':'MISSING'}).groupby(['Batch_ID','Date']).size().reset_index(name='rows').to_dict('records')}
    parsed=pd.to_datetime(s.exif_datetime,format='%Y:%m:%d %H:%M:%S',errors='coerce')
    result['single_exif_dates']={str(k):int(v) for k,v in parsed.dt.date.value_counts().items()}
    result['single_same_exif_timestamp_groups']=groups(
        s[['path','exif_datetime']].fillna('').to_dict('records'),'exif_datetime')
    joined=s.merge(df,left_on='filename_id',right_on='L_ID',how='inner',validate='one_to_one')
    dates=pd.to_datetime(joined.exif_datetime,format='%Y:%m:%d %H:%M:%S',errors='coerce').dt.date
    # Connected components across batch/date: expose why independent batch AND session
    # separation can be difficult; no final split is selected by this audit.
    parent={}
    def find(x):
        parent.setdefault(x,x)
        if parent[x]!=x:parent[x]=find(parent[x])
        return parent[x]
    def union(a,b):parent[find(a)]=find(b)
    for row,date in zip(joined.to_dict('records'),dates):
        lid='id:'+str(row['L_ID']);find(lid)
        if pd.notna(row['Batch_ID']):union(lid,'batch:'+str(row['Batch_ID']))
        if pd.notna(date):union(lid,'session_date:'+str(date))
    result['batch_and_exif_date_connected_component_sizes']=sorted(Counter(find('id:'+str(x)) for x in joined.L_ID).values(),reverse=True)
    # Display repeated-source variants and empty annotations for manual review.
    chosen=m[m.base_name.eq('001_jpg')].head(3).path.tolist()+m[m.label_count.eq(0)].path.tolist()
    samples=[]
    for name in chosen:
        rec,im=inspect_image(name,(ROOT/name).read_bytes(),'multi')
        samples.append((rec,im,[]))
    contact_sheet(samples,'multi_duplicate_and_empty_review.png')
    # Representative full-frame single images plus center crops for morphology.
    with zipfile.ZipFile(DATA/'Single Larvae data.zip') as z:
        selected=[1,200,600,1102,1371,1613]
        rows=s[s.filename_id.isin(selected)].to_dict('records')
        fig,axes=plt.subplots(len(rows),2,figsize=(11,3.4*len(rows)))
        for axs,row in zip(axes,rows):
            with Image.open(io.BytesIO(z.read(row['path']))) as im:
                im.load();axs[0].imshow(im);axs[0].set_title(Path(row['path']).name+' full frame')
                # Fixed central window, explicitly not a detector-derived crop.
                w,h=im.size;axs[1].imshow(im.crop((w*.3,h*.3,w*.7,h*.7)))
                axs[1].set_title('Central 40% diagnostic crop (uncalibrated)')
                for ax in axs:ax.axis('off')
        fig.tight_layout();fig.savefig(OUT/'single_detail_review.png',dpi=120);plt.close(fig)
    json_save('supplementary_checks.json',result)
    print(json.dumps(result,default=str),flush=True)


if __name__=='__main__':
    if '--supplement' in sys.argv:supplemental()
    else:
        main()
        supplemental()
