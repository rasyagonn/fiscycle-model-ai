# Audit integrasi Fiscycle — master prompt revisi UNS 2026

## Addendum terbaru — galeri test lengkap dan pelepasan final-test

Enhancement galeri telah ditambahkan pada API2.1.0 dan shell BSF yang sama. Atas instruksi pengguna **“lakukan evaluasi final, lalu lepaskan”**, seluruh46 A1 dan178 A2 test dicoba dan dilepaskan. Semua masih discoverable; kedua set tidak lagi blind. Checkpoint, image, annotation dan membership beku tetap sama; tidak ada tuning berdasarkan test. Pernyataan historis di bawah tentang belum memakai final test menggambarkan scope pekerjaan sebelum addendum ini.

Hasil A1:30 pipeline lengkap,15 sebagian,1 foto dengan0 deteksi,0 technical failure. Hasil A2:130 prediksi,48 ditahan SHORTCUT_SCREEN,0 technical failure. Cakupan A2 73,03%,MAE deskriptif19,14mg pada130 proposal ROI otomatis. **Metrik reviewed-ROI final belum tersedia,n=0**; A1 segmentation accuracy juga tidak dihitung karena label completeness belum disahkan. Full report dan keterbatasan: BSF_GALLERY_REPORT.md.

Main handover sekarang membawa registry/referensi/hasil akhir/seluruh226 thumbnail dan dua fixture development. Semua224 test original+46 annotation source berada pada **FISCYCLE_GALLERY_DATA.zip** yang terpisah; tidak ada test image yang dihilangkan dari distribusi gabungan. Full-resolution portable gallery memerlukan bundle tersebut dipasang di service/ atau melalui server-controlled env. Source app tetap di app/,hasil ilmiah versi baru di folder domain model_a_gallery_v1. Bukti final:38 regresi lulus,2 cek tambahan lulus,Chrome grid/detail tiga viewport lulus,62 checks mandiri dan336 checksum lulus setelah ekstraksi bersama data bundle. Tidak ada klaim clean-install/Docker/CUDA atau field validation.

Tanggal: 6 November 2026 (WIB). Acuan utama: `FISCYCLE_UNS_2026_FINAL_MASTER_PROMPT_REVISED.md` yang ditunjuk pengguna. Laporan ini menggantikan status cakupan BSF-only pada audit sebelumnya; sejarah eksperimen tidak diubah.

## Temuan dan perbaikan aktual

| Area | Sebelum | Implementasi sekarang |
|---|---|---|
| Handover | BSF saja; Water tidak dapat dijalankan dari paket | Builder menyertakan Water A/B/C, 7 estimator dan 2 persistence, seluruh BSF A1/A2 v3/B1, serta dua seed replay |
| Satu foto | A1 dan A2 harus dijalankan terpisah | `/api/v1/bsf/analyze-photo` menjalankan A1, ROI piksel sumber, A2 v3 eksperimental per area layak, agregasi dan DSS khusus foto |
| Water replay | Tabel pasangan tanpa baseline yang setara | MAE/RMSE/bias/cakupan dan persistence pada pasangan waktu yang sama; target tertunda tidak dihitung sebagai kegagalan |
| Water DSS | Enam aturan ada, trace kurang lengkap | Registry versi, QA per parameter, umur data, faktor/nilai/satuan/horizon, jejak aturan dan abstention biologis |
| History | SQLite BSF tanpa tenant | Riwayat Water dan BSF persisten, migrasi v2, filter tenant pada ID/list/batch; sesi replay juga terikat tenant |
| Keamanan | Hanya memeriksa Content-Length | Batas stream aktual, gateway bearer dipetakan server ke tenant, loopback-only jika tanpa gateway, CORS eksplisit, request ID tanpa log body/token |
| Readiness | File A1/A2 ada tetapi lazy-load | Checkpoint dimuat saat inisialisasi dan hash runtime diverifikasi; domain gagal secara terpisah |
| Dashboard | Dua halaman domain dalam satu server | Halaman lama dipertahankan; konteks ekosistem dan empat demo ditambahkan pada navigasi/PWA yang sama |

`app/` adalah sumber aplikasi yang diedit. `FISCYCLE_DEV_HANDOVER/` adalah hasil build, bukan sumber alternatif. Tidak ada `.git` pada workspace ini; source revision dilaporkan `null`, bukan commit rekaan. Pencarian direktori proyek yang relevan di `D:/project/Fyscycle` tidak menemukan frontend tim lain dengan `package.json`/Vite. Integrasi yang diuji adalah UI referensi Fiscycle yang memang tersedia di `app/static`, bukan frontend eksternal yang tidak dapat diakses.

## Inventaris model yang digunakan

