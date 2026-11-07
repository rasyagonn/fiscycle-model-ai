# Integrasi AI Fiscycle

Aplikasi Next.js tetap menjadi satu frontend Fiscycle. AI Service FastAPI berada di
`ai-service/` dan memakai model lokal release `3.0.0-rc2-local`. Tidak ada training ulang.
Jalur request: browser → `/api/ai/service/*` Next.js → FastAPI → model/checksum lokal.
Token upstream hanya dibaca di server. Foto diunggah asli tanpa resize/crop oleh Next.js.

## Menjalankan lokal

Prasyarat: Node.js 24, pnpm sesuai package.json, Python 3.13 64-bit. CPU didukung;
CUDA tidak diwajibkan. Internet diperlukan saat instalasi paket pertama.

```powershell
pnpm.cmd install --frozen-lockfile
py -3.13 -m venv ai-service/.venv
.\ai-service\.venv\Scripts\python.exe -m pip install -r ai-service/requirements.txt
Copy-Item .env.example .env.local
```

Isi `.env.local` dengan `FISCYCLE_AI_API_URL=http://127.0.0.1:8001`.
`FISCYCLE_AI_API_KEY` boleh kosong untuk uji localhost; untuk koneksi antarservice isi
token kuat milik tim. `ai:dev` mengirim token yang sama sebagai credential FastAPI.
Jangan memakai variabel NEXT_PUBLIC_ untuk URL privat/token. `.env.local` diabaikan Git.

Terminal pertama: `pnpm.cmd ai:dev`. Terminal kedua: `pnpm.cmd dev`.

- Aplikasi Mitra: http://localhost:3000/mitra/ai
- Aplikasi desktop: http://localhost:3000/desktop/ai
- AI health: http://127.0.0.1:8001/health
- Dokumen model API: http://127.0.0.1:8001/docs
- Gateway health: http://localhost:3000/api/ai/bridge

Jika AI belum hidup, UI menunjukkan layanan belum siap. Setelah server AI siap,
muat ulang halaman untuk mengambil ulang pilihan periode, trajektori dan galeri.

## Replay Water privat

Seed Water dan golden fixture TIDAK dimasukkan ke repository utama. Untuk instalasi
internal ini disimpan di folder saudara `../FISCYCLE_PRIVATE_REPLAY/`; atur:

```dotenv
FISCYCLE_WATER_REPLAY_CSV=../FISCYCLE_PRIVATE_REPLAY/water_replay_v1.csv
```

CSV memuat 299 rekaman lokal; `water_replay_v1.metadata.json` harus di samping CSV.
Untuk smoke test numerik lengkap diperlukan `water_reference.json` di folder yang sama.
Jangan publikasikan/commit data privat, `.env`, state SQLite atau cache.
Tanpa seed: inferensi Water dari request tetap bisa, replay Water mengembalikan 503.
Replay B1 publik dan 16 foto demo sudah ada di ai-service; tidak perlu full galeri 224 foto.

## Fitur dan kontrak

- Water: QA sensor, prediksi 30/60/120 menit yang didukung, replay bertahap, tabel
  pasangan galat vs persistence, alasan DSS, dan riwayat. Semua timestamp rekaman WIB.
- A1: segmentasi larva terlihat dan overlay; raw image dan multipart didukung.
- A2 v3: berat dari foto native 4056×3040 dengan reviewed ROI. Canvas 2048 netral 127,
  satu bilinear resize 224 dan normalisasi persis model. Jangan ganti preprocessing.
- A1→A2: eksperimen foto multi-larva, larva yang ditolak tetap ditampilkan; bukan biomassa batch.
- Galeri: 8 A1 pilihan pengguna + 8 A2 acak. Status REJECTED/PARTIAL bukan kegagalan transport
  dan bukan akurasi; jangan mengganti foto yang ditolak.
- B1: replay 16 trajektori development, prediksi rerata wet-weight mg/individu, serta
  enam fitur manual dengan asal input measured-declared atau synthetic-scenario.
- DSS: faktor, availability, asal data, aturan terpicu, sumber dan kebutuhan verifikasi.
- Riwayat: trace AI mempertahankan versi model saat perhitungan. Backend utama tetap
  pemilik business history, authorization, farm, pond dan user.

Daftar lengkap endpoint: `ai-service/docs/API_ENDPOINTS.md` dan
`ai-service/docs/OPENAPI.json`. Kontrak gateway meneruskan JSON/status asli tanpa
prediksi fallback; prefix `/api/ai/service` ditambahkan sebelum path asli.
Contoh: POST `/api/ai/service/api/v1/bsf/forecast`.
`lib/ai/service-client.ts` menyediakan client browser; `lib/ai/server.ts` hanya server.

Kompatibilitas lama:

- `/api/ai/bridge`: health asli dan POST domain bsf_b1/water_analyze dengan payload asli.
- `/api/ai/recommend/:pondId`: HTTP409 MEASUREMENTS_REQUIRED; kolam demo tidak
  dipetakan ke rekaman lokal tanpa bukti relasi. Kirim riwayat ke Water analyze.
