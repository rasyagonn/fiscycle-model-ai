"""Apply explicit user batch approval, holding documented risks for human review.

References existing versioned labels/crops; never synthesizes per-image checklists.
"""
import json
from datetime import datetime,timezone,timedelta
from pathlib import Path
import pandas as pd
import numpy as np
import finalize_model_a as f

OUT=f.ROOT/'hasil/model_a_approval_v2'
AUTHORIZATION='udah, gini aja, approved semuanya kecuali yang kamu anggep masi salah, nah itu yang aku jadikan human test'
RISK_COLUMNS=['border_touch_polygons','tiny_polygons_under_64px','coarse_polygons_5_vertices_or_less',
              'overlap_pairs_over_5pct','high_iou_pairs_over_80pct']


def main():
    assert not OUT.exists(),'Version already exists; preserve it'
    f.verify_package(full=True)
    items=f.read_json(f.OUT/'review_items.json')
    a1=pd.read_csv(f.QA/'a1_prioritized_review_queue.csv').set_index('image_path')
    a2=pd.read_csv(f.OUT/'a2_working_manifest.csv').set_index('review_id')
    human_path=f.ROOT/'hasil/model_a_human_decisions.json'
    human=f.read_json(human_path)
    assert human['package_hash']==f.sha(f.OUT/'review_items.json')
    old_snapshot=f.OUT/'review_snapshots'/f.sha(human_path)[:16]
    for name,digest in f.read_json(old_snapshot/'FREEZE.json')['files'].items():
        assert f.sha(old_snapshot/name)==digest,name
    previous={d['id']:d for d in human['decisions']}
    original2=pd.read_csv(f.FROZEN/'a2_manifest.csv').set_index('L_ID')
    rows=[]; accepted=[]; held=[]
    recorded_at=datetime.now(timezone(timedelta(hours=7))).isoformat()
    for e in items:
        prior=previous.get(e['id'])
        if prior: f.validate_decision(prior,e)
        reasons=[]
        if e['hard_hold']: reasons.append('EXISTING_HARD_HOLD')
        if prior and prior['decision']!='approve': reasons.append('PRIOR_HUMAN_'+prior['decision'].upper())
        if e['track']=='A1':
            q=a1.loc[e['source_path']]
            reasons.extend(c for c in RISK_COLUMNS if q[c]>0)
            if 'POSSIBLE_MISSED_ANNOTATIONS' in str(q.eligibility_status): reasons.append('SUSPECTED_MISSING_ANNOTATIONS')
            if q.agent_visual_status in ['NEEDS_CORRECTION','NEEDS_ADJUDICATION','KEEP_EXCLUDED']:
                reasons.append('AGENT_VISUAL_'+q.agent_visual_status)
            if any(c['type']=='PROPOSE_REMOVE_POSSIBLE_DUPLICATE' for c in e['changes']):
                reasons.append('DUPLICATE_REMOVAL_NOT_RESOLVED')
            polygons=prior['polygons'] if prior and prior['decision']=='approve' else e['proposed_polygons']
            try: f.validate_polygons(polygons,enforce_visibility=True)
            except ValueError as exc: reasons.append('INVALID_GEOMETRY:'+str(exc))
            assert f.sha(f.ROOT/e['source_path'])==e['source_sha256']
            assert f.sha(f.ROOT/e['source_label_path'])==e['source_label_sha256']
            # Use actual individually accepted edits when available; otherwise the proposal.
            if prior and prior['decision']=='approve':
                snapshot=f.OUT/'review_snapshots'/f.sha(human_path)[:16]
                artifact=snapshot/'labels'/(e['id']+'.txt')
                assert artifact.exists()
                parsed=f.parse_labels(artifact)
                assert len(parsed)==len(polygons)
                for old,new in zip(parsed,polygons):
                    assert old['source_class']==0 and np.allclose(old['points'],new['points'],rtol=0,atol=1e-11)
            else: artifact=f.OUT/e['proposed_label_path']
            source=e['source_path']; rank=int(q.review_rank)
        else:
            q=a2.loc[e['id']]
            if q.status=='HOLD': reasons.append(str(q.hold_reasons))
            if not q.roi_found: reasons.append('NO_CANDIDATE')
            artifact=f.OUT/e['crop_url'] if e['crop_url'] else None
            if artifact: assert f.sha(artifact)==e['crop_sha256']
            source=e['archive_path']+'::'+e['archive_member'];rank=1000+int(e['L_ID'])
        permitted=e['split'] in ('train','validation','test')
        approved=permitted and not reasons
        row=dict(id=e['id'],track=e['track'],image_id=e['image_id'],split=e['split'],
                 reserved_group_split=e['reserved_group_split'],split_group_id=e['split_group_id'],
                 source_path=source,source_sha256=e['source_sha256'],source_label_sha256=e.get('source_label_sha256',''),
                 artifact_path=artifact.relative_to(f.ROOT).as_posix() if artifact else '',
                 artifact_sha256=f.sha(artifact) if artifact else '',proposal_hash=e['proposal_hash'],
                 status='APPROVED' if approved else 'HELD_FOR_HUMAN_REVIEW',hold_reasons='|'.join(reasons),
                 approval_basis=('INDIVIDUAL_REVIEW_JSON' if prior and prior['decision']=='approve' else 'USER_BATCH_AUTHORIZATION') if approved else '',
                 individual_review_record_exists=bool(prior),individual_decision=prior['decision'] if prior else '',
                 prior_approval_held=bool(prior and prior['decision']=='approve' and not approved),
                 human_reviewed_at=prior['reviewed_at'] if prior else '',authorization_recorded_at=recorded_at,
                 reviewer='Rasya',training_eligible=approved and e['split']=='train',
                 validation_or_test_reserved=approved and e['split'] in ('validation','test'),
                 label_completeness_certified=False,rank=rank,L_ID=e.get('L_ID',''),
                 annotation_or_crop_version=e.get('method_version',f.POLICY['version']))
        if e['track']=='A2':
            meta=original2.loc[e['L_ID']]
            row.update(Batch_ID=meta.Batch_ID,measured_weight_g=float(meta.Weight),Length=float(meta.Length),
                       Width=float(meta.Width) if pd.notna(meta.Width) else None,width_valid=bool(meta.width_valid))
        rows.append(row)
        (accepted if approved else held).append(row)
    # Quarantine and unprocessed final test are reservations, never silently approved.
    for lid,meta in original2[~original2.split.isin(['train','validation'])].iterrows():
        rows.append(dict(id=f'A2_{lid:04}',track='A2',image_id=f'{lid:04}',L_ID=lid,split=meta.split,
                         reserved_group_split=meta.reserved_group_split,split_group_id=meta.split_group_id,
                         source_sha256=meta.image_sha256,status='RESERVED_TEST_NOT_PROCESSED' if meta.split=='test' else 'FROZEN_QUARANTINE',
                         hold_reasons='No development crop; original reservation retained',training_eligible=False))
    OUT.mkdir()
    ledger=pd.DataFrame(rows);good=pd.DataFrame(accepted);queue=pd.DataFrame(held).sort_values('rank')
    for name,df in [('eligibility_manifest.csv',ledger),('approved_working_manifest.csv',good),('human_review_queue.csv',queue)]:
        df.to_csv(OUT/name,index=False)
    policy={'version':'user_batch_approval_v2','authorization_text':AUTHORIZATION,'recorded_at':recorded_at,
            'authorizer':'Rasya','scope':'All eligible reviewed-package candidates except documented unresolved risks',
            'approval_method':'Explicit conversation-level batch authorization; not independent per-image clicks',
            'per_image_checklists_synthesized':False,'scientific_completeness_certified':False,
            'policy_change':'User authorizes batch acceptance in place of individual clicking; earlier per-image records preserved',
            'a1_hold_rules':RISK_COLUMNS+['suspected missing annotations','agent correction/adjudication','unresolved duplicate removal','invalid geometry','prior human non-approval','frozen exclusions'],
            'a2_hold_rule':'All HOLD rows (including heuristic suspicion) and prior human non-approval remain in manual review',
            'human_test_meaning':'Manual review queue; not a new statistical test split',
            'previous_approvals':'Preserved as historical evidence; unresolved risk may hold prior approval in this new version',
            'test_policy':'Never train on validation/test; A2 final test not processed or approved'}
    f.write_json(OUT/'approval_policy.json',policy)
    coverage=[]
    for (split,batch),g in original2[original2.split.isin(['train','validation'])].groupby(['split','Batch_ID']):
        chosen=good[(good.track=='A2')&(good.split==split)&(good.Batch_ID==batch)]
        coverage.append(dict(split=split,batch=batch,available=len(g),approved=len(chosen),fraction=len(chosen)/len(g),
                             **{f'weight_{k}':v for k,v in f.summarize(chosen.measured_weight_g).items()}))
    pd.DataFrame(coverage).to_csv(OUT/'a2_coverage.csv',index=False)
    summary={'approved':good.groupby(['track','split']).size().to_dict(),
             'held':queue.groupby(['track','split']).size().to_dict(),
             'prior_approvals_held':int(queue.prior_approval_held.sum()),
             'training_executed':False}
    summary={k:({' / '.join(key):int(value) for key,value in v.items()} if isinstance(v,dict) else v) for k,v in summary.items()}
    f.write_json(OUT/'summary.json',summary)
    # Reuse every image and the old export binding; only select the manual-review queue.
    page=(f.OUT/'review_cepat.html').read_text(encoding='utf-8')
    page=page.replace('<meta charset="utf-8">','<meta charset="utf-8"><base href="../model_a_finalization_v1/">')
    ids={r['id']:r['hold_reasons'] for r in held}
    selection='<script>const manualReviewReasons='+json.dumps(ids)+';window.REVIEW_DATA.items=window.REVIEW_DATA.items.filter(e=>Object.hasOwn(manualReviewReasons,e.id));window.REVIEW_DATA.items.forEach(e=>e.issues="MANUAL REVIEW: "+manualReviewReasons[e.id]+"; "+e.issues);</script>'
    page=page.replace('<script src="review.js"></script>',selection+'<script src="review.js"></script>')
    page=page.replace('Model A — Review cepat','Model A — Antrean human review')
    page=page.replace('Tidak ada gambar yang disetujui otomatis.','Antrean kasus yang ditahan. Status browser lama tidak membatalkan hold pada manifest v2; keputusan baru harus diimpor dan direkonsiliasi.')
    (OUT/'human_review.html').write_text(page,encoding='utf-8')
    (OUT/'README.md').write_text('''# Persetujuan massal Model A v2

User memberi persetujuan massal melalui percakapan untuk kandidat selain yang masih bermasalah. Lihat `approval_policy.json` untuk teks dan provenance. Tidak dibuat klik, checklist atau waktu pemeriksaan individu palsu. `human_reviewed_at` hanya terisi jika ada keputusan asli dalam JSON.

`approved_working_manifest.csv` adalah subset yang disetujui berdasarkan kebijakan baru. Path artifact relatif terhadap folder domain fiscycle-bsf-ai; tidak ada duplikasi ribuan file. Setiap artifact dan sumber terikat SHA-256. `label_completeness_certified=False` berarti persetujuan pengguna bukan sertifikasi ilmiah bahwa anotasi lengkap.

`human_review.html` menampilkan hanya kasus yang ditahan, memakai gambar lama. `human_review_queue.csv` memuat alasan per gambar. Flag risiko adalah dugaan, bukan selalu kesalahan yang terbukti. A1 border/overlap dapat diterima kemudian jika mask visible benar dan identitas jelas. Kepadatan atau sedikit label saja tidak otomatis dianggap salah.

Keputusan needs_revision/reject terdahulu tetap ditahan. Persetujuan lama yang berbenturan dengan flag risiko juga ditahan dalam versi ini; catatan asli dan snapshot v1 tetap utuh. Review berikutnya harus menyelesaikan alasan hold secara eksplisit; ekspor JSON lama tidak otomatis menghapus hold v2.

Human test di sini berarti review manual. Split frozen tidak berubah. Validation/test tidak boleh masuk training. A2 test 178 gambar belum diproses; quarantine tidak disahkan. Gambar bukan replikasi biologis independen. A1 validation hanya satu primary group; A2 final test juga satu.

Tidak ada training dijalankan. Subset ini bisa menjadi dasar eksperimen research terkontrol setelah instruksi training; klaim metrik tetap perlu pengungkapan label yang diterima massal, bias seleksi dan keterbatasan group. Hasil bukan field-validated. Coverage per batch/berat ada di a2_coverage.csv.
''',encoding='utf-8')
    f.write_json(OUT/'FREEZE.json',{'status':'USER_AUTHORIZED_BATCH_SUBSET_NOT_PER_IMAGE_CERTIFICATION',
         'recorded_at':recorded_at,'builder_sha256':f.sha(Path(__file__)),
         'original_package_sha256':f.sha(f.OUT/'PACKAGE_RECEIPT.json'),
         'original_review_json_sha256':f.sha(human_path),'original_split_freeze_sha256':f.sha(f.FROZEN/'FREEZE.json'),
         'approved_count':len(good),'held_for_human_review_count':len(queue),
         'files':{p.name:f.sha(p) for p in sorted(OUT.iterdir()) if p.is_file()}})
    assert len(ledger)==1929 and len(good)+len(queue)==1435
    assert not good.loc[good.split!='train','training_eligible'].any()
    print(json.dumps(summary,indent=2))


if __name__=='__main__': main()
