# Verifikasi MVP Fiscycle — Water, Smart BSF dan galeri test lengkap

**READY WITH DOCUMENTED LIMITATIONS**

Tanggal 6 November 2026 (WIB). Release `fiscycle-integrated-research-mvp-2.1.0-gallery`, API `2.1.0`. Runtime Windows/Python3.13.3/PyTorch2.12.0+cpu/OpenCV4.13.0. Tidak ada training ulang atau perubahan frozen model/split/image/label.

## Hasil pengujian aktual

| Gate | Hasil |
|---|---|
| Regresi seluruh aplikasi | **38 passed**,65,19 detik: Water, A1/A2/B1, replay, DSS, history, gallery, cache, jobs dan restart |
| Pemeriksaan tambahan | **2 passed**,16,02 detik: invalidasi cache pada checkpoint hash berbeda, serta bundle hilang/rusak |
| Chrome nyata | **PASS**: empat flow sebelumnya, gallery46/178, pagination, search, A2 original4056px, cache, seluruh48 rejected tetap terlihat, bulk46 A1, next-image, prefix /custom/bsf; grid dan detail390/768/1440 tanpa overflow |
| Evaluasi final sebelum pelepasan | **224/224 dicoba**,pending0,cache_hits0 pada kedua job awal; hasil tetap tersimpan |
| Paket staging dan ekstraksi independen | **62 checks PASS**, actual model/replay/DSS/gallery dengan optional data bundle yang disalin ke service di luar repository |
| Integritas main package | **337 checksum payload cocok**,338 file termasuk CHECKSUMS |
| Dua build final | Release runtime sebelum refresh dokumen:334 file stabil identik pada dua build. Refresh dokumen terbaru tidak mengulang dua build;316 file non-dokumen terbukti identik terhadap ZIP sebelumnya |
| Keutuhan input lama | **42 hash** model/config/freeze/manifest/source replay yang diperiksa tetap sama |
| A2 parity | Transform v3 pixel/tensor golden dan output standalone terhadap research adapter lulus |
| Water parity | Sembilan forecast golden serta output research runtime lulus |
| Isolasi dan persistence | Tenant record/batch/job/sesi dibatasi; body streaming berlebih ditolak; hasil dan job bertahan saat SQLite dibuka kembali |
| Dataset tidak dipasang | Metadata tetap tersedia; availability0 dan original retrieval503 yang jelas |
| Dataset rusak | Bundle SHA mismatch ditolak; image SHA diverifikasi saat dibaca; source frozen membership cocok |

Command regresi: `python -m pytest app/tests -q -p no:cacheprovider`. Command fokus terakhir memilih dua tes cache/bundle. Tes tambahan membuat total39 fungsi tes sumber; tidak mengklaim satu eksekusi39/39. Daftar cek mandiri ada di `FISCYCLE_DEV_HANDOVER/VERIFICATION_REPORT.md`; bukti machine-readable terbaru di `app/release_evidence.json`.

## Hasil evaluasi BSF yang benar-benar dijalankan

Pengguna menginstruksikan **“lakukan evaluasi final, lalu lepaskan”**. Kedua koleksi telah dievaluasi dan dilepaskan; status kini **RELEASED_NOT_BLIND_AFTER_FINAL_EVALUATION**. Parameter ditetapkan sebelum prediksi, tanpa tuning menggunakan hasil.

| Dataset | Declared/readable | Dicoba | Success | Partial | Rejected/tidak ada estimasi | Technical failure |
|---|---:|---:|---:|---:|---:|---:|
| A1 test | 46/46 | 46 | 30 | 15 | 1 | 0 |
| A2 test | 178/178 | 178 | 130 | 0 | 48 | 0 |

Semua224 masih discoverable; missing0,corrupt0,restricted0. A1 source annotation46 tersedia, tetapi completeness belum disahkan: **akurasi segmentasi tidak dihitung**. Satu A1 `A1_aa77a94b3495ef69` menghasilkan0 deteksi dan estimasi massa null; itu tidak disembunyikan. Success adalah status eksekusi, bukan akurasi.

A2 menggunakan proposal ROI ranked v2 yang sudah ada, konfigurasi tetap, diikuti exact native2048→224 A2v3. Seluruh48 ditolak oleh `SHORTCUT_SCREEN` yang menandai kemungkinan garis/ink, bukan pembuktian adanya penanda. Pada130 prediksi otomatis: MAE19,140898mg,RMSE23,555634mg,bias+3,057749mg,cakupan73,03%. **Strict reviewed-ROI final metric belum tersedia,n=0.** Hasil otomatis bersifat deskriptif dan bersyarat pada gate; tidak menyatakan akurasi resmi seluruh178 atau improved generalization.

A1 test mempunyai2 primary group; A2 test hanya1/B011. Jumlah foto bukan sampel biologis independen. Protokol Weight basah/kering A2 dan skala kamera belum tervalidasi. A1→A2 tetap integrasi eksperimen; agregat merupakan massa terlihat yang berhasil dianalisis, bukan biomassa populasi atau input B1.

