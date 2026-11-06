# Manifest handover Fiscycle — Water/BSF dan galeri lengkap

**READY WITH DOCUMENTED LIMITATIONS**

Release `fiscycle-integrated-research-mvp-2.1.0-gallery`,API `2.1.0`. Sumber utama `app/`; source_revision null karena workspace tidak mempunyai Git metadata. Builder memakai source dan frozen artifacts, bukan handover lama.

| Distribusi | Isi | Ukuran | SHA-256 |
|---|---|---:|---|
| FISCYCLE_DEV_HANDOVER.zip | App/runtime semua model, dua replay, metadata/referensi/baseline galeri, semua thumbnail dan dua dev fixture | 22,050,394 bytes | `a55015499574b83bb6aea5cf5c9f7caa22019a66170201168cf1daf83e2601a9` |
| FISCYCLE_GALLERY_DATA.zip | Semua46 A1+178 A2 test original dan46 source annotation A1,CC BY4.0 | 766,100,663 bytes | `3ed81388e1e3b0f2b63643683e3265cef6d83f40234ee22482671f4d7b133c7b` |

Main package terbaru:338 file,337 checksum payload. Refresh dokumentasi memakai satu build terverifikasi;316 file runtime/model/data identik terhadap release sebelumnya yang telah diuji mandiri. Main ZIP tidak membawa224 test original beresolusi penuh: seluruhnya berada pada optional data ZIP. Total original test yang dihilangkan dari distribusi gabungan: **0**. Semua226 thumbnail dan226 registry record(224 test+2 dev) ada di main package.

Sumber dataset/scientific results baru: `.agents/skills/fiscycle-bsf-ai/hasil/model_a_gallery_v1/`. Sumber frozen tetap pada folder sebelumnya, tidak diedit. Registry/protocol/final evaluation/baseline/bundle receipt disertakan di `service/bsf_assets/gallery/`; database scientific/user state tidak disertakan.

## Source baru pada enhancement ini

- app/gallery_prepare.py — inventory dari frozen manifests, checksum dan pra-registrasi.
- app/gallery_evaluate.py — final pass yang disahkan, penyimpanan hasil dan pelepasan.
- app/gallery_bundle.py — complete data ZIP dan gallery export.
- app/gallery_docs.py — panduan integrasi/deployment yang dihasilkan builder.
- app/gallery_checks.py — pemeriksaan runtime galeri portable.
- app/routers/bsf_gallery.py — HTTP gallery/image/job adapter.
- app/services/bsf_gallery.py — registry, secure source access, cache dan persistent worker.
- app/services/bsf_gallery_roi.py — salinan ranked ROIv2 untuk inference, tanpa training imports.
- app/static/gallery.html, gallery.js, gallery.css — tab galeri dalam shell BSF.
- app/tests/test_bsf_gallery.py, app/tests/test_gallery_portable.py.
- BSF_GALLERY_REPORT.md — inventory, hasil lengkap dan batas ilmiah.

Source yang diubah: app/main.py, core/config.py, static/bsf.html, static/ecosystem.html, static/sw.js, build_handover.py, handover_verify.py, verify_release.py, tests/browser_smoke.py, README.md dan STRUCTURE.md. Bukti app/release_evidence.json dan empat laporan tingkat root diperbarui. Output app/state/ adalah mutable history/cache privat, tidak didistribusikan.

Tidak ada checkpoint,frozen image,frozen annotation,frozen membership atau source training experiment yang diubah. Tidak ada root models/,API kedua atau frontend project kedua.

## Struktur distribusi

```text
FISCYCLE_DEV_HANDOVER/
  README.md
  HANDOVER_MANIFEST.json / .md
  CHECKSUMS.sha256
  VERIFICATION_REPORT.md
  openapi.json
  verify_checksums.py
  docs/                         termasuk GALLERY_INTEGRATION_GUIDE.md dan GALLERY_DEPLOYMENT.md
  integration_examples/
  service/
    app/                        runtime modular,galeri UI/API,checks dan portable pytest
    bsf_assets/
      hasil/...                 checkpoint A1/A2v3 dan config/receipt
      models/                   B1 predictor/estimator/metadata/uncertainty
      replay/                   development seed288baris/16trajektori
      gallery/
        manifest.json
        inventory.json
        evaluation_protocol.json
        final_evaluation.json
        baseline_results.jsonl
        bundle_receipt.json
        deployment.json
        thumbnails/             seluruh226 JPG,tidak disampling
    water_assets/
      models/mvp_v2/            manifest,7ML,2persistence dalam registry
      replay/                   seed299baris,metadata,dictionary,index
    fixtures/                   dua original development train + golden refs
    migrations/
    requirements.txt            CPU lock
    Dockerfile                  belum diuji
    .env.example
    verify_package.py

FISCYCLE_GALLERY_DATA.zip        artefak optional terpisah;salin ke service/atau mount via env
  MANIFEST.json / ATTRIBUTION.txt
  images/                       seluruh224 original,byte/hash sama
  annotations/                  46 label A1 source tanpa perbaikan
```

Daftar **setiap338 file** beserta hash berada pada CHECKSUMS.sha256(selain file checksum sendiri). Semua image ID,filename asal,locator sumber,split,group dan hash terdaftar lengkap pada service/bsf_assets/gallery/manifest.json. ID photo bukan path yang dikirim klien.

## Seluruh endpoint dalam OpenAPI release ini

