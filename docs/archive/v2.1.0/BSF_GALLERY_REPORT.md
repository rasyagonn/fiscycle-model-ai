# Galeri Pengujian AI BSF — laporan final

Tanggal 6 November 2026 (WIB). Scope: enhancement MVP yang sudah ada, berdasarkan lampiran `SMART BSF COMPLETE TEST IMAGE GALLERY & BATCH INFERENCE IMPROVEMENT`. Pengguna secara eksplisit menginstruksikan: **“lakukan evaluasi final, lalu lepaskan”**. Evaluasi final telah selesai sebelum kedua koleksi dilepaskan.

## Dataset dan kelengkapan

| Koleksi | Manifest menyatakan | Ditemukan dan terbaca | Hilang / rusak / restricted | Referensi | Primary split group |
|---|---:|---:|---:|---|---:|
| A1 test, BSF_Larvae_v1 | 46 | 46 | 0 / 0 / 0 | 46 file anotasi tersedia; kelengkapan belum disahkan | 2 |
| A2 test, Single Larvae | 178 | 178 | 0 / 0 / 0 | 178 Weight individual, g dikonversi ke mg | 1 (B011) |
| Development A1 — Bukan Test | 1 fixture yang sudah ada | 1 | 0 / 0 / 0 | Tidak digunakan sebagai test | Train |
| Development A2 — Bukan Test | 1 fixture yang sudah ada | 1 | 0 / 0 / 0 | Geometry v3 development yang sudah ada | Train |

Seluruh **224** anggota test pada manifest beku dicatat, ditampilkan dan dicoba. Tidak ada pemilihan subset berdasarkan kualitas hasil. Dua fixture development tetap terpisah dan bukan pengganti test. Validation, quarantine, excluded dan seluruh training set tidak dilabel ulang sebagai test.

Bukti membership: `.agents/skills/fiscycle-bsf-ai/hasil/model_a_preparation_v1/FREEZE.json`, `a1_manifest.csv` dan `a2_manifest.csv`. Checksum keduanya diverifikasi sebelum inventaris dibuat. Setiap test image dibaca, di-decode dan dicocokkan SHA-256 serta dimensinya terhadap manifest asli.

A1 original: `.agents/skills/fiscycle-bsf-ai/data/BSF_Larvae_v1/Images/`, anotasi asli pada `Labels/`. A2 original: `.agents/skills/fiscycle-bsf-ai/data/Single Larvae data.zip`; setiap original sample ID, archive member, ukuran, hash, grup, kamera/EXIF yang tersedia dan referensi Weight dicatat dalam registry lengkap.

Sumber publik: Quentin Geissmann, *Black Soldier Fly detection, phenotyping and sex prediction dataset*, Zenodo v1, DOI 10.5281/zenodo.13359376. Status CC BY 4.0 berdasarkan bukti audit provenance yang sudah ada; atribusi dibawa dalam distribusi. Metadata kamera A2 tersedia pada record masing-masing; timezone kamera yang belum diketahui tetap UNKNOWN. Weight basah/kering belum dikonfirmasi.

## Evaluasi aktual, tanpa tuning

Konfigurasi dipra-registrasikan pada `evaluation_protocol.json`. Checkpoint A1 dan A2 v3 tidak diganti. A1 tetap imgsz320, confidence0,25 dan max_det300. Orkestrasi tetap maksimum64 ROI, threshold overlap0,5 terhadap area box terkecil, dan penahanan ROI menyentuh tepi. Tidak ada threshold yang dipilih berdasarkan hasil test.

A2 menggunakan **algoritme ranked ROI v2 yang sudah ada**, dengan parameter yang sama, kemudian exact v3: ROI pada piksel asli → kanvas2048 dengan padding127 → bilinear224 → normalisasi ImageNet → inverse target mean/std checkpoint. Proposal tidak menerima Weight, ID, batch, sex atau tanggal sebagai predictor. Parity proposal terhadap algoritme lama diuji pada development.

| Koleksi | Dicoba | Berhasil | Sebagian | Ditolak / tanpa estimasi layak | Gagal teknis | Pending |
|---|---:|---:|---:|---:|---:|---:|
| A1 test → A1/A2 eksperimental | 46 | 30 | 15 | 1 | 0 | 0 |
| A2 test → standalone A2 v3 | 178 | 130 | 0 | 48 | 0 | 0 |

“Berhasil” merupakan status eksekusi/kelengkapan pipeline, **bukan akurasi terhadap ground truth**.

Foto A1 `A1_aa77a94b3495ef69` menghasilkan **nol deteksi**. Estimasi massa, rata-rata, median dan cakupannya null; kasus ini tetap ada di galeri. Pada A1 yang lain, partial berarti sebagian ROI menghasilkan estimasi dan sebagian ditolak. Tidak dihitung mAP/akurasi segmentasi karena label belum tersertifikasi lengkap dan makna biologis source class0/1 belum terkonfirmasi.

