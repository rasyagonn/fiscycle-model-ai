# Fiscycle Smart BSF — Model B1: Starter Materials (revised)

**Folder project milik pengguna sudah ada: `fiscycle-bsf-ai`. Paket ini tidak menentukan struktur proyek.**

## Isi paket (semua file diletakkan rata di dalam ZIP, bukan template struktur subfolder)

| File | Fungsi |
|---|---|
| `Impact of substrate moisture content on BSF larvae Data.xlsx` | Data penelitian **asli**, jangan diubah. |
| `Fiscycle_BSF_SubstrateMoisture_LongForm_400rows.csv` | Hasil penyusunan ulang data menjadi long format, untuk memudahkan audit dan training; validasi lagi ke workbook asli. |
| `PROMPT_AI_MODEL_B.md` | Prompt utama untuk coding AI agar memeriksa workspace lalu membuat eksperimen Model B1. |
| `SKILL.md` | Aturan riset/ML dan batasan ilmiah; **AI coding menentukan lokasi skill** setelah membaca struktur dan aturan tools yang digunakan. |
| `MODEL_B_REQUIREMENTS.md` | Target, deliverables, quality gates tanpa memaksa nama/lokasi output. |
| `README_PAKET.md` | File ini, dokumentasi singkat. |

## Cara pakai (tanpa memaksakan struktur)
1. Simpan file ZIP ini **di dalam project yang sudah ada** bernama `fiscycle-bsf-ai`, atau salin file dari ZIP ke folder project yang kamu tentukan.
2. **Jangan ekstrak sambil menimpa file yang namanya sama tanpa pemeriksaan.** Paket ini tidak mengklaim lokasi subfolder tertentu.
3. Minta AI coding **memeriksa isi aktual root project dan isi ZIP terlebih dahulu**. Berikan `PROMPT_AI_MODEL_B.md`, `SKILL.md` dan `MODEL_B_REQUIREMENTS.md` sebagai instruksi.
4. Biarkan AI coding membuat/mengorganisasikan **satu notebook utama** dan output yang relevan berdasarkan workspace sesungguhnya.
5. Periksa laporan hasil training dan evaluasi sebelum menghubungkannya ke MVP.

## Status data dan model
Dataset berasal dari eksperimen publik: 20 replikasi, 4 level kadar air substrat, sekitar 400 pengamatan longitudinal. Data **bukan sensor lokal Fiscycle**. File CSV telah diolah untuk memudahkan pembacaan (bukan pengganti workbook asli). Tidak ada model terlatih, skor akurasi, notebook implementasi, atau output simulasi final di paket ini — semuanya harus dibuat dan diuji oleh AI coding.

## Demo yang dibenarkan
- Data historis riset asli yang di-holdout untuk replay prediksi.
- Data input skenario sintetis untuk **simulasi demo**, selalu diberi label dan tidak boleh dipakai sebagai bukti akurasi model.

## Sumber penelitian
Impact of substrate moisture content on growth and development of black soldier fly larvae — dataset publik Mendeley Data: https://data.mendeley.com/datasets/k435zc736t/1