- `GET /health`
- `GET /water-quality/health`
- `GET /water-quality/models`
- `POST /water-quality/analyze`
- `GET /water-quality/replay/periods`
- `POST /water-quality/replay/sessions`
- `POST /water-quality/replay/sessions/{session_id}/start`
- `POST /water-quality/replay/sessions/{session_id}/pause`
- `POST /water-quality/replay/sessions/{session_id}/next`
- `POST /water-quality/replay/sessions/{session_id}/reset`
- `GET /water-quality/replay/sessions/{session_id}`
- `GET /bsf/health`
- `GET /bsf/models`
- `POST /bsf/next-weight`
- `GET /api/v1/bsf/health`
- `GET /api/v1/bsf/models`
- `POST /api/v1/bsf/segment`
- `POST /api/v1/bsf/analyze-photo`
- `POST /api/v1/bsf/estimate-weight`
- `GET /api/v1/bsf/replay/trajectories`
- `GET /api/v1/bsf/replay/{trajectory_id}`
- `GET /api/v1/bsf/overview`
- `POST /api/v1/bsf/forecast`
- `GET /api/v1/bsf/factors`
- `GET /api/v1/bsf/rules`
- `POST /api/v1/bsf/decision-support`
- `POST /api/v1/bsf/observations`
- `GET /api/v1/bsf/observations`
- `GET /api/v1/bsf/history`
- `GET /api/v1/bsf/history/{record_id}`
- `GET /api/v1/bsf/recommendations/{record_id}`
- `GET /water-quality/rules`
- `GET /water-quality/history`
- `GET /water-quality/history/{record_id}`
- `POST /water-quality/replay/sessions/{session_id}/snapshot`
- `POST /water-quality/scenario`
- `POST /water-quality/replay/sessions/{session_id}/advance`
- `GET /api/v1/demo/catalog`
- `GET /api/v1/demo/photo`
- `GET /api/v1/bsf-research/treatment-comparison`
- `GET /api/v1/bsf/gallery/datasets`
- `GET /api/v1/bsf/gallery/datasets/{dataset_id}/metrics`
- `GET /api/v1/bsf/gallery/images`
- `GET /api/v1/bsf/gallery/images/{image_id}`
- `GET /api/v1/bsf/gallery/images/{image_id}/content`
- `POST /api/v1/bsf/gallery/images/{image_id}/analyze`
- `GET /api/v1/bsf/gallery/images/{image_id}/results`
- `GET /api/v1/bsf/gallery/jobs`
- `POST /api/v1/bsf/gallery/jobs`
- `GET /api/v1/bsf/gallery/jobs/{job_id}`
- `POST /api/v1/bsf/gallery/jobs/{job_id}/resume`

UI/PWA: /,/ecosystem,/bsf-intelligence#gallery,/manifest.webmanifest,/sw.js,/fiscycle-icon.svg dan aset yang diizinkan. Alias lama tetap tersedia untuk compatibility.

## Startup dan integrasi

Source: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` dari root repository.

Handover: ekstrak main ZIP,salin data ZIP ke FISCYCLE_DEV_HANDOVER/service/FISCYCLE_GALLERY_DATA.zip(biarkan terkompresi),lalu:

```powershell
cd FISCYCLE_DEV_HANDOVER
python verify_checksums.py
cd service
python verify_package.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Alternatif mounting: set FISCYCLE_BSF_GALLERY_DATA ke approved ZIP path. Tanpa data ZIP, runtime_available0 pada dua test collections dan original retrieval503; metadata/thumbnail/baseline tetap tersedia. Dengan bundle:46+178 original tersedia sesudah relokasi. Semua model dan kedua replay tetap bisa berjalan dari main package.

Buka http://127.0.0.1:8000/bsf-intelligence#gallery. Pakai single uvicorn worker untuk job SQLite lokal; konfigurasikan gateway/CORS/persistent volumes sesuai deployment guide. Integrator dapat mengganti router/presentation tanpa mengubah model/preprocessing. Hasil final test sudah released/not blind; dilarang tuning berdasarkan gallery outcomes. Fresh install/Docker belum diverifikasi; pengujian memakai existing CPU environment.

## Addendum integrasi frontend produk dan hosting

Panduan terbaru ada pada FISCYCLE_TEAM_INTEGRATION_GUIDE.md dan disertakan di handover sebagai docs/PRODUCT_MVP_INTEGRATION_GUIDE.md. UI internal dapat diganti oleh UI tim. Jalur yang disarankan: frontend -> backend produk dengan login/permission -> AI service privat yang di-host pada server. Tim boleh menamai endpoint publik sendiri melalui adapter; jangan mengubah model/preprocessing untuk menyesuaikan UI. Mapping request foto(raw bytes),enam fitur B1,Water historical-only,auth gateway,persistent storage dan tanggung jawab staging dijelaskan di sana.

Referensi API2.0.0 yang sudah usang pada endpoint guide diperbaiki agar mengikuti OpenAPI/manifest2.1.0. Perubahan ini hanya dokumentasi/builder:62 staging runtime checks kembali lulus,337 checksum pada ekstraksi ZIP baru cocok,dan316 file non-dokumen identik terhadap release runtime mandiri sebelumnya. Tidak mengklaim pengujian ulang runtime eksternal pada refresh dokumen ini. Tidak ada deployment server tim,fresh-install Linux/Docker,integrasi login produk atau frontend eksternal yang sudah dilakukan. Data Water lokal tetap memerlukan izin sebelum publikasi/hosting eksternal.

