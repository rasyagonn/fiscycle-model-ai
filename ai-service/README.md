# Fiscycle AI Service — model lokal

API Water Quality + Smart BSF A1/A2 v3/B1, DSS, historical replay, dan 16 foto demo.
Model disertakan dan diperiksa SHA-256. Tidak perlu HF_TOKEN atau unduhan model.
Paket runtime CPU dikunci untuk Python 3.13 (diverifikasi di Windows 64-bit 3.13.3).
Internet diperlukan saat instalasi dependensi pertama. GPU tidak wajib.

Folder ini adalah runtime handover aktif dalam repository `rasyagonn/fiscycle-model-ai`.
Panduan backend/UI: [integrasi](../docs/INTEGRATION.md). Status checkout terbaru:
[verifikasi](../docs/VERIFICATION.md). Jalankan perintah di bawah **dari folder ini**,
agar `app.main` tidak mengacu ke aplikasi riset lama di root repository.

## Menjalankan di Windows

Install Python 3.13 64-bit dengan Python Launcher. Klik dua kali `JALANKAN_WINDOWS.cmd`.
Buka http://127.0.0.1:8001/health dan http://127.0.0.1:8001/docs.
Script membuat virtual environment terpisah, memasang dependensi, lalu menjalankan API localhost.
Script ini tidak memasang Python. Port 8001 harus kosong. Ctrl+C menghentikan API.

Atau PowerShell, dari folder ai-service:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1
```

Linux/macOS: `python3.13 -m venv .venv`, `.venv/bin/python -m pip install -r requirements.txt`,
lalu `.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1`.
Pemasangan di OS lain dan Docker belum dieksekusi; jangan menganggapnya sudah lulus.

## Replay privat

Pertahankan folder `PRIVATE_WATER_REPLAY/` di sebelah ai-service untuk mencoba replay Water.
Jika ai-service dipindah ke repo utama, simpan seed privat di luar Git lalu set:
`$env:FISCYCLE_WATER_REPLAY_CSV="C:\lokasi-privat\water_replay_v1.csv"`.
Metadata JSON harus tetap berada di sebelah CSV. Tanpa seed, inferensi Water dari request
tetap berjalan; endpoint replay Water mengembalikan 503. Replay B1 sudah di dalam ai-service.

## Integrasi dengan backend utama

Hanya masukkan folder ai-service ke repository tim yang aksesnya dibatasi. Model `.pt`/`.joblib`
di model_artifacts sengaja diizinkan oleh .gitignore. Jangan publikasikan model tanpa persetujuan pemilik.
Jangan commit folder privat, .venv, .cache, .env, token, atau riwayat SQLite.
Frontend -> backend utama -> AI Service. Backend utama tetap mengurus login, user,
farm/pond, authorization dan business history. AI Service menerima request HTTP/JSON/multipart.

Untuk koneksi antarservice, buat token sendiri lalu set di terminal server:

```powershell
$env:FISCYCLE_RUNTIME_ENV="production"
$env:FISCYCLE_AI_SERVICE_TOKEN="ISI_TOKEN_KUAT_MILIK_TIM"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --workers 1
```

Token contoh harus diganti; simpan sebagai server secret, jangan berikan ke browser.
Backend utama mengirim `Authorization: Bearer <token>`.
Atur backend `FISCYCLE_AI_API_URL=http://127.0.0.1:8001` dan `FISCYCLE_AI_API_KEY=<token>`
untuk dua service pada host yang sama. Gunakan alamat jaringan/container AI yang dapat dicapai
jika host berbeda. Gunakan jaringan privat/TLS untuk deployment.

| Kebutuhan | Endpoint |
|---|---|
| Kesehatan/model | GET /health, GET /api/v1/models |
| Kontrak aktual | GET /docs, GET /openapi.json |
| Water + DSS | POST /api/v1/water/analyze |
| Water replay | GET /api/v1/water/replay/periods |
| Segmentasi A1 | POST /api/v1/bsf/segment |
| Berat A2 v3 (reviewed ROI) | POST /api/v1/bsf/estimate-weight |
| Eksperimen foto A1 -> A2 | POST /api/v1/bsf/analyze-photo |
| Forecast B1 | POST /api/v1/bsf/forecast |
| B1 replay | GET /api/v1/bsf/replay/trajectories |
| BSF DSS | POST /api/v1/bsf/decision-support |
| Galeri demo | GET /api/v1/bsf/demo-gallery |
| Riwayat trace AI | GET /api/v1/bsf/history |

Lihat docs/API_ENDPOINTS.md, docs/OPENAPI.json, dan examples/ untuk kontrak/contoh.
Jangan resize/crop foto A2 di backend sebelum dikirim; preprocessing v3 ada di AI Service.
Galeri berisi 8 A1 pilihan pengguna + 8 A2 acak; 1 A2 tetap ditolak oleh quality guard.
Tidak semua foto akan menghasilkan prediksi; status PARTIAL/REJECTED harus ditampilkan.

## Pengujian

```powershell
.\.venv\Scripts\python.exe tools/verify_checkout.py
.\.venv\Scripts\python.exe -m pytest tests/test_service.py -q
.\.venv\Scripts\python.exe tools/http_smoke.py --base-url http://127.0.0.1:8001 --water-fixture "D:\data-privat\water_reference.json"
```

Tes Water numerik/replay memerlukan data privat yang diberikan terpisah; data ini tidak ikut Git.
Set `FISCYCLE_WATER_REPLAY_CSV` ke CSV dengan metadata dan fixture di folder yang sama.
Tanpa fixture, tes Water yang memerlukannya akan di-skip. Jika server memakai token,
set `FISCYCLE_AI_API_KEY` pada terminal smoke test. Hasil aktual paket ada di docs/LOCAL_VERIFICATION.json.

## Docker (konfigurasi tersedia; belum diuji karena Docker tidak tersedia)

```sh
docker build -t fiscycle-ai-service:3.0.0-rc2-local .
docker run --rm -p 8001:8000 --env-file .env -v fiscycle-ai-state:/data/state fiscycle-ai-service:3.0.0-rc2-local
```

Salin .env.example ke .env dan isi token. Replay Water memerlukan bind mount privat ke
`/data/replay/water` (CSV + metadata); data ini tidak dimasukkan ke Docker image.
Model sudah ada dalam image; tidak perlu HF cache/token. HF mode bukan target distribusi lokal ini.

## Batas hasil

Ini MVP riset. Water historical replay bukan live feed. BSF tetap RESEARCH_PROTOTYPE /
NOT_FIELD_VALIDATED. A1 -> A2 bukan biomassa batch tervalidasi; A2 -> B1 tidak otomatis.
Weight A2 wet/dry belum terkonfirmasi. DSS bukan ambang budidaya yang disahkan ahli.
Tidak ada pelatihan ulang atau perubahan checkpoint. Baca docs/KNOWN_LIMITATIONS.md.
