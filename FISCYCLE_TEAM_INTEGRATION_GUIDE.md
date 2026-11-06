# Serah-terima tim developer — MVP Fiscycle online

Kontrak diperiksa terhadap API **2.1.0** pada repository ini. Dokumen ini adalah acuan integrasi produk; dashboard HTML yang disertakan merupakan referensi internal/QA. Tim bebas menggunakan framework, layout dan endpoint publik aplikasi sendiri.

## 1. Yang sudah selesai dan yang belum

Sudah tersedia: service Python/FastAPI yang memuat checkpoint nyata, preprocessing, Water A/B/C, BSF A1/A2 v3/B1, dua historical replay, DSS, history, galeri, jobs/cache, OpenAPI dan paket runtime mandiri. Source aplikasi otoritatif berada di app/. Tidak perlu melatih ulang atau mengonversi model ke bahasa backend produk.

Belum dilakukan: deployment ke server milik tim, fresh dependency installation pada OS server tersebut, domain/HTTPS, integrasi login/permission produk, integrasi frontend produk yang berada di luar repository, dan pengujian staging menyeluruh. Dockerfile tersedia tetapi belum diuji build. Hasil Windows CPU lokal tidak dianggap bukti bahwa semua konfigurasi server pasti berjalan.

MVP dapat di-host online untuk upload foto BSF, input riwayat terukur yang didukung, dan demonstrasi historical replay. Water saat ini secara kontrak hanya menerima mode historical_replay; ingest sensor langsung atau forecast operasional kolam pengguna belum diimplementasikan/divalidasi. Meng-host API tidak mengubah data historis menjadi data live atau mengesahkan validasi lapangan.

## 2. Arsitektur integrasi yang disarankan

```text
Frontend Fiscycle web/PWA/mobile (desain tim)
  -> HTTPS Backend Produk (login, akses user/farm, endpoint publik, database produk)
     -> jaringan privat: FastAPI AI (model, preprocessing, inference, replay, DSS)
        -> persistent volume (history/job SQLite + optional gallery-data ZIP)
```

Backend produk menjadi adapter/proxy. Browser memakai sesi/JWT pengguna yang sudah dimiliki produk. Backend memeriksa akses pengguna dan memilih tenant AI yang diizinkan, lalu mengirim bearer gateway secret server-ke-server. Frontend tidak perlu menampilkan halaman internal /ecosystem atau /bsf-intelligence kepada pengguna produk.

Jangan memasukkan secret gateway AI ke bundle JavaScript/mobile atau mem-forward token tersebut ke browser. Fitur sessionStorage pada dashboard referensi hanya untuk pengujian internal. Service AI saat ini memakai mapping secret->tenant, bukan validator JWT pengguna produk; jangan meneruskan JWT login ke AI dan menganggapnya otomatis dikenali.

## 3. UI dan endpoint publik boleh berbeda

Contoh mapping berikut adalah **rancangan adapter backend tim**, bukan route baru yang sudah diimplementasikan:

| Aksi UI | Contoh endpoint publik tim | Route AI yang sudah tersedia |
|---|---|---|
| Upload foto banyak larva | POST /api/bsf/analyze | POST /api/v1/bsf/analyze-photo |
| Tampilkan pertumbuhan | GET /api/bsf/growth/... | GET /api/v1/bsf/replay/{trajectory_id}?revealed=N |
| Forecast dari berat terukur | POST /api/bsf/forecast | POST /api/v1/bsf/forecast |
| Dukungan keputusan BSF | POST /api/bsf/decision | POST /api/v1/bsf/decision-support |
| Replay Water | /api/water/replay/... | /water-quality/replay/periods dan /replay/sessions/... |
| Analisis riwayat Water | POST /api/water/analyze | POST /water-quality/analyze |
| Galeri riset/test | /api/research/bsf/... | /api/v1/bsf/gallery/... |

Tim boleh mengubah nama URL atau bentuk view model pada backend adapter. Pertahankan arti measured/predicted, satuan, horizon, provenance, null, rejection/failure, cakupan dan keterbatasan. Nilai null tidak boleh dijadikan0. Hindari perubahan pada services/bsf_models.py, frozen weights, canvas A2 atau feature order hanya untuk menyesuaikan UI.

Jika route langsung FastAPI harus diubah, edit app/routers/ atau tambahkan alias berversi. Prefix BSF dapat dikonfigurasi lewat FISCYCLE_BSF_API_PREFIX; custom prefix sudah diuji. Jangan menghapus route lama tanpa migrasi consumer. Versi kontrak aktual ada di openapi.json dan HANDOVER_MANIFEST.json.

## 4. Kontrak upload foto yang perlu diperhatikan

Frontend boleh mengirim multipart/form-data ke backend produk. Backend kemudian mengambil byte file asli dan memanggil AI seperti berikut:

