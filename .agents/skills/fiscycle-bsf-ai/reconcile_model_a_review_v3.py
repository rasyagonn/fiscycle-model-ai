"""Reconcile actual review 2 and delegated AI triage without changing frozen inputs."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pandas as pd
from PIL import Image,ImageDraw,ImageFont
import finalize_model_a as f

OUT=f.ROOT/'hasil/model_a_review_v3'
PREVIOUS=f.ROOT/'hasil/model_a_approval_v2'
REVIEW=f.ROOT/'hasil/model_a_human_decisions_2.json'
FONT=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',17)


def prepare():
    assert not (OUT/'FREEZE.json').exists()
    f.verify_package(full=False)
    old=f.read_json(PREVIOUS/'FREEZE.json')
    for name,h in old['files'].items(): assert f.sha(PREVIOUS/name)==h,name
    review=f.read_json(REVIEW)
    assert review['package_hash']==f.sha(f.OUT/'review_items.json')
    ds={d['id']:d for d in review['decisions']}
    assert len(ds)==len(review['decisions'])
    entries={e['id']:e for e in f.read_json(f.OUT/'review_items.json')}
    validation=[]
    for d in ds.values():
        try: f.validate_decision(d,entries[d['id']]);error=''
        except ValueError as exc: error=str(exc)
        validation.append(dict(id=d['id'],track=entries[d['id']]['track'],split=d['split'],decision=d['decision'],error=error))
    queue=pd.read_csv(PREVIOUS/'human_review_queue.csv')
    todo=[entries[r.id] for r in queue[queue.track=='A2'].itertuples() if r.id not in ds and not entries[r.id]['hard_hold']]
    OUT.mkdir(exist_ok=True);(OUT/'a2_triage_sheets').mkdir(exist_ok=True)
    pd.DataFrame(validation).to_csv(OUT/'human_review_validation.csv',index=False)
    f.write_json(OUT/'review2_provenance.json',{'source':str(REVIEW.relative_to(f.ROOT)),'sha256':f.sha(REVIEW),
        'actual_human_decisions':len(ds),'ai_visual_todo':len(todo),
        'delegation':'User requests assistant to check remaining A2 cases; AI observations are not human clicks'})
    index=[]
    for start in range(0,len(todo),16):
        sheet=Image.new('RGB',(1536,1200),'#eeeeee');draw=ImageDraw.Draw(sheet)
        for offset,e in enumerate(todo[start:start+16]):
            x=(offset%4)*384;y=(offset//4)*300
            with Image.open(f.OUT/e['crop_url']) as im: sheet.paste(im.resize((256,256)),(x,y+30))
            with Image.open(f.OUT/e['image_url']) as im:
                context=im.copy();context.thumbnail((128,128))
                b=e['crop_bbox'];s=context.width/e['width'];d=ImageDraw.Draw(context)
                d.rectangle((b[0]*s,b[1]*s,b[2]*s,b[3]*s),outline='#00aa00',width=1)
                sheet.paste(context,(x+256,y+30))
            draw.text((x+5,y+4),e['id']+' '+e['split'],font=FONT,fill='black')
            index.append(dict(id=e['id'],sheet=f'{start//16+1:02}.jpg',position=offset+1,split=e['split'],
                              crop_sha256=e['crop_sha256'],source_sha256=e['source_sha256']))
        sheet.save(OUT/'a2_triage_sheets'/f'{start//16+1:02}.jpg',quality=95)
    pd.DataFrame(index).to_csv(OUT/'a2_triage_index.csv',index=False)
    print(json.dumps({'sheets':(len(todo)+15)//16,'images':len(todo),'invalid_human_decisions':sum(bool(r['error']) for r in validation)}))


def finalize():
    assert not (OUT/'FREEZE.json').exists(), 'Preserve completed version'
    f.verify_package(full=True)
    for name,h in f.read_json(PREVIOUS/'FREEZE.json')['files'].items():
        assert f.sha(PREVIOUS/name)==h,name
    provenance=f.read_json(OUT/'review2_provenance.json')
    assert f.sha(REVIEW)==provenance['sha256']
    review=f.read_json(REVIEW)
    assert review['package_hash']==f.sha(f.OUT/'review_items.json')
    ds={d['id']:d for d in review['decisions']}
    assert len(ds)==len(review['decisions'])==220
    entries={e['id']:e for e in f.read_json(f.OUT/'review_items.json')}
    old=pd.read_csv(PREVIOUS/'eligibility_manifest.csv',keep_default_na=False)
    qa=pd.read_csv(f.QA/'a1_prioritized_review_queue.csv',keep_default_na=False).set_index('image_path')
    ai={}; visual_rows=[]
    clean='NO_OBVIOUS_DEFECT_AT_PREVIEW_SCALE'
    for filename,indexname,kind in [
        ('A2_AI_VISUAL_OBSERVATIONS.json','a2_triage_index.csv','held_candidates'),
        ('A2_REMAINING_VISUAL_OBSERVATIONS.json','a2_remaining_check_index.csv','additional_candidates')]:
        obs=f.read_json(OUT/filename)
        idx=pd.read_csv(OUT/indexname)
        assert set(idx.sheet)==set(obs['inspected_sheets'])
        okay=set(obs.get('no_obvious_defect_ids',[]))
        holds=obs.get('hold_findings',obs.get('specific_hold_findings',{}))
        assert {int(x) for x in holds}.issubset({int(entries[i]['L_ID']) for i in idx.id})
        for r in idx.itertuples():
            e=entries[r.id];lid=int(e['L_ID'])
            assert e['split'] in ['train','validation'] and not e['hard_hold']
            assert r.crop_sha256==e['crop_sha256']
            finding=holds.get(str(lid),clean if kind=='additional_candidates' or lid in okay else obs['remaining_inspected_ids_finding'])
            assert r.id not in ai
            ai[r.id]=finding
            visual_rows.append(dict(id=r.id,split=e['split'],finding=finding,reviewer_kind='AI_AGENT',
                evidence=filename,sheet=r.sheet,crop_sha256=e['crop_sha256'],source_sha256=e['source_sha256']))
    obs=f.read_json(OUT/'A2_HUMAN_APPROVAL_CONFLICT_CHECK.json')
    human_ok=set(obs['no_obvious_defect_ids']);human_holds=obs['hold_findings']
    human_ids={int(entries[k]['L_ID']) for k,d in ds.items() if entries[k]['track']=='A2' and d['decision']=='approve'}
    assert human_ok.isdisjoint({int(k) for k in human_holds})
    assert human_ok|{int(k) for k in human_holds}==human_ids
    for lid in sorted(human_ids):
        key=f'A2_{lid:04}';e=entries[key]
        assert key not in ai
        ai[key]=human_holds.get(str(lid),clean)
        visual_rows.append(dict(id=key,split=e['split'],finding=ai[key],reviewer_kind='AI_AGENT',
            evidence='A2_HUMAN_APPROVAL_CONFLICT_CHECK.json',sheet='a2_human_check_sheets',
            crop_sha256=e['crop_sha256'],source_sha256=e['source_sha256']))
    assert len(ai)==1083
    now=datetime.now(timezone(timedelta(hours=7))).isoformat()
    rows=[];validation=[]
    for original in old.to_dict('records'):
        r=dict(original);key=r['id'];e=entries.get(key)
        r.update(previous_status=r['status'],previous_hold_reasons=r.get('hold_reasons',''),
                 reconciliation_recorded_at=now,ai_visual_finding=ai.get(key,''),
                 human_validation_error='',human_review_source='',human_notes='',
                 reviewer_kind='INHERITED_V2',label_completeness_certified=False)
        if not e:
            assert r['track']=='A2' and r['split'] in ['test','quarantine']
            rows.append(r);continue
        d=ds.get(key);error=''
        if d:
            try:f.validate_decision(d,e)
            except ValueError as exc:error=str(exc)
            validation.append(dict(id=key,track=e['track'],split=e['split'],decision=d['decision'],error=error))
            r.update(individual_review_record_exists=True,individual_decision=d['decision'],
                     human_reviewed_at=d['reviewed_at'],human_review_source=provenance['source'],
                     reviewer=d['reviewer'],human_notes=d.get('notes',''),human_validation_error=error)
        reasons=[];approved=original['status']=='APPROVED';basis=original.get('approval_basis','')
        if e['track']=='A1':
            if d:
                approved=d['decision']=='approve' and not error
                if error:reasons.append('INVALID_HUMAN_APPROVAL:'+error)
                if d['decision']!='approve':reasons.append('HUMAN_'+d['decision'].upper())
                if approved:
                    q=qa.loc[e['source_path']]
                    # Review-2 contains no corrected polygons. An approve click does not fix known missing masks.
                    unchanged=d['polygons']==e['proposed_polygons']
                    if unchanged and q.agent_visual_status in ['NEEDS_CORRECTION','NEEDS_ADJUDICATION','KEEP_EXCLUDED']:
                        reasons.append('UNRESOLVED_AGENT_VISUAL_'+q.agent_visual_status)
                    if unchanged and 'POSSIBLE_MISSED_ANNOTATIONS' in str(q.eligibility_status):
                        reasons.append('UNRESOLVED_SUSPECTED_MISSING_ANNOTATIONS')
                    if 'belum teranotasi' in d.get('notes','').lower():
                        reasons.append('HUMAN_NOTES_REPORT_MISSING_ANNOTATIONS')
                    if not reasons:
                        assert unchanged,'New polygon edits require explicit versioned export implementation'
                        artifact=f.OUT/e['proposed_label_path']
                        r.update(artifact_path=artifact.relative_to(f.ROOT).as_posix(),artifact_sha256=f.sha(artifact))
                        basis='INDIVIDUAL_REVIEW_JSON'
                        r['reviewer_kind']='HUMAN_RECORDED'
                    approved=not reasons
            elif not approved:reasons.append(original['hold_reasons'])
        else:
            approved=False
            if d and d['decision']!='approve':reasons.append('HUMAN_'+d['decision'].upper())
            if error:reasons.append('INVALID_HUMAN_APPROVAL:'+error)
            if key in ai:
                if ai[key]!=clean:reasons.append('AI_VISUAL_'+ai[key])
                approved=not reasons
                basis='INDIVIDUAL_REVIEW_JSON_AND_AI_TRIAGE' if d else 'USER_BATCH_AUTHORIZATION_PLUS_DELEGATED_AI_TRIAGE'
                r['reviewer_kind']='HUMAN_RECORDED_AND_AI_AGENT' if d else 'AI_AGENT_UNDER_USER_AUTHORIZATION'
            elif not reasons:reasons.append(original['hold_reasons'] or 'NO_ACCEPTABLE_CROP_REVIEW')
        if e['hard_hold']:
            reasons.append('EXISTING_HARD_HOLD');approved=False
        if e['split'] not in ['train','validation','test']:approved=False
        if reasons:approved=False
        r.update(status='APPROVED_CONDITIONAL_RESEARCH' if approved else 'HELD_FOR_CORRECTION',
                 hold_reasons='|'.join(dict.fromkeys(reasons)),approval_basis=basis if approved else '',
                 prior_approval_held=bool(r.get('individual_decision')=='approve' and not approved),
                 training_eligible=approved and e['split']=='train',
                 validation_or_test_reserved=approved and e['split'] in ['validation','test'])
        if approved:
            assert not e['hard_hold'] and not error and not reasons
            assert not d or d['decision']=='approve'
            assert f.sha(f.ROOT/r['artifact_path'])==r['artifact_sha256']
            if e['track']=='A1':
                f.validate_polygons(d['polygons'] if d else e['proposed_polygons'],enforce_visibility=True)
                assert f.sha(f.ROOT/e['source_path'])==e['source_sha256']
                assert f.sha(f.ROOT/e['source_label_path'])==e['source_label_sha256']
            else:assert ai[key]==clean
        rows.append(r)
    ledger=pd.DataFrame(rows)
    good=ledger[ledger.status=='APPROVED_CONDITIONAL_RESEARCH'].copy()
    held=ledger[ledger.status=='HELD_FOR_CORRECTION'].copy()
    assert len(ledger)==1929 and len(good)+len(held)==1435
    assert ledger.id.is_unique and ledger.id.tolist()==old.id.tolist()
    for column in ['split','reserved_group_split','split_group_id','source_sha256']:
        assert ledger[column].tolist()==old[column].tolist(),column
    assert not good.loc[good.split!='train','training_eligible'].any()
    assert sum(bool(v['error']) for v in validation)==29
    assert not ledger.loc[ledger.id.isin(ds) & (ledger.individual_decision!='approve'),'training_eligible'].any()
    for name,df in [('eligibility_manifest.csv',ledger),('approved_working_manifest.csv',good),
                    ('held_for_correction.csv',held),('a2_ai_visual_review.csv',pd.DataFrame(visual_rows)),
                    ('human_review_validation.csv',pd.DataFrame(validation))]:
        df.to_csv(OUT/name,index=False)
    dev=ledger[(ledger.track=='A2')&ledger.split.isin(['train','validation'])].copy()
    dev['eligible']=dev.status=='APPROVED_CONDITIONAL_RESEARCH'
    coverage=[]
    for (split,batch),g in dev.groupby(['split','Batch_ID']):
        chosen=g[g.eligible]
        coverage.append(dict(split=split,batch=batch,available=len(g),approved=len(chosen),fraction=len(chosen)/len(g),
            **{f'weight_{k}':v for k,v in f.summarize(pd.to_numeric(chosen.measured_weight_g)).items()}))
    pd.DataFrame(coverage).to_csv(OUT/'a2_coverage.csv',index=False)
    counts=lambda df:{' / '.join(k):int(v) for k,v in df.groupby(['track','split']).size().items()}
    summary=dict(decision='CONDITIONAL GO: controlled research subset only',approved=counts(good),held=counts(held),
        actual_human_decisions=220,invalid_a1_human_approvals=29,a2_ai_visually_inspected=1083,
        a2_human_approvals_held_by_visual_check=len(human_holds),a2_reserved_test_unprocessed=178,
        a2_quarantine_unchanged=316,training_executed=False,full_raw_integrity_verified=True)
    f.write_json(OUT/'summary.json',summary)
    f.write_json(OUT/'approval_policy.json',dict(version='reconciled_review_v3',recorded_at=now,
        human_json_sha256=f.sha(REVIEW),
        user_delegation='aku udh simpan human a 2 ... ya kau lah yang pastiin sendiri tapi overall aku lihat udah oke semua',
        inherited_batch_authorization=f.read_json(PREVIOUS/'approval_policy.json')['authorization_text'],
        synthesized_human_clicks=False,meaning='Conditional research eligibility; AI review is preview-scale triage, not human certification',
        a1_rule='Latest valid human review can resolve geometric risk flags, but unchanged known/suspected missing masks, adjudication, conflicting notes and invalid geometry stay held; otherwise inherit v2',
        a2_rule='All 1083 inspectable development candidates checked visually; hold visible shortcuts/artifacts/body loss, human negative decisions and hard holds',
        split_rule='Frozen memberships retained; held images are a correction queue, never a new test set'))
    table='\n'.join(f"| {k} | {v} |" for k,v in summary['approved'].items())
    report=f'''# Model A review v3 — hasil finalisasi

Keputusan: **CONDITIONAL GO** untuk eksperimen research pertama memakai subset pada `approved_working_manifest.csv`. Belum ada training atau evaluasi model. File ini menggantikan pemilihan subset v2 untuk eksperimen berikutnya; versi lama tetap utuh.

| Track / split | Gambar eligible |
|---|---:|
{table}

Ditahan per split: `{json.dumps(summary['held'])}`. Kolom `training_eligible` hanya benar untuk train. Validation dan test tetap reservasi semula.

JSON kedua berisi 220 keputusan asli. Ada 29 approval A1 yang gagal batas geometri minimum terdokumentasi (luas 16 pixel native kuadrat / sisi pendek bbox 3 pixel). Catatan asli tidak diedit. Approval A1 dengan mask belum diperbaiki dan bukti kekurangan anotasi tetap ditahan, termasuk catatan manusia “masih ada yang belum teranotasi”. Flag border/overlap saja boleh diselesaikan oleh approval manusia valid; tidak direkonstruksi objek yang tertutup. Makna biologis kelas 0/1 tetap UNKNOWN; pemetaan target visible_bsf_larva mengikuti keputusan proyek terdahulu.

A2: 1083 kandidat train/validation diperiksa visual pada preview crop 256 pixel dengan konteks sumber; 31 kasus lain sudah needs_revision atau hard hold, termasuk crop tanpa ROI. Dari 487 kasus awal yang ditahan, 111 tidak memperlihatkan cacat jelas pada preview dan 376 tetap ditahan. Pemeriksaan juga mencakup seluruh 558 kandidat tambahan dan 38 approval manusia: 18 dari 38 masih berbenturan dengan objek latar/penggaris/tulisan, sehingga ditahan. `a2_ai_visual_review.csv` memuat bukti per gambar. Tidak ada klaim semua gambar aman, sertifikasi resolusi penuh, atau checklist manusia buatan.

Preprocessing tetap memakai crop v2 yang sudah ada, mempertahankan aspect ratio dengan padding, tanpa central crop atau perubahan foto asli. Temuan mencakup penggaris/tulisan tertinggal, noda berulang, dan crop memotong tubuh (contoh A2_0474). Ini alasan penyaringan konservatif, bukan bukti terukur bahwa model sudah memakai shortcut. Crop lolos berarti tidak ada cacat jelas pada skala preview; detail kecil dan soft focus masih dapat terlewat.

Keterbatasan: **A1 validation hanya satu primary split group; A2 final test hanya satu primary split group**. Jumlah gambar bukan jumlah sampel biologis independen. Kelengkapan seluruh anotasi A1 validation/test belum tersertifikasi; subset yang diterima juga bukan jaminan seluruh instance benar. Tidak boleh mengubah arsitektur/hyperparameter/preprocessing berdasarkan prediksi test. A2 final test 178 gambar tidak diproses/dievaluasi dalam pekerjaan ini; 316 quarantine tetap. Paparan historis preview A2 test ID 1102 pada QA sebelumnya tetap harus diungkapkan, sehingga tidak mengklaim test sepenuhnya belum pernah dilihat.

Seleksi crop dapat mengubah distribusi batch/berat; lihat `a2_coverage.csv` dan bandingkan baseline pada ID evaluasi yang sama. Target adalah measured Weight (g), protokol wet-weight belum terkonfirmasi. Tidak ada konversi pixel ke millimeter. Tidak ada validasi lapangan, sertifikasi sex/class biologis, atau generalisasi otomatis dari studio/tray ke kandang BSF produk.

Yang siap: manifest subset dengan split, provenance, SHA-256 artifact; labels A1 dan crop A2 yang sudah ada; baseline dan eksperimen train/validation terkontrol setelah instruksi training. Pakai `training_eligible=True`; validation hanya untuk pemilihan di dalam eksperimen; test tetap terkunci sampai protokol final.

Yang masih perlu verifikasi manusia bila ingin dipakai kemudian: anotasi A1 yang kurang/ambigu dan mask terlalu kecil; A2 yang ditahan karena latar/crop; metadata protokol berat, unit Width, dan kalibrasi fisik. Kasus ini boleh tetap dikeluarkan dari eksperimen pertama, tidak perlu approve semuanya sekarang. Review ahli resolusi penuh masih dibutuhkan sebelum menyebut label/crop tersertifikasi atau melakukan klaim produk.

Path artifact relatif terhadap folder fiscycle-bsf-ai. Input raw, frozen split, JSON manusia, versi sebelumnya dan Model B1 terverifikasi hash dan tidak diubah. Waktu pencatatan memakai WIB. Ulangi verifikasi dengan `python -B reconcile_model_a_review_v3.py --verify` dari folder domain; jangan rerun finalisasi pada versi yang sudah frozen.
'''
    (OUT/'READINESS_REPORT.md').write_text(report,encoding='utf-8')
    f.write_json(OUT/'FREEZE.json',dict(status='CONDITIONAL_RESEARCH_SUBSET',recorded_at=now,
        builder_sha256=f.sha(Path(__file__)),human_review_sha256=f.sha(REVIEW),
        previous_freeze_sha256=f.sha(PREVIOUS/'FREEZE.json'),
        original_split_freeze_sha256=f.sha(f.FROZEN/'FREEZE.json'),
        files={p.relative_to(OUT).as_posix():f.sha(p) for p in sorted(OUT.rglob('*')) if p.is_file()},
        referenced_artifacts={r.artifact_path:r.artifact_sha256 for r in good.itertuples()}))
    print(json.dumps(summary,indent=2))


def verify():
    receipt=f.read_json(OUT/'FREEZE.json')
    assert receipt['builder_sha256']==f.sha(Path(__file__))
    assert receipt['human_review_sha256']==f.sha(REVIEW)
    assert receipt['previous_freeze_sha256']==f.sha(PREVIOUS/'FREEZE.json')
    assert receipt['original_split_freeze_sha256']==f.sha(f.FROZEN/'FREEZE.json')
    for name,h in receipt['files'].items():assert f.sha(OUT/name)==h,name
    for name,h in receipt['referenced_artifacts'].items():assert f.sha(f.ROOT/name)==h,name
    f.verify_package(full=False)
    print('PASS: frozen v3 outputs, accepted artifacts, human JSON, original package/splits and protected B1')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    if args.prepare:prepare()
    elif args.verify:verify()
    else:finalize()
