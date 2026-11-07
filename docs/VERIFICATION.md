# Verifikasi handover AI Service

Runtime: `ai-service/`, release `3.0.0-rc2-local`, Windows CPU, Python 3.13.

## Bukti paket sumber

Paket RC2 sumber mencatat **18 tes pytest dan 23 pemeriksaan HTTP lulus**.
Laporan asli dipertahankan pada [LOCAL_VERIFICATION.json](../ai-service/docs/LOCAL_VERIFICATION.json),
[LOCAL_HTTP_SMOKE.json](../ai-service/docs/LOCAL_HTTP_SMOKE.json) dan
[LOCAL_TEST_RESULTS.xml](../ai-service/docs/LOCAL_TEST_RESULTS.xml).
Laporan ini mengacu pada pengujian paket RC2, bukan klaim eksekusi baru dari checkout ini.

## Checkout main

**PASS — 7 November 2026, WIB.** Dijalankan dari `ai-service/` dalam repository
`rasyagonn/fiscycle-model-ai`, memakai environment CPU terisolasi yang sudah ada.
Instalasi dependensi baru dari nol tidak diulang pada pengujian ini.

| Pemeriksaan aktual | Hasil |
|---|---|
| Pytest, model nyata dan 16 foto demo | 18 lulus; 0 gagal/error/skip |
| HTTP nyata, startup/docs, Water/A1/A2/B1, DSS, replay dan token salah | 23 lulus |
| Checksum empat bundle model dan 16 original + thumbnail galeri | Cocok |
| `pip check` dan versi paket terhadap requirements | Lulus; cocok dengan lock |
| Kontrak OpenAPI aktual versus snapshot | Cocok; metadata request ID/timestamp dikecualikan |
| Water `/next` dua kali dan reset | Tepat satu observasi per request; reset kosong |
| Perbandingan awal Water | Aktual target masa depan belum ditampilkan |
| Riwayat AI sesudah server restart | Tetap tersedia |
| Tanpa seed Water privat | Replay 503; inferensi request Water dan B1 tetap berjalan |
| Startup localhost tanpa token dan tanpa data privat | Berjalan; keempat model siap |
| Kode/model/data riset beku | 50 checksum sumber dan artefak model tetap cocok |

Selama tes inferensi, import Hugging Face, koneksi jaringan eksternal dan pembacaan
storage riset diblokir. Hanya HTTP loopback diizinkan. Data Water yang dipakai tes
dipasang dari luar repository dan tidak dikomit. Checkpoint, preprocessing dan
126 file service lain tetap identik dengan paket RC2; penyesuaian hanya dokumentasi,
ignore rules, helper checksum dan lokasi fixture tes Water melalui environment.

Laporan aktual: [verifikasi JSON](evidence/AI_SERVICE_MAIN_VERIFICATION.json),
[pemeriksaan HTTP](evidence/AI_SERVICE_MAIN_HTTP.json), serta
[hasil pytest](evidence/AI_SERVICE_MAIN_TEST_RESULTS.xml).
Tidak ada kegagalan tersisa pada cakupan pengujian ini. Semua server tes dihentikan.

## Jalankan ulang

Dari folder `ai-service/` dengan environment yang sudah diinstal:

```powershell
.\.venv\Scripts\python.exe tools/verify_checkout.py
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest tests/test_service.py -q
```

Untuk tes lengkap Water, set `FISCYCLE_WATER_REPLAY_CSV` ke CSV privat dengan metadata
dan `water_reference.json` di folder yang sama sebelum menjalankan tes/startup.
Tanpa fixture, tes yang bersangkutan di-skip secara eksplisit.

Dengan service aktif, jalankan di terminal lain:

```powershell
$env:FISCYCLE_AI_API_KEY="TOKEN_YANG_DIPAKAI_SERVICE_JIKA_ADA"
.\.venv\Scripts\python.exe tools/http_smoke.py --base-url http://127.0.0.1:8001 --water-fixture "D:\data-privat\water_reference.json"
```

Jika startup localhost tanpa token, abaikan baris pengisian key. Untuk memeriksa
penolakan credential, jalankan service dengan token dan kirim key yang sama pada suite.

## Batas yang belum diuji

- Docker tidak tersedia pada lingkungan pengujian sebelumnya; build/run belum diverifikasi.
- Cloud/remote API, Linux/macOS dan beban multiuser belum diverifikasi.
- Pengujian lokal tidak berarti deployment publik atau validasi biologis lapangan selesai.
- Model, data riset beku dan preprocessing A2 tidak dilatih atau diubah untuk handover ini.
