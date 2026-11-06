"""Create the measured experiment report and integrity receipt after all stages finish."""
from train_model_a import ROOT,OUT,PREP,REVIEW,STATUS,save,f
from pathlib import Path
import json
import pandas as pd
import numpy as np

def main():
    assert not (OUT/'EXPERIMENT_RECEIPT.json').exists(),'Preserve completed experiment'
    smoke=f.read_json(OUT/'inference_smoke_test.json');assert smoke['passed']
    dataset=f.read_json(OUT/'dataset_receipt.json')
    for name,h in dataset['files'].items():assert f.sha(OUT/name)==h,name
    assert f.sha(PREP/'FREEZE.json')==dataset['source_split_freeze']
    assert f.sha(REVIEW/'FREEZE.json')==dataset['review_v3_freeze']
    f.verify_package(full=True)
    for name,h in dataset['protected_b1'].items():assert f.sha(ROOT/name)==h,name
    for name,h in f.read_json(REVIEW/'FREEZE.json')['files'].items():assert f.sha(REVIEW/name)==h,name
    a1=f.read_json(OUT/'a1_diagnostics/metrics.json');count=f.read_json(OUT/'a1_diagnostics/count_summary.json')
    curves=pd.read_csv(OUT/'a1_initial/results.csv');assert np.isfinite(curves.select_dtypes('number')).all().all()
    best_epoch=int(curves.loc[(curves['metrics/mAP50-95(B)']+curves['metrics/mAP50-95(M)']).idxmax(),'epoch'])
    base=f.read_json(OUT/'a2_baselines/metrics.json');comp=f.read_json(OUT/'a2_diagnostics/comparison.json')
    visual=f.read_json(OUT/'visual_error_analysis.json')
    a1df=pd.read_csv(OUT/'a1_development_manifest.csv');a2df=pd.read_csv(OUT/'a2_development_manifest.csv')
    for df in [a1df,a2df]:
        assert set(df.split)=={'train','validation'}
        assert not set(df[df.split=='train'].split_group_id)&set(df[df.split=='validation'].split_group_id)
    a2selection=comp['selected'];initial=comp['candidates']['a2_initial'];improved=comp['candidates'].get('a2_improved')
    selection=f.read_json(OUT/'selected_models.json')
    masks=a1['metrics'];baseline_table='\n'.join(f"| {name} | {b['full_validation']['MAE_mg']:.3f} | {b['full_validation']['RMSE_mg']:.3f} | {b['full_validation']['bias_mg']:.3f} |" for name,b in base.items())
    comparison_table='\n'.join(f"| {name} | {b['MAE_mg']:.3f} | {b['RMSE_mg']:.3f} | {b['bias_mg']:.3f} |" for name,b in comp['models'].items())
    report=f'''# Fiscycle Model A — experimental training v1

## A. Execution Summary

**{STATUS} / RESEARCH_PROTOTYPE / NOT_FIELD_VALIDATED.** Level 1 sanity dan Level 2 exploratory benar-benar dijalankan untuk A1 dan A2. Tiga baseline A2 fitted, checkpoint neural tersimpan, inference standalone lulus smoke test. Level 3 tidak dilakukan: final test A1 46 dan A2 178 tetap tidak dipakai. Tidak ada API atau integrasi A1→A2→B1.

CPU Intel i5-11400H, 4 thread dikonfigurasi; RTX 2050 4GB tersedia secara hardware tetapi torch terpasang CPU-only. RAM sistem sekitar 7.7GB dengan sekitar 1GB tersedia saat inspeksi. Memakai model kecil, workers=0, tanpa image cache RAM. Seed 20261105; versi dependency ada di `environment.json`. Dua checkpoint pretrained resmi total sekitar 16MB, provenance dan SHA di `pretrained/provenance.json`.

Instruksi exploratory baru mengizinkan label development belum disahkan. Field approval historis tetap disalin tanpa diubah. File sumber, split, finalisasi/QA/review sebelumnya, serta B1 diverifikasi hash sebelum dan sesudah. Tidak ada modifikasi Water Quality. Sumber data: Quentin Geissmann, Zenodo v1 13359376 (2024), CC BY 4.0; atribusi audit tetap berlaku.

## B. A1 Training

YOLO11n-seg pretrained COCO, input 320, batch 2, AdamW lr0=0.001, maximum 25 epoch, patience 7. Augmentasi sinkron gambar/polygon: flips, rotasi ±10°, translasi 5%, scale ±15%, perubahan warna ringan; mosaic/mixup/copy-paste nonaktif. `overlap_mask=False` menjaga mask instance terpisah. Pemetaan source 0/1→visible_bsf_larva merupakan keputusan rekayasa, bukan ekuivalensi biologis.

Frozen train 204 → **166 digunakan, 38 dikeluarkan** (33 di bawah batas visibility geometry lama; 5 explicit human reject). Frozen validation **61/61 digunakan**, 546 instance anotasi; train 2999 instance. Incomplete/unreviewed labels boleh ikut: 5 train dan 17 validation yang held pada v3 ikut eksplorasi. Tidak ada mask ditebak; tidak ada proposed duplicate removal otomatis dipakai. Redundant closing vertex saja dinormalisasi. Semua physical instance sumber tetap terpisah pada gambar yang dipakai.

Sanity 1 epoch pada 12 train/8 validation menghasilkan finite loss dan checkpoint reload. Tidak ada deteksi pada contoh reload di conf 0.05; mask-output diagnostik diverifikasi pada conf 0.001. Ini bukan ukuran keberhasilan deteksi. Training utama menyelesaikan **{len(curves)} epoch**; best/last ada di `a1_initial/weights/`. Framework memilih best memakai development-validation fitness; logged fitness tertinggi ada pada **epoch {best_epoch}**.

Hasil best checkpoint pada 61 validation (provisional):

| Mask metric | Nilai |
|---|---:|
| Precision | {masks['metrics/precision(M)']:.5f} |
| Recall | {masks['metrics/recall(M)']:.5f} |
| mAP50 | {masks['metrics/mAP50(M)']:.5f} |
| mAP50–95 | {masks['metrics/mAP50-95(M)']:.5f} |

Count pada confidence 0.25: total predicted **{count['predicted_total']}**, annotated **{count['annotated_total']}**, MAE count terhadap anotasi **{count['count_MAE_vs_incomplete_annotations']:.3f}**. Ini selisih terhadap label tidak lengkap, bukan error count biologis terverifikasi. Precision/recall framework memakai operating point internal, berbeda dari threshold count. Prediksi tambahan tidak otomatis false positive. Panel source-label vs prediction dan antrean 12 kasus ada di `a1_diagnostics/`. Empat probe train paling padat mencapai cap **300 deteksi**, dengan mask kasar/blocky dan overlap: count adegan padat belum reliabel. Inference mengembalikan `detection_limit_reached` ketika cap tercapai. Validation tidak mencakup high-density scenes; contoh padat bukan generalization test.

## C. A2 Baselines

924 train, 190 development-validation; Weight g×1000→mg. Mean memakai train mean. Linear memakai Length manual; Ridge alpha=1 dengan StandardScaler fitted train saja. Width/Sex/ID/batch bukan fitur. Model `.joblib` dan prediksi per baris tersimpan.

| Model | MAE mg | RMSE mg | Bias mg |
|---|---:|---:|---:|
{baseline_table}

## D. A2 Image Training

MobileNetV3 Small pretrained ImageNet1K_V1, regression head 576→128→1, input RGB crop 160×160 dari letterbox v2 512×512. Train **456/924**, validation **152/190**; excluded/held train 468 dan validation 38. Seleksi memakai QA piksel/visual v3, bukan residual atau target berat. Model hanya memakai piksel; mean/std target fitted pada train. Protokol wet/dry UNKNOWN, output `predicted_measured_weight_mg`.

Initial: frozen pretrained feature backbone + trained head, maximum 20 epoch, early stop patience 5; selesai {initial['completed_epochs']} epoch, best epoch {initial['best_epoch']}. Ini transfer learning dengan head benar-benar dilatih, bukan model acak. Perbaikan terbatas membuka tiga blok feature terakhir, lr 0.0002, flips/rotasi 90° yang menjaga seluruh tubuh; batchnorm tetap eval untuk mencegah statistik batch kecil bergeser. Kedua checkpoint dipertahankan. Konfigurasi, learning curves, prediksi, error per batch dan plot residual tersedia per run.

Perbandingan pada **152 ID validation yang sama** (Length adalah benchmark referensi dengan pengukuran manual, bukan input-equivalent):

| Model | MAE mg | RMSE mg | Bias mg |
|---|---:|---:|---:|
{comparison_table}

Mean/Length/Ridge utama fitted pada 924 train; `eligible_train_mean` memberi pembanding mean pada 456 train citra yang sama. Tidak ada klaim hasil image model mencakup seluruh 190 validation.

## E. Error Analysis

Temuan visual development dan pembedaan observasi/hipotesis ada di `visual_error_analysis.json`. Panel A1 membandingkan actual annotation dengan prediksi; A2 memperlihatkan contoh error terbesar/terkecil beserta measured/predicted mg. Antrean ini menargetkan sejumlah kasus, bukan meminta review ulang semua dataset. A1_2d202b776bdbd859 dan A1_e8de6b4740cfeb5c memperlihatkan larva nyata tanpa anotasi yang berhasil dideteksi; A1_478febe1ffa4806e masih kehilangan partial bodies di border. A1_01a886178d6862b9 memberi contoh berguna 11 anotasi/11 prediksi, tanpa mengklaim semua kontur sempurna.

Pada A2 terpilih, bobot >240mg (46 validation) punya MAE **80.510mg**, seluruhnya underprediction. Bobot <180mg (55 gambar) punya bias **+24.001mg**. Batch B006 MAE **32.044mg**, B013 **61.895mg**. Contoh A2_1448: measured341mg, predicted196.107mg; A2_0610:353mg vs214.678mg. Tubuh tetap tampak utuh dalam preview delapan error terbesar; tidak terlihat kegagalan gross wrong-object/body-cutting. Ada noda samar dekat kepala A2_1448 untuk ditinjau, tetapi tidak dibuktikan sebagai penyebab error. Prioritas perbaikan: (1) uji informasi ukuran yang hilang saat crop dinormalisasi, (2) lengkapi anotasi A1 pada antrean kecil, (3) pulihkan coverage batch A2 dengan crop yang benar-benar bebas shortcut. Jangan menghapus contoh berat hanya karena residual besar.

Baseline Length menunjukkan underprediction pada bobot besar; bias penuh {base['length_linear']['full_validation']['bias_mg']:.3f} mg. Error berbeda menurut batch. Batch/scene shift, incomplete masks, penghilangan skala absolut akibat normalisasi ROI, dan ketimpangan populasi crop merupakan penjelasan kandidat; bukan kausalitas yang sudah dibuktikan. Tidak ada sampel dihapus hanya karena residual besar.

## F. Improvement Comparison

Initial image MAE: {initial['overall']['MAE_mg']:.3f} mg. Revised: {improved['overall']['MAE_mg'] if improved else 'not run'} mg. Kandidat terpilih **{a2selection}** berdasarkan MAE development-validation. Revised berhenti pada 8 epoch, best epoch3. Penurunan MAE hanya **0.195mg / sekitar 0.49%**; RMSE memburuk 51.213→51.567mg dan bias -18.438→-20.960mg. Tidak ada bukti perbaikan kuat atau signifikan. Lihat `a2_improved/improvement_rationale.json` untuk alasan yang dicatat sebelum retraining. Split, eligible IDs dan protokol evaluasi tidak berubah. Tidak ada pengulangan tuning tak terbatas. A1 initial tetap dipertahankan; perbaikan label A1 memerlukan koreksi terarah manusia, tidak dibuat otomatis.

## G. Saved Artifacts

Semua hasil di `{OUT}`. Kode di domain BSF: `train_model_a.py`, `diagnose_model_a.py`, `model_a_inference.py`, `finish_model_a_experiment.py`. Model yang dipilih direkam pada `selected_models.json`.

- A1: `a1_initial/weights/best.pt`, `last.pt`, `args.yaml`, `results.csv`.
- A2: `a2_initial/best.pt`, `last.pt`; `a2_improved/best.pt`, `last.pt`; config/metrics/predictions masing-masing.
- Baselines: `a2_baselines/mean.joblib`, `length_linear.joblib`, `length_ridge.joblib`.
- Manifest: `a1_development_manifest.csv`, `a2_development_manifest.csv`, `a2_tabular_development.csv`; field eksperimen terpisah dari approval.
- Smoke: `inference_smoke_test.json`; laporan/metrik di direktori diagnostics.

Dari root repository, gunakan:

```powershell
python -B .agents/skills/fiscycle-bsf-ai/model_a_inference.py a1 PATH_GAMBAR
python -B .agents/skills/fiscycle-bsf-ai/model_a_inference.py a2 PATH_SINGLE_LARVA
python -B .agents/skills/fiscycle-bsf-ai/model_a_inference.py a2 PATH_CROP_V2_512 --preprocessed
python -B .agents/skills/fiscycle-bsf-ai/diagnose_model_a.py smoke
```

Python: `from model_a_inference import predict_larvae, predict_measured_weight`. A2 raw-photo ROI dapat abstain ketika candidate tidak ada atau screen menandai truncation/shortcut. Screen bukan jaminan crop benar; input crop eksplisit harus berformat v2. Tidak ada interval confidence berat buatan. A1 detector confidence bukan probabilitas terkalibrasi.

Reproduksi training memakai stage `prepare`, `baselines`, `a1_sanity`, `a1_train`, `a2_sanity`, `a2_train`, `a2_improve`; output versi ini menolak overwrite checkpoint. Untuk run ulang, tetapkan OUT ke nama versi baru dan gunakan input frozen yang sama. Sumber pretrained: [Ultralytics segmentation](https://docs.ultralytics.com/tasks/segment/), [training arguments](https://docs.ultralytics.com/modes/train/), [Torchvision MobileNetV3 Small](https://docs.pytorch.org/vision/main/models/generated/torchvision.models.mobilenet_v3_small.html). Lisensi Ultralytics dan atribusi dataset perlu dibawa pada penggunaan/redistribusi berikutnya.

## H. Remaining Limitations

A1 validation hanya **satu primary group**; A2 final test juga **satu primary group**. Jumlah gambar bukan replikasi biologis independen. Missing larvae bisa diperlakukan sebagai background oleh supervised loss dan mencemari precision/recall. Sebagian source variants berkorelasi. A2 crop screening sangat mengurangi batch B008/B009/B010, sehingga distribusi train berubah; subset tidak mewakili semua data asal. Review AI preview bukan human certification. ROI rescaling tidak memberi kalibrasi millimeter. Weight belum dikonfirmasi wet/dry. Domain laboratorium/tray tidak sama dengan kamera kandang atau crop A1. Paparan historis gambar A2 test 1102 pada QA terdahulu tetap diungkap; tidak ada gambar/prediksi test dipakai pada training task ini.

## I. Next Action

{visual['highest_value_followup']}

Status akhir: GO untuk penggunaan eksperimen dan pengujian inference internal, NO-GO untuk klaim final-test/produksi/field validation.
'''
    (OUT/'EXPERIMENT_REPORT.md').write_text(report,encoding='utf-8')
    save(OUT/'EXPERIMENT_RECEIPT.json',dict(status=STATUS,training_executed=True,final_test_evaluated=False,
        code={name:f.sha(ROOT/name) for name in ['train_model_a.py','diagnose_model_a.py','model_a_inference.py','finish_model_a_experiment.py']},
        files={p.relative_to(OUT).as_posix():f.sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts},
        raw_and_b1_integrity='PASS',frozen_split_integrity='PASS',inference_smoke='PASS'))
    print('COMPLETE:',OUT/'EXPERIMENT_REPORT.md')

if __name__=='__main__':main()
