# Fiscycle AI — mulai di sini

Repository ini menyediakan layanan AI untuk **Water Quality** dan **Smart BSF**. Developer produk dapat membuat UI dan endpoint publik sendiri, lalu menghubungkannya ke satu layanan FastAPI ini. Tidak perlu melatih ulang model.

**Status:** paket telah diuji pada lingkungan lokal Windows CPU. Deployment online, instalasi baru di server, dan integrasi aplikasi tim belum diverifikasi. Dashboard bawaan adalah alat demo/QA internal.

## 1. Unduh dua paket

Buka **[Release MVP v2.1.0](https://github.com/rasyagonn/fiscycle-model-ai/releases/tag/v2.1.0-mvp)** dengan akun yang memiliki akses repository, lalu unduh:

| File | Gunanya |
|---|---|
| `FISCYCLE_DEV_HANDOVER.zip` | Layanan siap dijalankan, checkpoint, preprocessing, dua dataset replay, dokumentasi dan kontrak API. |
| `FISCYCLE_GALLERY_DATA.zip` | Foto resolusi penuh untuk galeri BSF lengkap dan inferensi dari foto galeri. Wajib untuk scope galeri MVP saat ini. |

Clone repository atau unduhan otomatis **Source code** saja belum menyertakan model dan dataset runtime. Ukuran dan SHA-256 kedua paket tercatat di [ARTIFACTS.json](ARTIFACTS.json).

## 2. Jalankan API secara internal

Ekstrak `FISCYCLE_DEV_HANDOVER.zip`. Buka terminal pada folder paket yang berisi `verify_checksums.py` dan `service/`. Paket utama diperiksa sebelum menambahkan data galeri.

Dengan Python 3.13 pada Windows PowerShell:

```powershell
python verify_checksums.py
Copy-Item -LiteralPath "D:\LOKASI_UNDUHAN\FISCYCLE_GALLERY_DATA.zip" -Destination .\service\
cd service
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python verify_package.py
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Ganti `D:\LOKASI_UNDUHAN` dengan lokasi ZIP galeri di komputer developer. **Biarkan ZIP galeri tetap terkompresi.** Hentikan langkah berikutnya jika pemeriksaan atau instalasi gagal; simpan output error untuk diagnosis. Instalasi dependensi dari nol tetap perlu diuji di komputer/server penerima.

Setelah startup berhasil, buka:

- Kontrak API interaktif: http://127.0.0.1:8000/docs
- Demo terpadu internal: http://127.0.0.1:8000/ecosystem
- Galeri BSF: http://127.0.0.1:8000/bsf-intelligence#gallery

## 3. Integrasikan ke aplikasi tim

Baca **[panduan integrasi produk](FISCYCLE_TEAM_INTEGRATION_GUIDE.md)**. Salinannya tersedia dalam paket di `docs/PRODUCT_MVP_INTEGRATION_GUIDE.md`; kontrak lengkap ada di `openapi.json` paket dan `/docs` saat layanan berjalan.

Alur integrasi: **UI Fiscycle → backend produk dengan login/otorisasi → layanan AI privat**. Tim dapat memakai framework, desain, dan URL publik sendiri. Secret gateway AI disimpan di server.

| Fitur | Route awal yang tersedia |
|---|---|
| Analisis foto BSF A1 → A2 v3 | `POST /api/v1/bsf/analyze-photo` |
| Forecast pertumbuhan B1 | `POST /api/v1/bsf/forecast` |
| Historical replay BSF | `GET /api/v1/bsf/replay/trajectories` |
| Explainable DSS BSF | `POST /api/v1/bsf/decision-support` |
| Historical replay Water | `GET /water-quality/replay/periods` |
| Analisis Water A/B/C | `POST /water-quality/analyze` |

Upload foto ke layanan AI memakai **raw image bytes**, bukan multipart atau base64. Detail request, autentikasi, error, state persisten dan deployment tersedia pada panduan integrasi. Contoh startup di atas hanya untuk internal loopback; deployment online membutuhkan konfigurasi server pada panduan tersebut.

## File mana yang perlu dibaca?

| Kebutuhan | Lokasi |
|---|---|
| Mulai mencoba | README ini + dua ZIP di Release |
| Menghubungkan frontend/backend produk | [FISCYCLE_TEAM_INTEGRATION_GUIDE.md](FISCYCLE_TEAM_INTEGRATION_GUIDE.md) |
| Mengubah implementasi API | [app/README.md](app/README.md), [app/STRUCTURE.md](app/STRUCTURE.md), kode `app/` |
| Memeriksa bukti pengujian | [FISCYCLE_MVP_VERIFICATION_REPORT.md](FISCYCLE_MVP_VERIFICATION_REPORT.md) |
| Audit ilmiah atau melanjutkan riset | Laporan `*REPORT.md`, evidence matrix, dan `.agents/skills/` |

Laporan audit dan folder riset tidak perlu dibaca seluruhnya untuk mencoba paket. Source API yang diedit ada di `app/`; paket ZIP adalah hasil build, sehingga edit pada paket saja tidak memperbarui source repository.

## Batas penggunaan yang harus dipertahankan

- Water adalah **historical replay**, belum layanan sensor IoT live yang tervalidasi. Waktu rekaman menggunakan WIB.
- BSF tetap **RESEARCH_PROTOTYPE / NOT_FIELD_VALIDATED**. Estimasi berat foto A2 bukan pengukuran berat basah B1; rantai A1 → A2 → B1 belum tervalidasi secara ilmiah.
- Pertahankan label data terukur, historis, prediksi, simulasi, penolakan dan nilai `null` pada UI produk.
- Seed Water lokal hanya untuk handover developer yang diotorisasi; bukan data berlisensi publik. Galeri BSF memerlukan atribusi yang disertakan dalam paket.
- Jangan melatih ulang atau mengubah checkpoint, preprocessing A2 v3 dan data riset beku untuk integrasi UI.

**Penerimaan developer:** jalankan verifikasi paket, coba foto BSF dan kedua replay, lalu uji alur UI → backend → AI di staging. GitHub Release bukan deployment API online.