| Model | Artefak/metode | Status |
|---|---|---|
| Water A | QA kausal di `app/services/water_core.py` | Aturan engineering; Isolation Forest tetap nonaktif/riset |
| Water B pH | HGB 30m, XGBoost 60m, HGB 120m | Fitted frozen; replay historis |
| Water B suhu | Persistence 30m, HGB 60m, LightGBM 120m | Baseline diberi label terpisah |
| Water B kekeruhan | HGB 30m/60m, Persistence 120m | Tidak ada model DO/TAN |
| Water C | Enam aturan C01–C06 yang memang ada pada kode sebelumnya | Verifikasi/permintaan data, bukan kendali biologis |
| BSF A1 | `hasil/model_a_training_v1/a1_initial/weights/best.pt` | Instance terlihat, kelas target agnostik; makna biologis ID 0/1 sumber tetap belum pasti |
| BSF A2 | `hasil/model_a2_training_v3/best.pt` + config + COMPLETE | MobileNetV3 Small; exact native-pixel canvas v3; eksperimen domain foto |
| BSF B1 | `models/bsf_model_b1_estimator.joblib` + metadata + uncertainty | HistGradientBoosting, enam fitur, berat basah rata-rata per individu |

Hash lengkap ada di `app/runtime_artifacts.json`, manifest rilis, dan checksums paket. Water inference dipindahkan secara portabel ke aplikasi tanpa mengubah fitur/prediksi model; parity numerik diuji terhadap modul riset asli. A2 API diuji terhadap implementasi v3 asli pada foto development kompatibel. Tidak ada retraining, tuning final test, atau perubahan data penelitian yang dibekukan. Tes legacy yang sebelumnya memakai contoh holdout B1 diganti contoh sintetis berlabel untuk regresi kontrak; ini tidak membuat holdout yang dahulu diperiksa kembali menjadi untouched.

## Integritas data dan keputusan

Water seed berisi 299 rekaman lokal asli, termasuk konteks awal, dengan source row ID, satu grup kolam yang identitasnya tidak diketahui, WIB, satuan dan flag missingness. Pemilihan dimulai setelah akhir kalibrasi, tetapi semua data lokal pernah diperiksa: evaluasi tetap retrospektif, bukan holdout baru. NTU dikonfirmasi product owner; kalibrasi/perangkat belum diverifikasi. Identifier kolam bukan bukti sensor tersambung. Seed lokal hanya untuk handover developer yang diminta pengguna, tanpa izin publikasi umum.

BSF seed berisi 288 baris development/16 trajektori, 19 observasi per trajektori setelah observasi awal dipulihkan dari previous_weight. Empat replikasi akhir bersufiks `-5` dikecualikan. Bobot mendatang tidak menjadi fitur. Horizon B1 replay ditetapkan satu hari; waktu pengukuran penelitian tidak selalu tepat satu hari sehingga selisih yang tidak selaras tetap null. B1 tidak menggunakan berat foto A2.

Pada alur foto, ROI harus positif, finite, berada di sumber, dan muat pada kanvas 2048. Box yang menyentuh tepi ditolak. Irisan box / area box terkecil >0,5 menandai keduanya untuk ditolak; ini heuristik geometris engineering, bukan batas biologis atau hasil kalibrasi ilmiah. Maksimum 64 ROI dianalisis per request. EXIF ditangani pada gambar asli, dengan pemetaan koordinat kembali ke sumber. Piksel ROI tidak diperbesar sebelum kanvas v3. Penanda tertulis/occlusion tidak dapat dipastikan otomatis. Kamera/skala belum terverifikasi tetap dapat menghasilkan angka **EXPERIMENTAL**, sesuai master prompt terbaru.

Water scenario membandingkan QA/DSS referensi dengan asumsi stale atau timestamp salah. Output `SIMULATED_RULE_ONLY`; tidak menghitung ulang ML atau menyebutnya efek perlakuan. C05 tidak aktif tanpa ambang, reviewer, dan sumber yang disahkan. Seluruh DSS menahan keputusan operasional otomatis.

## Keterbatasan tersisa

Input pada `POST /water-quality/analyze` adalah klaim historis klien, sehingga diberi `CALLER_DECLARED_HISTORICAL_UNVERIFIED`; angka yang dikirim klien tidak otomatis dianggap rekaman sensor terverifikasi. Replay yang dibaca server dari seed lokal tetap mempunyai provenance historis yang terpisah. Rekomendasi Water kini juga mencatat kewajiban verifikasi manusia dan bukti operasional yang belum tersedia.

- Belum ada autentikasi akun produk, rotasi token, TLS/rate limiting produksi atau integrasi farm operasional; gateway boundary dan isolasi tenant diuji sebagai kontrak backend.
- A1 validation memiliki satu primary split group; final test A2 juga satu primary split group. Jumlah gambar bukan jumlah sampel biologis independen.
- A2 Weight belum dipastikan basah/kering; skala foto multi-larva dan agregasi massa terlihat belum tervalidasi lapangan. Tidak boleh disebut biomassa populasi atau input B1 terukur.
- Replay B1 bersifat in-sample development; Water retrospektif satu kolam. Tidak ada klaim peningkatan generalisasi dari hasil demo.
- Runtime CPU yang ada diuji. Docker dan instalasi dependensi baru dari nol belum diverifikasi. Lingkungan global mempunyai konflik paket `opencv-contrib-python 4.12` terhadap NumPy 2.5; paket yang dikunci menggunakan `opencv-python 4.13`, tanpa contrib, dan tidak mengubah environment riset.
- Pengumpulan limbah, konversi pakan operasional, rewards/Circular Points, logistik, pasar, dan pengukuran dampak tetap rencana.

Hasil pengujian dan status rilis final terdapat di `FISCYCLE_MVP_VERIFICATION_REPORT.md` dan `app/release_evidence.json`.
