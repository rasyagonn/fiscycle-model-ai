# Integrasi AI Service ke aplikasi tim

Runtime yang diserahkan adalah **`ai-service/`, release `3.0.0-rc2-local`**.
Backend dan frontend produk tetap dikelola tim developer. Tidak perlu mengambil
kode aplikasi dari repository lain atau menjalankan dashboard riset lama.

## Pembagian tanggung jawab

| AI Service | Backend dan frontend produk |
|---|---|
| Load model, checksum dan preprocessing | Login, otorisasi, user/farm/pond dan isolasi akses |
| Inferensi Water/A1/A2/B1 | Endpoint publik, upload dari browser dan UI |
| Replay, DSS, provenance, trace inferensi | Penyimpanan business history, deployment dan HTTPS |

Jalur: **UI → backend produk → AI Service privat**. Token service bukan token login pengguna.
Backend harus memeriksa akses pengguna sebelum mengirim request ke AI.

## Instalasi dan startup

Ikuti [README AI Service](../ai-service/README.md). Gunakan Python 3.13 64-bit,
environment terpisah dan requirements yang dikunci. Jalankan dari folder `ai-service/`
agar `app.main` mengacu ke runtime baru, bukan `app/` riset di root repository.
Gunakan satu worker; sesi replay berada di memori dan hilang ketika restart.

Untuk uji localhost tanpa token, bind hanya `127.0.0.1`. Untuk koneksi antarservice,
buat token acak kuat sendiri dan set di terminal server:

```powershell
$env:FISCYCLE_MODEL_SOURCE="local"
$env:FISCYCLE_RUNTIME_ENV="production"
$env:FISCYCLE_AI_SERVICE_TOKEN="GANTI_DENGAN_TOKEN_ACAK_KUAT"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --workers 1
```

Backend produk menyimpan konfigurasi berikut sebagai server environment:

```dotenv
FISCYCLE_AI_API_URL=http://127.0.0.1:8001
FISCYCLE_AI_API_KEY=TOKEN_YANG_SAMA_DENGAN_SERVICE
```

Kedua nama ini adalah contoh konfigurasi adapter milik backend, bukan variabel
yang otomatis dibaca AI Service. Kirim key sebagai `Authorization: Bearer <token>`.
Jika berbeda container/host, gunakan alamat jaringan privat AI yang dapat dijangkau.
Jangan memakai `localhost` browser sebagai alamat server lain. Gunakan TLS/jaringan privat.
`.env.example` hanya template; Python tidak otomatis memuat `.env`. Gunakan shell,
secret platform atau `docker --env-file`. Token tidak boleh masuk bundle frontend.

## Endpoint utama

| Aksi | API AI |
|---|---|
| Kesehatan dan kesiapan model | `GET /health`, `GET /api/v1/models` |
| QA, forecasting dan DSS Water | `POST /api/v1/water/analyze` |
| Periode Water | `GET /api/v1/water/replay/periods` |
| Membuat replay Water | `POST /api/v1/water/replay/sessions` |
| Langkah tepat satu observasi | `POST /api/v1/water/replay/sessions/{session_id}/next` |
| Memajukan beberapa observasi | `POST /api/v1/water/replay/sessions/{session_id}/advance?steps=25` |
| Segmentasi A1 | `POST /api/v1/bsf/segment` |
| Berat A2 v3 dengan reviewed ROI | `POST /api/v1/bsf/estimate-weight` |
| Foto A1→A2 eksperimental | `POST /api/v1/bsf/analyze-photo` |
| Forecast B1 | `POST /api/v1/bsf/forecast` |
| Daftar replay B1 | `GET /api/v1/bsf/replay/trajectories` |
| Replay B1 sampai observasi N | `GET /api/v1/bsf/replay/{trajectory_id}?revealed=N` |
| DSS BSF | `POST /api/v1/bsf/decision-support` |
| Galeri 16 foto demo | `GET /api/v1/bsf/demo-gallery` |
| Riwayat AI | `GET /api/v1/bsf/history`, `GET /api/v1/water/history` |

