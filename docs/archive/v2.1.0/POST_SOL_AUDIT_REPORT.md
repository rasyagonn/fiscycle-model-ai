# Audit pasca implementasi Smart BSF Intelligence

Tanggal audit: 6 November 2026 (WIB). Root nyata: `D:\project\Fyscycle\fiscycle-model-ai`. Sumber aplikasi tunggal: `app/`. Folder `.agents/skills/fiscycle-bsf-ai/` tetap untuk riset dan artefak beku; `FISCYCLE_DEV_HANDOVER/` adalah hasil generator.

## Kondisi awal dan perbaikan

| Subsistem | Kondisi awal | Akar masalah / risiko | Perbaikan dalam audit | Status akhir |
|---|---|---|---|---|
| FastAPI gabungan | Berjalan; Water Quality dan BSF ada dalam satu `app/main.py` | Ekspor BSF saja gagal karena impor Water Quality wajib | Impor Water Quality bersyarat; rute Water Quality tetap hidup di workspace lengkap | WORKING AND VERIFIED |
| Replay Water Quality | Endpoint hidup tetapi UI memakai ID kolam tetap dan kesiapan global | Kolam bisa diberi label salah; masalah BSF dapat membuat Water tampak gagal; sesi lama menumpuk; grafik mengubah null menjadi nol | Periode membawa pond_id sumber, server memfilter dan menolak kolam lain, UI memeriksa kesiapan Water saja dan mengganti sesi, null tidak diplot sebagai nol | WORKING AND VERIFIED pada data lokal satu pond |
| Frontend Smart BSF | Lima layar di `app/static/bsf.html` dan navigasi Fiscycle | Prefix API tertanam di JavaScript; tautan Water Quality pada paket tanpa domain tersebut | Prefix disuntik dari konfigurasi; tautan Water Quality disembunyikan hanya dalam paket BSF standalone | WORKING AND VERIFIED |
| A1 YOLO11n-seg | Checkpoint nyata dan API segmentasi sudah ada | Runtime mengimpor helper dari riset; ekspor tidak mandiri | `app/services/bsf_models.py` memuat checkpoint dan mengembalikan poligon, skor, dimensi asli, overlay | WORKING AND VERIFIED pada fixture train |
| A2 v3 MobileNetV3 Small | Endpoint ROI manual dan checkpoint nyata sudah ada | Runtime mengimpor `a2_scale_v3.py` dan `train_model_a.py` dari riset | Arsitektur, head, canvas 2048, tensor 224, normalisasi, dan konversi mg dipindah ke core aplikasi; hash checkpoint dan config diperiksa | WORKING AND VERIFIED pada fixture train |
| B1 frozen | Predictor/joblib nyata di folder domain | Bundle dan metadata harus ikut distribusi | Empat file runtime B1 dimasukkan tanpa mengubah model; hasil golden sama | WORKING AND VERIFIED pada fixture dev |
| Replay historis | Dibaca langsung dari CSV OOF riset | Paket tidak membawa data replay dan dapat kehilangan provenance | Seed CSV berversi berisi 288 baris/16 replika pengembangan; ID eksperimen kurasi, perlakuan, replika, trajektori; checksum, metadata, indeks, kamus data; replika final-test dikecualikan | WORKING AND VERIFIED, **IN_SAMPLE_DEVELOPMENT_REPLAY** |
| DSS | 32 faktor, 7 aturan permintaan observasi | Katalog faktor tidak meliputi beberapa kandidat dan abstention operasional kurang eksplisit; foto terakhir dan riwayat batch dapat tertaut tanpa verifikasi | 40 faktor dengan kategori/status, metadata prasyarat/hasil/batas aturan, status `ABSTAIN_OPERATIONAL`; foto hanya ditautkan ke batch lewat pilihan eksplisit; pergantian batch mengosongkan daftar lokal dan input baru memuat ulang riwayat batch dari DB | WORKING AND VERIFIED sebagai aturan observasi; **belum** disahkan ahli untuk intervensi |
| Riwayat | SQLite berfungsi | Skema tanpa nomor versi | `PRAGMA user_version=1` dan penolakan versi tak dikenal; persistensi lintas pembukaan diuji | WORKING AND VERIFIED untuk demo satu pengguna |
| Konfigurasi | Path riset lokal terikat repo | Paket mandiri tidak dapat menemukan model | Deteksi `bsf_assets` relatif paket, env untuk root/replay/DB/prefix/device | WORKING AND VERIFIED |
| Distribusi | Tidak ada builder mandiri | Salinan manual mudah membawa dataset, cache, atau file pribadi | Builder whitelist, staging bersih, smoke test nyata, checksum SHA-256, manifest, dokumentasi | WORKING AND VERIFIED |
| Dependensi | `numpy==2.5.4` sementara OpenCV lokal meminta `<2.3` | `pip check` gagal pada lingkungan saat ini | Persyaratan sumber diperbaiki menjadi `numpy>=2.1,<2.3` | PARTIAL: instalasi bersih belum diuji |
| Keamanan multi-pengguna | Tidak ada login atau pembatasan tenant | Semua riwayat SQLite dapat dibaca oleh pemakai API | Startup dengan `FISCYCLE_RUNTIME_ENV=production` ditolak secara eksplisit | EXTERNALLY BLOCKED sampai autentikasi, otorisasi tenant, dan tinjauan privasi tersedia |
| Docker | Tidak ada verifikasi deploy | Perintah `docker` tidak tersedia di mesin audit | Dockerfile dan panduan disertakan | IMPLEMENTED BUT UNVERIFIED |
| Git | `git status` gagal: bukan repository | Revisi sumber dan tracking tidak dapat dicatat | `.gitignore` untuk distribusi, data mentah, runtime, dan biner besar; manifest menulis `source_revision=null`; panduan release/rollback dibuat | EXTERNALLY BLOCKED sampai workspace berada dalam alur Git yang disetujui |