- `/api/ai/match-supply`: ranking bisnis deterministik atas seed, mode BUSINESS_RULE_DEMO;
  tidak mengaku memakai model supply yang tidak ada.
- `/api/iot/telemetry`: tetap simulasi/echo tidak persisten, live_sensor_connected=false.

## Pengujian

Dengan kedua server aktif dan seed privat tersedia:

```powershell
pnpm.cmd typecheck
pnpm.cmd lint
pnpm.cmd build
pnpm.cmd test:ai
```

Catatan: suite Python bawaan RC2 dijalankan dari folder ai-service dan mengharapkan
PRIVATE_WATER_REPLAY sebagai saudara ai-service untuk golden Water. Tes integrasi Node
memakai `FISCYCLE_WATER_REPLAY_CSV` dan tidak perlu menyalin fixture ke repo.
`FISCYCLE_AI_TEST_URL` dapat mengganti URL aplikasi untuk tes. Laporan HTTP tersimpan di
`ai-service/.cache/MAIN_INTEGRATION_HTTP.json` (diabaikan Git). Status aktual pengujian
integrasi dicatat di `docs/AI_INTEGRATION_VERIFICATION.json` setelah tes dijalankan.
Tes browser opsional: `py -3.13 tests/ai_browser_smoke.py` (perlu Selenium dan Chrome).

CSS memakai plugin resmi @tailwindcss/postcss untuk Webpack dan Turbopack. Konfigurasi
loader Turbopack lama tidak dipakai lagi karena build --webpack melewatinya dan sebelumnya
menghasilkan halaman tanpa utility Tailwind walaupun build selesai tanpa error.

## Batas deployment dan ilmiah

Auth aplikasi saat ini adalah demo Zustand/client-side, bukan authorization server.
Karena itu proxy produksi default tertutup. `FISCYCLE_AI_PROXY_ENABLED=true` hanya untuk
demo internal/lingkungan yang aksesnya dibatasi, atau setelah backend utama memasang
otorisasi server. Jangan menjadikan service token di browser sebagai sistem login baru.
Allowlist endpoint, pemeriksaan origin mutation, batas upload 10 MB dan timeout 120 detik
tetap berlaku; invalid input/layanan mati tidak menghasilkan prediksi pengganti.

Jalankan FastAPI satu worker. Sesi replay/cache berada di memori; restart mengakhiri sesi
replay, sementara trace SQLite dipertahankan. Belum ada pembuktian scaling multiuser/SLA.
Dockerfile tersedia tetapi Docker/cloud/Linux/macOS belum diuji pada integrasi ini.
Model HF privat pernah diverifikasi pinned; runtime ini tidak memerlukan HF_TOKEN.
HF Docker Space tidak dideploy karena percobaan sebelumnya HTTP402.

BSF tetap RESEARCH_PROTOTYPE / NOT_FIELD_VALIDATED. A1 validation satu primary group;
A2 final test satu primary group, label/kalibrasi/domain terbatas. Weight A2 wet/dry belum
terkonfirmasi dan piksel bukan mm. B1 replay in-sample bukan validasi lapangan. Tidak ada
rantai A2→B1 otomatis. Water satu kolam historis, DO/TAN tidak tersedia, kalibrasi belum
diverifikasi. DSS engineering rules belum menjadi ambang biologis yang disahkan ahli.
Ringkasan operasional lama tetap diberi label simulasi agar tidak tercampur dengan model asli.

## Hasil verifikasi aktual — 7 November 2026 (WIB)

GO untuk MVP riset/internal: typecheck, lint (0 warning), build production, pip check,
22 pemeriksaan HTTP integrasi, 15 tes browser Chrome, dan startup development Turbopack
lulus. Tes browser meliputi kedua replay, foto A1/A2 reviewed ROI, DSS, riwayat,
lebar 390/768 serta desktop, enam langkah Golden Thread, dan resource/hydration tanpa error.
Sepuluh rute aplikasi lama juga tetap dapat diakses, termasuk redirect yang semestinya.
Model, preprocessing dan galeri tetap identik byte dengan release lokal RC2.

Self-test lama mengharuskan ALC-0031 padahal ID itu sudah ada di seed. Assertion diperbaiki
untuk memastikan alokasi baru unik, isi transaksi benar dan alokasi lama tidak tertimpa;
seed dan logika alokasi tidak diubah. Dua ikon manifest yang sebelumnya 404 diekspor
dari logo Fiscycle yang sudah ada. Ini perbaikan aset aplikasi, bukan perubahan desain model.

Detail: AI_INTEGRATION_VERIFICATION.json, AI_INTEGRATION_FILES.json dan ai-evidence/.
Seluruh server pengujian dihentikan setelah tes. Jalankan dua terminal seperti panduan
di atas untuk mencoba sendiri. Belum commit/push/deploy. Auth server publik, Docker,
OS selain Windows dan validasi ilmiah lapangan tetap sesuai batasan yang disebutkan.
