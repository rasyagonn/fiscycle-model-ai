# Fiscycle Integrated AI — aplikasi sumber

Sumber aplikasi: `app/`. Model dan data penelitian tetap di `.agents/skills/`. `FISCYCLE_DEV_HANDOVER/` adalah hasil build yang menyertakan seluruh model runtime Water/BSF dan **kedua** seed replay.

## Jalankan

Dari root repository, dengan environment Python yang kompatibel:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Buka http://127.0.0.1:8000/ecosystem untuk empat demo; `/` untuk kontrol Water, `/bsf-intelligence` untuk BSF, dan `/docs` untuk API lengkap. Navigasi/PWA tetap satu aplikasi. Untuk instalasi baru gunakan venv terpisah dan `python -m pip install -r app/requirements.txt`; jangan menimpa environment riset. Lock merekam CPU. Instalasi dari nol dan Docker belum diverifikasi.

## Alur dan endpoint

| Alur | Endpoint utama | Makna |
|---|---|---|
| A: satu foto | POST /api/v1/bsf/analyze-photo | A1 → ROI piksel asli → A2 v3 eksperimental → distribusi/massa terlihat → DSS foto |
| B: pertumbuhan | GET /api/v1/bsf/replay/trajectories, /replay/{id}?revealed=N; POST /decision-support | B1 dari riwayat terukur penelitian, bukan berat foto |
| C: Water | GET /water-quality/replay/periods; POST /replay/sessions; POST /replay/sessions/{id}/advance | QA, 9 parameter/horizon, pasangan aktual dan persistence yang sama |
| D: keputusan | POST /water-quality/replay/sessions/{id}/snapshot; POST /water-quality/scenario | Asumsi stale/error; SIMULATED_RULE_ONLY, bukan efek perlakuan |
| Riwayat | /water-quality/history dan /api/v1/bsf/history | Hasil, versi, sumber dan waktu WIB persisten |
| Registry | /water-quality/models, /water-quality/rules; /api/v1/bsf/models, /factors, /rules | Kontrak model dan aturan sebenarnya |

URL pada kolom kedua yang disingkat mengikuti prefix domain pada barisnya; lihat OpenAPI untuk kontrak lengkap. Endpoint A1 `/segment` dan single-ROI A2 `/estimate-weight` tetap tersedia. Single-ROI A2 tetap memerlukan foto kompatibel 4056×3040 yang diperiksa pengguna. Batch foto mengizinkan ROI teknis layak dari domain belum terverifikasi dengan label eksperimental. Massa terlihat bukan biomassa populasi atau input B1.

## Penyimpanan dan keamanan

SQLite BSF menggunakan `FISCYCLE_BSF_HISTORY_DB`; Water memakai `water_history.sqlite3` di direktori yang sama. Hasil/versi/provenance/hash disimpan tanpa gambar atau base64. Migrasi v2 menempatkan rekaman lama pada tenant local_demo. Sesi replay Water di memori; snapshot tersimpan permanen.

Tanpa gateway, hanya loopback diterima. Backend induk dapat menyediakan `FISCYCLE_GATEWAY_TOKENS` JSON secret→tenant dan CORS eksplisit melalui `FISCYCLE_CORS_ORIGINS`. Tenant bukan field farm yang dapat dipilih bebas. Login produk, TLS, rotasi key dan rate limiting publik tetap bagian deployment induk. Prefix BSF bisa diubah melalui `FISCYCLE_BSF_API_PREFIX` tanpa mengubah model.

## Build dan verifikasi

```powershell
python -m pytest app/tests -q -p no:cacheprovider
python app/tests/browser_smoke.py
python -m app.build_handover
python -m app.verify_release
```

Browser smoke memakai Chrome/Selenium lokal. Verifier release membangun dua kali, membandingkan payload stabil, membuat ZIP, mengekstrak di luar repository lalu menjalankan semua model/replay. Timestamp dan manifest terkait dikecualikan dari perbandingan byte. Jika ACL menolak penyimpanan bukti JSON, hasil dicetak di stdout.

Paket sekarang mencakup Water dan BSF; seed lokal hanya untuk handover developer yang diotorisasi, bukan publikasi umum. Tidak ada retraining. Model BSF tetap RESEARCH_PROTOTYPE / NOT_FIELD_VALIDATED, Water historis bukan IoT live, A2 wet/dry dan skala kamera belum pasti, serta tidak ada ambang biologis DSS yang disahkan. Lihat laporan tingkat root untuk hasil dan batas aktual.

## Galeri lengkap pasca-evaluasi final

Buka http://127.0.0.1:8000/bsf-intelligence#gallery. Tersedia seluruh **46 test A1** dan **178 test A2**, dengan dua fixture development berlabel terpisah. Final-test telah dievaluasi dan dilepaskan atas instruksi pengguna; set tersebut tidak lagi blind. Tidak ada tuning atau training berdasarkan hasil ini.

Galeri mendukung thumbnail, pencarian, pagination, preview resolusi asli, navigasi foto, A1→A2 eksperimental, standalone A2 v3, status penolakan/kegagalan, DSS, history dan **Analisis Semua Foto** melalui satu worker dengan progres persisten. Cache diberi label; centang **Hitung ulang** untuk inferensi baru. Job terhenti dapat dilanjutkan dan item gagal dapat dicoba ulang.

Registry/protokol/evaluasi: `.agents/skills/fiscycle-bsf-ai/hasil/model_a_gallery_v1/`. A1 mempunyai 2 primary test group; A2 hanya 1. Kelengkapan anotasi A1 belum disahkan, sehingga akurasi segmentasi tidak dilaporkan. A2 otomatis menghasilkan prediksi pada 130/178 foto; 48 ROI ditolak dengan kebijakan tetap. MAE deskriptif 19,14 mg pada subset otomatis ini bukan benchmark reviewed-ROI atau validasi lapangan.

Untuk paket di luar repository, salin `FISCYCLE_GALLERY_DATA.zip` ke `FISCYCLE_DEV_HANDOVER/service/` dan **biarkan ZIP data tetap terkompresi**. Alternatif: set `FISCYCLE_BSF_GALLERY_DATA` ke path bundle server yang disetujui. Bundle 766.100.663 bytes membawa semua 224 test original dan 46 anotasi A1 asli, CC BY 4.0. Main ZIP membawa registry, referensi, hasil evaluasi, semua thumbnail dan fixture development; full-resolution test memerlukan bundle data. Tanpa bundle, API menyatakan runtime_available=0 untuk kedua koleksi test.

API galeri: /api/v1/bsf/gallery/datasets, /images, /images/{id}, /images/{id}/content, /images/{id}/analyze, /images/{id}/results, /datasets/{id}/metrics, /jobs, /jobs/{id}, /jobs/{id}/resume. Lihat OpenAPI untuk metode/schema. Klien hanya memakai ID foto, tidak mengirim path filesystem. Gunakan satu worker uvicorn untuk antrean SQLite lokal ini. Detail ada pada BSF_GALLERY_REPORT.md dan docs/GALLERY_DEPLOYMENT.md di handover.