```http
POST /api/v1/bsf/analyze-photo
Authorization: Bearer <secret-gateway-tenant-yang-diverifikasi-backend>
Content-Type: image/jpeg

<byte JPEG asli>
```

AI saat ini menerima **raw image bytes**, bukan FormData, base64 JSON, URL gambar atau path filesystem. JPEG, PNG dan WebP didukung. Batas gambar8MiB, body10MiB, dimensi128..6000 piksel. Jangan resize/tight-crop otomatis file sumber di frontend; preview CSS boleh diperkecil, tetapi inference A2 memerlukan informasi piksel native.

Field penting dari hasil gabungan:
- image_width/image_height, source_geometry dan instances[].polygon_xy untuk overlay.
- instances[].predicted_weight_mg, eligibility dan rejection_reason.
- summary.detected/analyzed/rejected/coverage serta analyzed_visible_mass_mg/g.
- histogram, mean dan median untuk larva yang benar-benar dianalisis.
- decision_support, model/pipeline/preprocessing version, provenance, limitations dan history_id.

Label yang dipertahankan: estimasi massa larva terlihat yang berhasil dianalisis. Berat foto A2 bukan otomatis mean wet-weight B1 atau biomassa seluruh wadah. A2 standalone /estimate-weight tetap memerlukan source4056x3040, ROI pada koordinat sumber dan review yang sesuai.

## 5. Data Water, B1, dan galeri memiliki kebutuhan berbeda

**Water:** GET /water-quality/replay/periods, lalu gunakan start/end/pond_id yang dikembalikan untuk POST /water-quality/replay/sessions. Gunakan next/advance dan tampilkan current_replay_timestamp; jangan memakai jam perangkat sekarang sebagai timestamp observasi historis. Sesi replay memori dapat hilang saat restart; snapshot/history hasil persisten. Analyze memerlukan riwayat kausal yang cukup, tidak sekadar tiga angka. Model A dapat menahan seluruh forecast ketika QA/history tidak cukup. Timestamp kontrak berupa ISO wall-clock WIB tanpa suffix timezone. pond_id pada seed adalah identitas grup rekaman, bukan bukti kolam produk/sensor tersambung; tenant akses adalah konsep terpisah.

**B1:** enam fitur wajib: moisture_percent, elapsed_days, current_weight_mg, previous_weight_mg, recent_growth_mg_per_day, forecast_horizon_days. Gunakan rata-rata berat basah terukur per individu dan selang pengamatan yang benar. Source user history memakai USER_ENTERED_MEASURED_HISTORY; contoh buatan harus SYNTHETIC_SCENARIO. Fitur/range tetap divalidasi model; jangan memasukkan foto sum/mean A2 sebagai pengukuran B1. Replay development tetap in-sample penelitian.

**Galeri:** fitur QA/riset/demo; tidak harus menjadi menu produk untuk pelanggan. Main package membawa semua metadata/thumbnail/baseline. Optional FISCYCLE_GALLERY_DATA.zip dibutuhkan untuk seluruh224 test original dan fresh inference dari foto test. Set yang ditampilkan sudah evaluated/released, tidak lagi blind. Pengguna produk yang mengunggah foto sendiri tidak memerlukan bundle galeri test.

## 6. Konfigurasi layanan di server

Seed Water lokal dalam handover diotorisasi untuk serah-terima developer. Jangan menganggapnya dataset berlisensi publik; pastikan izin pemilik data sebelum menampilkannya kepada publik atau memindahkannya ke hosting eksternal. Data galeri BSF publik memerlukan atribusi yang sudah disertakan. Backend dapat membatasi replay/galeri ke akses demo atau admin bila UI produk tidak memerlukannya.

Seed Water lokal dalam handover diotorisasi untuk serah-terima developer. Jangan menganggapnya dataset berlisensi publik; pastikan izin pemilik data sebelum menampilkannya kepada publik atau memindahkannya ke hosting eksternal. Data galeri BSF publik memerlukan atribusi yang sudah disertakan. Backend dapat membatasi replay/galeri ke akses demo atau admin bila UI produk tidak memerlukannya.

Ekstrak main package dan jalankan dari service/. Tetapkan melalui environment process/container, misalnya:

```text
FISCYCLE_RUNTIME_ENV=production
FISCYCLE_BSF_DEVICE=cpu
FISCYCLE_GATEWAY_TOKENS={"<secret-server-tenant-a>":"tenant-a"}
FISCYCLE_BSF_HISTORY_DB=/var/lib/fiscycle/bsf_history.sqlite3
FISCYCLE_BSF_GALLERY_DB=/var/lib/fiscycle/bsf_gallery.sqlite3
# Optional jika galeri test diperlukan:
FISCYCLE_BSF_GALLERY_DATA=/data/FISCYCLE_GALLERY_DATA.zip
```