Seluruh48 penolakan A2 beralasan `SHORTCUT_SCREEN`: screen lama menandai kemungkinan garis/ink-like components. Itu flag heuristik, bukan sertifikasi adanya penggaris/tulisan. Tidak ada retuning atau penghapusan gambar untuk menaikkan metrik.

Pada **130 dari178** foto A2 yang lolos gate otomatis:

- Cakupan prediksi: **73,03%**.
- MAE deskriptif: **19,140898 mg/larva**.
- RMSE deskriptif: **23,555634 mg/larva**.
- Bias deskriptif: **+3,057749 mg/larva**.
- ROI final-test yang sudah ditinjau sebelumnya: **0**; metrik benchmark reviewed-ROI tetap **UNAVAILABLE**.

Angka tersebut bersyarat pada gate ROI otomatis dan satu grup B011. Tidak boleh disebut akurasi resmi pada seluruh178 foto, bukti improved generalization, atau validasi lapangan. Per-image reference, prediction, absolute error atau null dan alasan penolakan semuanya dipertahankan.

Waktu rata-rata usaha per foto pada satu run CPU, termasuk decode/QA dan prediksi bila layak: A1 **0.512 detik**, A2 **0.456 detik**. Total usaha tercatat sekitar 23.55 dan 81.10 detik. Ini bukan benchmark inference murni atau janji latency. Kedua job evaluasi awal mempunyai cache_hits=0 dan completed=total.

## Integritas dan status blind

Kedua set kini **RELEASED_NOT_BLIND_AFTER_FINAL_EVALUATION**. Paparan historis A2 ID1102 pada QA lama juga tetap dicatat; tidak mengklaim pristine visual blindness sebelumnya. Tidak ada retraining, perubahan frozen split, perubahan source label/image, pemilihan checkpoint atau optimasi ROI berdasarkan error test. B1 dan Water tidak ikut dibuka ulang sebagai final test.

Hasil awal disimpan secara versioned dan tidak ditimpa oleh demo berikutnya. Review ROI pengguna setelah pelepasan merupakan analisis tambahan dengan cache key tersendiri; tidak menggantikan evaluasi awal. Future model selection tidak boleh memakai galeri ini sebagai blind holdout.

Folder hasil baru:

```text
.agents/skills/fiscycle-bsf-ai/hasil/model_a_gallery_v1/
  manifest.json                seluruh226 record dan locator sumber
  inventory.json               counts dan status pelepasan
  evaluation_protocol.json     pra-registrasi model/config dan hash
  evaluation_started.json      fingerprint runtime sebelum prediksi
  final_evaluation.json         hasil dua job final dan pelepasan
  baseline_results.jsonl        hasil per image asli, termasuk rejected
  final_jobs.sqlite3            progres pekerjaan evaluasi
  final_history.sqlite3         history evaluasi
  bundle_receipt.json           checksum/count bundle data
  thumbnails/                   226 thumbnail asli turunan
```

Fingerprint konfigurasi evaluasi: `6627397db7ec45ce3c0cd53b0fd2d32a62f0f3d720512f246963f075e0058407`. Protocol SHA-256: `359fdda9b8bdd2082e8c542e3a67a95a288b7e4499502605cb1a1bc8a49c1146`. Baseline JSONL SHA-256: `c1805348499182f757f9be4e49ea604d8e37ec763c8136c9c2f06d12e1d23f42`.

## Galeri, API, jobs dan cache

Halaman: **/bsf-intelligence#gallery**, tab **Galeri Foto BSF** pada dashboard BSF yang sama. Selector dataset/split, grid thumbnail, search filename/ID, pagination, preview resolusi penuh, previous/next, original-vs-overlay, metadata kamera, detail instance, distribusi bobot, DSS dan riwayat sudah tersedia. Kasus ditolak dan gagal tetap dapat ditampilkan melalui filter status.

Endpoint prefix default `/api/v1/bsf/gallery`:

- GET `/datasets`, `/images`, `/images/{image_id}`.
- GET `/images/{image_id}/content?variant=original|thumbnail|overlay|processed`.
- POST `/images/{image_id}/analyze`; GET `/images/{image_id}/results`.
- GET `/datasets/{dataset_id}/metrics`.
- POST `/jobs`; GET `/jobs` dan `/jobs/{job_id}`.
- POST `/jobs/{job_id}/resume?retry_failed=true`.

Klien memakai opaque image ID, tidak mengirim path filesystem. Path containment, MIME/size checks, checksum image/bundle dan boundary gateway/tenant diterapkan. Full-size original tidak dipasang sebagai direktori static terbuka.

**Analisis Semua Foto** mencakup seluruh koleksi, bukan halaman yang sedang terlihat. Satu worker memproses bertahap. Job/item/result persisten di `bsf_gallery.sqlite3` dekat history aplikasi; path dapat diatur dengan `FISCYCLE_BSF_GALLERY_DB`. Dead-worker recovery dan explicit resume mempertahankan pekerjaan yang sudah selesai; retry menambah attempts. Status pending/running/complete/failed/rejected dan cache hits ditampilkan.