Kontrak field dan response lengkap: [OpenAPI](../ai-service/docs/OPENAPI.json),
[daftar endpoint](../ai-service/docs/API_ENDPOINTS.md), atau `/docs` pada service hidup.
Contoh client: [Node.js](../ai-service/examples/node_client.mjs) dan
[Python](../ai-service/examples/python_client.py). Tim boleh membuat endpoint publik
sendiri dan memetakan response menjadi view model, sambil mempertahankan maknanya.

## Foto dan kualitas hasil

Upload menerima **raw image bytes atau multipart field `file`**. Jangan kirim path
filesystem lokal, URL atau base64 sebagai pengganti kontrak. Batas body 10 MiB.
Backend meneruskan byte asli; preview CSS boleh diperkecil, file inferensi jangan di-resize.
A2 standalone memerlukan source 4056×3040, koordinat ROI sumber dan `reviewed_roi=true`.
Canvas native-pixel 2048, resize bilinear 224 dan normalisasi dijalankan service.
Jangan mengubah preprocessing untuk menyesuaikan UI.

`PARTIAL` dan `REJECTED` adalah keluaran quality guard yang harus ditampilkan;
status HTTP 200 tidak berarti seluruh larva menghasilkan prediksi. Massa larva
terlihat yang diterima bukan biomassa seluruh batch. A2 tidak otomatis menjadi input B1.

## Replay dan sumber data

Model dan 16 foto demo ikut Git. Replay B1 publik sudah disertakan; full galeri riset
224 foto tidak diperlukan untuk demo ini. Foto memiliki atribusi pada
[ATTRIBUTION.txt](../ai-service/assets/demo_gallery/ATTRIBUTION.txt).

Untuk Water, minta data internal kepada Rasya melalui kanal privat. Simpan CSV,
`water_replay_v1.metadata.json`, dan fixture tes `water_reference.json` (jika diizinkan)
bersama-sama **di luar repository**, lalu sebelum startup:

```powershell
$env:FISCYCLE_WATER_REPLAY_CSV="D:\data-privat\water_replay_v1.csv"
```

Tanpa seed, replay Water mengembalikan 503 dan tidak mengarang rekaman.
Inferensi Water dari request valid tetap tersedia. Jangan commit data privat.
`pond_id` seed adalah grup rekaman historis, bukan bukti sensor/farm produk tersambung.
Bedakan measured, predicted, historical dan simulated; nilai yang tidak tersedia tetap null.

## Grafik aktual versus prediksi

Untuk Water, baca `observations`, `completed_comparisons`, `current_replay_timestamp`
dan `metrics` dari state sesi. Forecast pada waktu t dibandingkan dengan aktual
di target t+30/60/120 menit yang sudah terungkap, bukan pengukuran pada waktu t.
Toleransi pencocokan 90 detik; prediksi pending tidak boleh diberi aktual masa depan.
Bandingkan model dengan `persistence_same_pairs` pada pasangan yang sama.
Backend dapat membatasi daftar comparison yang dikirim; perhatikan `comparisons_truncated`.

Frontend mengatur putar/jeda dengan memanggil `/next` secara berurutan, menunggu
response sebelumnya sebelum langkah berikutnya. Jeda animasi UI berbeda dari
interval waktu historis. Endpoint start/pause bukan scheduler otomatis di server.
Timestamp rekaman naive adalah **WIB (Asia/Jakarta)**; jangan ditafsirkan sebagai UTC.
Untuk B1, tampilkan error hanya pada comparison `time_aligned=true`.

## Pengujian dan deployment

[Verifikasi](VERIFICATION.md) memisahkan tes aktual dari hal yang belum diuji.
Jalankan tes pada mesin/staging tim setelah instalasi. Tanpa fixture privat,
tes Water tertentu di-skip; skip bukan hasil lulus untuk fitur tersebut.
Jangan mengklaim deployment publik, Docker, performa multiuser atau validasi lapangan
selesai hanya karena uji lokal Windows lulus.

Simpan state SQLite dan cache di volume privat; jangan ditaruh di Git. Terapkan login,
otorisasi, rate limit, HTTPS dan kebijakan retensi upload pada backend/infrastruktur produk.
Health/docs adalah endpoint publik service; batasi akses jaringan sesuai kebutuhan tim.
BSF tetap `RESEARCH_PROTOTYPE / NOT_FIELD_VALIDATED`; DSS bukan ambang biologis terverifikasi ahli.
