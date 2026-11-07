# Fiscycle AI Service

Layanan FastAPI mandiri untuk **Water Quality dan Smart BSF A1, A2 v3, B1**.
Tim produk menghubungkannya ke backend dan UI sendiri melalui HTTP.
Model lokal, preprocessing, replay B1 dan 16 foto demo sudah tersedia di Git.
Tidak perlu training ulang, Hugging Face, atau ZIP galeri 224 foto untuk runtime ini.

**Mulai dari [`ai-service/`](ai-service/README.md).** Release `3.0.0-rc2-local`
telah diuji di Windows CPU. Status checkout terbaru ada di
[hasil verifikasi](docs/VERIFICATION.md). Deployment publik dan Docker belum diverifikasi.

## Jalankan lokal

Prasyarat: Python **3.13 64-bit**, Git, serta internet untuk instalasi dependensi pertama.
Dari PowerShell:

```powershell
git clone https://github.com/rasyagonn/fiscycle-model-ai.git
cd fiscycle-model-ai/ai-service
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1
```

Buka **http://127.0.0.1:8001/docs** untuk mencoba API dan
http://127.0.0.1:8001/health untuk melihat kesiapan model.
Alternatif Windows: klik `ai-service/JALANKAN_WINDOWS.cmd`.
Tidak ada frontend produk yang perlu dijalankan dari repository ini.

## Untuk teman developer

| Kebutuhan | Baca |
|---|---|
| Menjalankan service | [README AI Service](ai-service/README.md) |
| Menghubungkan backend dan UI | [Panduan integrasi](docs/INTEGRATION.md) |
| Endpoint dan request/response | [Daftar endpoint](ai-service/docs/API_ENDPOINTS.md), [OpenAPI](ai-service/docs/OPENAPI.json), `/docs` |
| Contoh client | [Python](ai-service/examples/python_client.py), [Node.js](ai-service/examples/node_client.mjs) |
| Tes yang sudah dijalankan dan batasnya | [Verifikasi](docs/VERIFICATION.md) |
| Batas ilmiah | [Known limitations](ai-service/docs/KNOWN_LIMITATIONS.md) |

Alur aplikasi: **UI tim → backend tim (login/otorisasi) → AI Service**.
Service token disimpan di backend. Tim bebas mengubah desain dan endpoint publik
aplikasinya; checkpoint, urutan fitur dan preprocessing A2 v3 harus dipertahankan.

## Data dan struktur

```text
ai-service/       layanan yang diserahkan ke developer, model dan galeri demo
docs/            panduan integrasi, verifikasi, serta arsip laporan
app/             aplikasi riset/dashboard internal versi lama; bukan entry point baru
.agents/skills/  kode dan catatan riset; tidak diperlukan oleh runtime ai-service
```

Replay **Water** membutuhkan CSV privat beserta metadata yang dikirim terpisah
melalui kanal internal. Set `FISCYCLE_WATER_REPLAY_CSV` ke lokasi CSV di luar Git.
Tanpa data itu, replay Water mengembalikan **503**; inferensi Water dari request
yang valid dan modul BSF tetap tersedia. Detail pemasangan ada di panduan integrasi.
Replay B1 publik dan galeri demo sudah disertakan.

Water adalah historical replay, bukan sensor live. BSF berstatus
`RESEARCH_PROTOTYPE / NOT_FIELD_VALIDATED`; A1→A2 eksperimental dan A2→B1
tidak otomatis. DSS belum menjadi ambang biologis yang disahkan ahli.

Laporan dan paket v2.1.0 disimpan sebagai [arsip](docs/archive/v2.1.0/README.md).
Gunakan `ai-service/` untuk handover terbaru, bukan langkah instalasi dari arsip.