Rata-rata satu usaha CPU termasuk decode/QA/prediksi bila layak: A1 0.512s/foto; A2 0.456s/foto. Ini bukan benchmark inference murni. Rincian lengkap: `BSF_GALLERY_REPORT.md` dan folder hasil versi baru `.agents/skills/fiscycle-bsf-ai/hasil/model_a_gallery_v1/`.

## Kemampuan yang dipertahankan

Water A/B/C, sembilan kombinasi parameter/horizon(7 ML+2 persistence), kedua historical replay, B1 enam fitur dari mean wet weight terukur, DSS, gateway boundary dan SQLite history tetap berjalan. Water replay adalah retrospektif/WIB; data klien diberi status historical-claim belum terverifikasi. Skenario Water tetap rule-only. B1 replay development tetap in sample; foto A2 tidak dipakai sebagai mean wet-weight B1.

## Paket dan cara menjalankan

Main ZIP: 22,050,394 bytes,SHA-256 `a55015499574b83bb6aea5cf5c9f7caa22019a66170201168cf1daf83e2601a9`.

Optional data ZIP: 766,100,663 bytes,SHA-256 `3ed81388e1e3b0f2b63643683e3265cef6d83f40234ee22482671f4d7b133c7b`. Isinya **seluruh224 test original +46 source annotation A1**. Main ZIP memuat seluruh226 thumbnail, registry/referensi/baseline dan dua fixture development. Main ZIP tanpa data ZIP hanya menyediakan gallery metadata/thumbnail/cache, belum full-resolution fresh test inference.

Source internal:

```powershell
cd D:\project\Fyscycle\fiscycle-model-ai
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Jika server lama masih berjalan, Ctrl+C lalu mulai ulang. Buka http://127.0.0.1:8000/bsf-intelligence#gallery.

Portable: ekstrak FISCYCLE_DEV_HANDOVER.zip, letakkan **FISCYCLE_GALLERY_DATA.zip di dalam service/** tanpa mengekstrak data ZIP(atau set FISCYCLE_BSF_GALLERY_DATA), jalankan `python verify_package.py`, lalu uvicorn yang sama dari service/. API lengkap: /docs. Source app tetap otoritatif; handover adalah output builder.

## Kegagalan/perbaikan dan batas tersisa

Prepare pertama berhenti saat nama fixture ekspor A1 tidak sama dengan filename manifest. Diperbaiki melalui hash sumber sebelum final evaluation; tidak mengubah split/model. Setelah evaluasi, perbaikan tampilan hanya menambah metadata kamera dan wrapping nama berkas pada detail mobile; hasil final tidak dihitung ulang atau ditimpa.

ACL lokal menolak penulisan langsung bukti JSON dari verifier. JSON selalu dicetak; hasil final disimpan melalui mekanisme edit workspace. Deprecation warnings Starlette/httpx dan joblib/NumPy tetap muncul. Lingkungan global juga memiliki metadata opencv-contrib4.12 yang konflik dengan NumPy2.5; binary yang dipakai adalah OpenCV4.13 dan lock menggunakan opencv-python4.13 tanpa contrib. Environment riset tidak ditimpa.

Instalasi baru dari nol, Docker dan CUDA deployment **UNVERIFIED**. Tes ekstraksi memakai dependency CPU yang sudah terpasang. Frontend eksternal tim tidak ditemukan; integrasi UI yang diuji adalah aplikasi Fiscycle yang tersedia pada repository. Deployment publik masih memerlukan backend akun/farm,TLS,key rotation,rate limiting dan review operasional; gateway boundary bukan identity provider.

Tidak ada field validation, biological safety threshold disahkan, dampak circular economy terukur, atau klaim produksi. Model remains RESEARCH_PROTOTYPE / NOT_FIELD_VALIDATED. Seed sensor lokal dalam main handover hanya untuk distribusi developer yang diminta pengguna, bukan izin publikasi umum.

## Addendum integrasi frontend produk dan hosting

Panduan terbaru ada pada FISCYCLE_TEAM_INTEGRATION_GUIDE.md dan disertakan di handover sebagai docs/PRODUCT_MVP_INTEGRATION_GUIDE.md. UI internal dapat diganti oleh UI tim. Jalur yang disarankan: frontend -> backend produk dengan login/permission -> AI service privat yang di-host pada server. Tim boleh menamai endpoint publik sendiri melalui adapter; jangan mengubah model/preprocessing untuk menyesuaikan UI. Mapping request foto(raw bytes),enam fitur B1,Water historical-only,auth gateway,persistent storage dan tanggung jawab staging dijelaskan di sana.

Referensi API2.0.0 yang sudah usang pada endpoint guide diperbaiki agar mengikuti OpenAPI/manifest2.1.0. Perubahan ini hanya dokumentasi/builder:62 staging runtime checks kembali lulus,337 checksum pada ekstraksi ZIP baru cocok,dan316 file non-dokumen identik terhadap release runtime mandiri sebelumnya. Tidak mengklaim pengujian ulang runtime eksternal pada refresh dokumen ini. Tidak ada deployment server tim,fresh-install Linux/Docker,integrasi login produk atau frontend eksternal yang sudah dilakukan. Data Water lokal tetap memerlukan izin sebelum publikasi/hosting eksternal.