Tidak ditemukan laporan Sol yang terpisah di root melalui inventaris berkas yang tersedia. Audit ini menggunakan implementasi aplikasi dan artefak riset aktual, bukan klaim dokumentasi lama.

## Batas ilmiah yang dipertahankan

- A1 menghitung **larva yang terlihat dan terdeteksi**. Larva tertutup/bertumpuk dan anotasi adegan padat belum terjamin. Makna biologis ID kelas sumber 0/1 belum dikonfirmasi.
- A2 v3 mensyaratkan foto sumber 4056×3040 yang kompatibel dan ROI satu larva utuh yang diperiksa pengguna. Kesetaraan skala kamera baru dan protokol berat basah/kering belum terverifikasi. Hasil validasi pengembangan sekitar MAE 17,29 mg, RMSE 22,56 mg, bias −3,42 mg, R² 0,820 bukan jaminan lapangan.
- B1 memerlukan berat terukur historis dan perlakuan kelembapan yang didukung. Prediksi A2 tidak diam-diam menjadi input berat terukur B1. Trajektori replay berasal dari data pengembangan yang tumpang tindih dengan pelatihan model akhir, sehingga selisih replay **bukan** estimasi generalisasi independen.
- Aturan DSS hanya meminta pengukuran, pemeriksaan foto, atau tinjauan manusia. Tidak ada ambang intervensi biologis, pengendalian alat, atau klaim validasi A1→A2→B1.

## Hak data dan preservasi

Paket membawa dua gambar **train** untuk smoke test dari [dataset Geissmann Zenodo v1](https://zenodo.org/records/13359376), DOI 10.5281/zenodo.13359376; catatan audit lokal mencatat CC BY 4.0. Seed replay dari [Mendeley Data v1](https://data.mendeley.com/datasets/k435zc736t/1), DOI 10.17632/k435zc736t.1, CC BY 4.0. Tidak ada dataset train lengkap, kelompok final-test, checkpoint yang diubah, catatan pengguna, database SQLite, atau cache Python dalam paket akhir. Dataset lokal Water Quality dan seluruh file riset dibiarkan di tempatnya.

## Berkas sumber yang berubah

Diubah: `app/core/config.py`, `app/main.py`, `app/routers/health.py`, `app/routers/bsf_intelligence.py`, `app/services/bsf_intelligence.py`, `app/services/bsf_decisions.py`, `app/services/water_quality.py`, `app/schemas/water_quality.py`, `app/static/bsf.html`, `app/static/dashboard.html`, `app/requirements.txt`, `app/README.md`, `app/tests/test_api.py`. Baru: `app/services/bsf_models.py`, `app/build_handover.py`, `app/handover_verify.py`, `app/handover_checksums.py`, `app/tests/browser_smoke.py`, `.gitignore`. Di root: tiga laporan audit/manifest, `FISCYCLE_DEV_HANDOVER/`, dan `FISCYCLE_DEV_HANDOVER.zip` yang digenerasi. Rincian checksum ada di manifest paket.

**Keputusan:** GO untuk demo riset lokal satu pengguna dan serah-terima integrasi API. NO-GO untuk produksi multi-tenant, rekomendasi budidaya otomatis, dan klaim validasi lapangan.