Nilai di atas adalah placeholder konfigurasi, bukan secret atau tenant nyata. Folder state harus dapat ditulis oleh proses. Water history otomatis memakai water_history.sqlite3 pada direktori yang sama. Mount folder state secara persisten, jangan bergantung pada filesystem container sementara. Raw gambar upload tidak disimpan oleh history AI; backend produk menentukan penyimpanan foto jika dibutuhkan dengan izin pengguna.

Environment .env.example adalah contoh saja; menyalinnya menjadi .env **tidak otomatis dibaca** oleh kode ini. Inject variabel melalui konfigurasi host/container/service supervisor yang dipilih tim. Jangan memasang FISCYCLE_BSF_ROOT/FISCYCLE_WATER_ROOT ke path Windows peneliti pada server; paket mendeteksi bsf_assets/water_assets sendiri.

Setelah environment siap:

```sh
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Gunakan satu worker pada implementasi job SQLite sekarang. AI dapat listen pada jaringan server, tetapi batasi akses melalui jaringan privat/firewall; backend produk yang mengaksesnya. Tanpa gateway secret, koneksi non-loopback ditolak. Startup production tanpa konfigurasi gateway diblokir. CORS tidak diperlukan untuk server-ke-server; jika memilih browser direct, perlu desain auth pengguna yang sesuai dan origin eksplisit. Membuka CORS bukan pengganti autentikasi.

Domain/HTTPS publik, reverse proxy, process restart, key rotation, upload limit pada proxy dan rate limiting diatur oleh deployment produk. CPU adalah jalur yang sudah diuji. Kapasitas server ditetapkan setelah mengukur RAM, latency dan concurrency pada staging; tidak ada janji spesifikasi minimum/cloud tertentu dari tes laptop.

Tenant AI berasal dari mapping secret yang dikelola server. Backend harus memverifikasi membership user/farm sebelum memilih secret, bukan menerima tenant dari field/header browser. Tenant AI memberi batas history/job per tenant; permission user/role di dalam tenant tetap tugas backend produk. Untuk demo satu tenant, backend tetap harus mencegah pengguna membaca record orang lain jika produk memerlukannya.

## 7. Respons, antrean dan error UX

Periksa HTTP status **dan** domain status. Gallery inference dapat mengembalikan HTTP200 dengan inference_status=FAILED/REJECTED; B1 juga mempunyai input_domain_status dan prediction null. Jangan menampilkan semua HTTP200 sebagai prediksi berhasil.

Tangani401(auth),403(access/loopback),404(record/dataset),409(state),413(ukuran),422(input),429(kapasitas) dan503(komponen/data tidak tersedia). Simpan X-Request-ID untuk diagnosis. Request foto tunggal dapat berjalan sinkron; jangan menahan HTTP untuk ratusan foto. Galeri menggunakan POST /gallery/jobs ->202, lalu polling GET /gallery/jobs/{id}; completed+remaining harus konsisten. Backend/frontend menampilkan cache_hit, pending, partial, rejected dan failed dengan benar.

Data measured, historical, AI-predicted dan simulated harus tetap dapat dibedakan dalam UI. Tidak ada biological safety threshold Water yang disahkan. A2 automatic-ROI errors dan A1->A2 integration tetap eksperimental, tidak menjadi klaim operasional panen/pakan.

## 8. Yang diserahkan dan pembagian tanggung jawab

**Rasya/AI:** FISCYCLE_DEV_HANDOVER.zip; model/config yang dibundel; openapi.json; README,requirements lock,.env.example; guide ini dan dokumentasi per-model/DSS; hasil uji/limitasi. Optional data ZIP766MB jika tim ingin galeri test lengkap. Notebook/raw training datasets tidak diperlukan untuk menjalankan inference.

**Backend/deployment tim:** pasang di staging,inject environment,secrets dan persistent volume; implement adapter endpoint publik; verifikasi login/role/farm; kelola domain/HTTPS/restart/rate limits; tetapkan penyimpanan foto/hasil utama produk.

**Frontend tim:** desain halaman/komponen sendiri,form upload/data historis,loading/retry/progress,error/partial states,grafik,overlay dan label sumber/keterbatasan. Frontend memanggil backend produk dengan auth pengguna yang sudah ada.

**QA bersama:** verifikasi real photo -> backend -> AI -> response -> UI; Water replay dan B1; invalid/missing input; dua tenant dengan penolakan silang; restart dengan history/job tetap ada; data bundle jika digunakan; domainHTTPS; ukuran file dan latency di jaringan target. Jalankan verify_checksums.py dan verify_package.py pada server staging sebelum menyatakan deployment selesai. Fresh install/Docker/server-online belum diuji pada sesi pengembangan lokal.

Kesimpulan status: paket AI siap diserahkan untuk integrasi; produk online dengan UI tim belum di-deploy atau diuji end-to-end di server tim. Penentuan stack backend, lokasi staging, domain, auth/farm mapping dan fitur Water historical-versus-live perlu disepakati tim sebelum go-live.
