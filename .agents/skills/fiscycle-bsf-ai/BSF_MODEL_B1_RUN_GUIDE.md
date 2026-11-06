# Fiscycle Smart BSF Model B1 — Run Guide

Status: `RESEARCH_PROTOTYPE` / `NOT_FIELD_VALIDATED`.

Notebook utama: `bsf_model_b1_growth_forecasting.ipynb`.

Jalankan dari root workspace `fiscycle-model-ai`:

```powershell
python -m jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=600 .agents/skills/fiscycle-bsf-ai/bsf_model_b1_growth_forecasting.ipynb
```

Atau buka notebook tersebut di Jupyter dan jalankan **Restart Kernel and Run All Cells**. Notebook membaca workbook dan CSV dari `data/` dan menulis laporan serta demo ke `hasil/`.

Mode default `RUN_TRAINING = False` memakai estimator final dan hasil pembandingan yang sudah tersimpan. Model terpilih diperiksa kembali pada holdout. Empat fitting fold development diperlukan sekali untuk merekonstruksi residual kalibrasi; eksekusi berikutnya memakai cache residual dengan hash yang cocok. Tidak ada tuning ulang atau fitting model final pada mode ini. Jangan aktifkan ulang blok training arsip untuk pekerjaan validasi ini.

Untuk menjalankan hanya validasi dari root workspace:

```powershell
python -B .agents/skills/fiscycle-bsf-ai/bsf_b1_validation.py
python -B .agents/skills/fiscycle-bsf-ai/test_bsf_b1_inference.py
```

Fungsi yang dipakai integrasi ada di `bsf_b1_inference.py`; alur audit/kalibrasi ada di `bsf_b1_validation.py`. Keduanya sengaja ditempatkan sebagai modul ringan di root BSF agar dapat digunakan ulang tanpa notebook atau scaffold API. Kontrak lengkap ada di `hasil/v2/MODEL_B1_INTEGRATION_CONTRACT.md`. Mulai membaca hasil tahap kedua dari `hasil/v2/bsf_model_b1_validation_report.md` dan grafik di sebelahnya.

Dependensi yang dipakai:

- Python 3.13
- pandas, numpy, openpyxl
- scikit-learn, joblib
- matplotlib
- Jupyter/nbformat/nbclient untuk eksekusi notebook

Input read-only di folder `data/`:

- `Impact of substrate moisture content on BSF larvae Data.xlsx`
- `Fiscycle_BSF_SubstrateMoisture_LongForm_400rows.csv`

Output notebook di folder `hasil/`:

- `bsf_model_b1_evaluation_summary.json`
- `bsf_model_b1_historical_replay.csv`
- `bsf_model_b1_synthetic_scenarios.csv`
- `bsf_model_b1_results_comparison.png`
- `bsf_model_b1_historical_replay_visual.png`
- estimator dan metadata hanya bila ML terpilih secara objektif pada validasi dan mengalahkan persistence

Output validasi tahap kedua dikelompokkan di `hasil/v2/`:

- Di root `v2/` hanya tiga dokumen utama: laporan validasi, visual validasi, dan kontrak integrasi.
- `detail/`: tabel audit/error, tiga contoh replay, ringkasan JSON, dan laporan penurunan berat.
- `internal/`: residual development, manifest fold, coverage per replikasi, dan kalibrasi uncertainty.

Model dan metadata tahap pertama tetap di `hasil/`. `B1Predictor()` otomatis membaca kalibrasi dari `hasil/v2/internal/bsf_model_b1_uncertainty.json`. Folder sumber dan notebook tetap di tempat semula.

Folder `models/` adalah bundle runtime datar berisi tepat empat file untuk dipindahkan ke backend MVP. Fungsi inference di dalam bundle otomatis memuat tiga artefak yang berada di folder yang sama.

Skenario sintetis tetap di file tersendiri dan tidak digunakan dalam metrik atau kalibrasi. Estimator final, metadata training, dan dua input sumber dipertahankan serta diperiksa hash-nya. Hasil uncertainty hanya terkait versi estimator yang cocok.

Data berasal dari eksperimen publik Mendeley Data versi 1, DOI `10.17632/k435zc736t.1`, lisensi CC BY 4.0. Tidak ada data sensor atau validasi lapangan Fiscycle dalam eksperimen ini.