Cache meliputi hash image, hash checkpoint, preprocessing, ROI ranking/config, source pipeline, device/library versions dan optional ROI review. Cache sesuai dipakai ulang dengan label `cache_hit`; centang Hitung ulang untuk percobaan baru. Hasil failure bisa dicoba kembali. Tidak ada inferensi seluruh test saat halaman dibuka.

## Packaging lengkap

Paket aplikasi: `FISCYCLE_DEV_HANDOVER/` dan `FISCYCLE_DEV_HANDOVER.zip`. Semua model lama, kedua historical seed, registry galeri, referensi, hasil evaluasi, seluruh226 thumbnail, docs dan tes portable dibawa.

Bundle optional **FISCYCLE_GALLERY_DATA.zip** membawa **seluruh224 test original +46 anotasi A1 asli**, tanpa ada test image yang dihilangkan. Ukuran 766,100,663 bytes; SHA-256 `3ed81388e1e3b0f2b63643683e3265cef6d83f40234ee22482671f4d7b133c7b`.

Jumlah original test yang tidak masuk **main ZIP**:224, karena dipisahkan sebagai bundle besar. Jumlah test original yang hilang dari **distribusi gabungan**:0. Main ZIP sendiri hanya menyediakan metadata/thumbnail/baseline dan dua fixture penuh; itu belum full-resolution gallery. Setelah bundle dipasang, runtime tersedia46 A1 +178 A2.

Untuk handover, salin bundle ZIP tetap terkompresi ke `FISCYCLE_DEV_HANDOVER/service/FISCYCLE_GALLERY_DATA.zip`, atau set `FISCYCLE_BSF_GALLERY_DATA` ke path bundle yang disetujui server. Tanpa bundle, API melaporkan runtime_available=0 dan fresh original retrieval mendapat503 yang jelas. Tidak ada ketergantungan ke folder riset setelah app dan data bundle dipindahkan.

## Pengujian dan penggunaan

- Regresi lengkap: **38 passed** (65,19 detik), termasuk Water, B1, DSS, source image gallery, cache, jobs dan restart.
- Dua cek terarah tambahan: cache invalidation ketika checkpoint hash berubah, serta bundle hilang/rusak ditolak.
- Chrome: empat flow lama, gallery pagination/search, originalA2 4056px, cache, 48 rejected tetap terlihat, bulk46 A1, previous/next dan layar390/768/1440 pada grid serta detail: **PASS**.
- Staging dan ekstraksi independen: lihat bukti rilis terbaru pada `app/release_evidence.json` dan `FISCYCLE_MVP_VERIFICATION_REPORT.md`.
- Instalasi environment baru dari nol, Docker dan CUDA deployment **belum diuji**.

Jika server versi lama masih berjalan, hentikan dengan Ctrl+C lalu jalankan ulang:

```powershell
cd D:\project\Fyscycle\fiscycle-model-ai
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Buka http://127.0.0.1:8000/bsf-intelligence#gallery. Pilih A1, buka foto mana saja, lalu Jalankan AI untuk melihat segmentasi/estimasi/DSS. Pilih A2 untuk standalone individual-weight. Gunakan status ROI Ditolak untuk memeriksa seluruh penolakan. Analisis Semua Foto memakai cache yang cocok; centang Hitung ulang bila ingin real inference baru. Sampel development dilabel Bukan Test. Model tetap **RESEARCH_PROTOTYPE / NOT_FIELD_VALIDATED**.

## Catatan perbaikan dan source

Prepare awal berhenti karena nama fixture ekspor A1 berbeda dari filename sumber. Pencocokan diperbaiki berdasarkan hash source dan split manifest **sebelum evaluasi final**. Tidak ada perbaikan model berdasarkan hasil test. Perubahan tampilan setelah evaluasi hanya menampilkan metadata kamera dan membungkus filename panjang pada mobile; hasil evaluasi/model tetap sama.

Source baru: `app/gallery_prepare.py`, `gallery_evaluate.py`, `gallery_bundle.py`, `gallery_docs.py`, `gallery_checks.py`, `routers/bsf_gallery.py`, `services/bsf_gallery.py`, `services/bsf_gallery_roi.py`, `static/gallery.html`, `gallery.js`, `gallery.css`, `tests/test_bsf_gallery.py`, `tests/test_gallery_portable.py`.

Source yang diubah: `app/main.py`, `core/config.py`, `static/bsf.html`, `static/ecosystem.html`, `static/sw.js`, `build_handover.py`, `handover_verify.py`, `verify_release.py`, `tests/browser_smoke.py`, `README.md`, `STRUCTURE.md`. Release/report tingkat root diperbarui; kode utama tetap hanya di `app/`.
