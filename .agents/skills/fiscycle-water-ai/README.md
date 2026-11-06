# Fiscycle Water Quality Intelligence v2

**Simulasi Data Historis.** Modul Python untuk backend, bukan live IoT, layanan API, atau dashboard. Instruksi implementasi final pengguna memperluas batas notebook-only dalam AGENTS.md dan skill lama. Data dan seluruh lima notebook/dua model v1 tetap di `.agents/skills/fiscycle-water-ai/`. Folder ini menyimpan implementasi dan riset baru. Hanya paket aplikasi terpilih berada di `models/mvp_v2/`.

## Menjalankan

Gunakan environment Python yang tercatat di `research/environment.json` (Python 3.13; pandas, numpy, scikit-learn, XGBoost, LightGBM, joblib, threadpoolctl, matplotlib, psutil, pytest, nbformat, nbconvert). Tidak ada instalasi otomatis. Backend tidak membutuhkan XGBoost/LightGBM jika manifest final tidak memilihnya; gunakan versi environment penelitian untuk reproduksi.

```powershell
cd D:\project\Fyscycle\fiscycle-model-ai\.agents\skills\fiscycle-water-ai
python -m nbconvert --to notebook --execute --inplace notebook/final_water_quality_mvp.ipynb --ExecutePreprocessor.timeout=1800
python -m pytest test_water_quality.py -q
```

Notebook menjalankan eksperimen, mengekspor hanya kandidat lolos gate, lalu menjalankan acceptance tests. `train_validate.py` adalah entry point training yang sama. Rerun dapat mengganti output v2 miliknya sendiri; jika models/mvp_v2/ memiliki file di luar paket yang diharapkan, training berhenti tanpa menghapusnya. Jangan mengeksekusi ulang notebook v1 untuk migrasi: beberapa notebook lama menulis artefak v1.

Inferensi tidak menjalankan training dan tidak memerlukan CSV target:

```python
import json
from pathlib import Path
from water_quality import WaterQualityEngine

engine = WaterQualityEngine(models_dir=Path('models/mvp_v2'))  # load sekali per worker
request = json.loads(Path('research/replay_input_example.json').read_text())
response = engine.infer(request)
print(json.dumps(response, ensure_ascii=False, allow_nan=False))
```

File joblib hanya boleh berasal dari paket lokal tepercaya; engine memverifikasi hash file dan urutan fitur sebelum inferensi. Frontend memanggil backend; jangan memuat joblib di browser. Aplikasi FastAPI gabungan dan dashboard pengujian internal sekarang berada di root `app/`. Folder Water Quality ini hanya memiliki engine, artefak, data, notebook, dan bukti evaluasi domain.

## Kontrak input/output

Input wajib: `pond_id` nonkosong, `mode='historical_replay'`, `current_timestamp` ISO naive, `readings` urut kronologis yang masing-masing berisi `timestamp`, `ph`, `temperature_c`, `turbidity_ntu`. Bila row membawa pond_id, harus sama. Model berasal dari satu kolam yang identitas aslinya tidak diketahui; nama `fiscycle_local_pond_unknown` adalah identitas teknis, bukan identifikasi kolam yang telah diverifikasi. Jangan memakai ID berbeda sebagai bukti validasi multi-kolam.

Timezone sudah dikonfirmasi **WIB (`Asia/Jakarta`, UTC+07:00)** pada 5 November 2026. Untuk kompatibilitas model/replay v2, timestamp internal dan input API tetap berupa ISO naive wall-clock lokal; contoh `2026-10-22T03:01:14` dibaca sebagai 03:01:14 WIB dan tidak digeser. Timestamp dengan suffix zona masih ditolak agar tidak terjadi konversi ganda. Nilai berformat satu koma desimal diterima; kombinasi titik+koma ambigu, non-finite, atau nilai hilang menjadi missing. Semua future rows ditolak, bukan disembunyikan. Paket v2 menolak origin sebelum 22 Oktober 2026 karena fitting/kalibrasinya akan memakai informasi yang belum tersedia pada saat itu.

Riwayat harus mencakup sedikitnya sekitar 60 menit valid kontinu; kirim setidaknya 90–180 menit untuk replay. Model menerima 36 fitur dengan urutan `models/mvp_v2/manifest.json`. `water_quality.py` membentuk fitur identik saat training dan inferensi. Tidak ada preprocessing fitted tersembunyi. Semua non-VALID memutus history. Lags dicocokkan ke waktu aktual ±90 detik, tie ditolak, rolling (15/30/60 menit) menggunakan hanya observasi hingga origin. Prediksi direct, tidak rekursif.

Response menyertakan pond, mode, label historis, clock replay, timestamp sensor terakhir, current readings, status/reasons QA, indikasi IF atau unavailable, sembilan entry forecasting, Decision Support, errors/warnings/limitations. Setiap forecast memiliki parameter, unit, horizon, target timestamp, angka atau null, model ID/version/algorithm, readiness, interval status, target coverage, empirical coverage. Forecast origin selalu **timestamp sensor terakhir**, bukan waktu wall clock. Satu interval tidak menyatakan peluang prediksi tunggal benar.

Input invalid/stale atau history kurang → forecast null, `INPUT_UNAVAILABLE`. ML terpilih → `COMPUTED_ML`; baseline → `PERSISTENCE_FALLBACK`. `MVP_REPLAY_APPROVED` adalah hasil gate teknis demo historis, bukan persetujuan ahli atau validasi produksi. Entry persistence dalam manifest adalah konfigurasi baseline beserta residual calibration, bukan file model terlatih.

## Model A dan aturan QA

Prioritas: SENSOR_ERROR > STALE > SUSPICIOUS > VALID. VALID berarti lolos pemeriksaan yang tersedia, bukan bukti air aman atau sensor terkalibrasi.

| Rule ID / reason | Perilaku dan dasar |
|---|---|
| INVALID_TIMESTAMP_OR_TIMEZONE, DUPLICATE_TIMESTAMP, OUT_OF_ORDER_TIMESTAMP | SENSOR_ERROR. Kontrak data; duplicate kedua ditandai saat muncul, tidak mengubah masa lalu. |
| MISSING_OR_MALFORMED_* | SENSOR_ERROR. Pembacaan tidak bisa digunakan. |
| TEMP_SENTINEL_MINUS127 | SENSOR_ERROR. Sentinel yang diketahui dari audit lokal. |
| TEMPERATURE_BELOW_ABSOLUTE_ZERO, NEGATIVE_TURBIDITY | SENSOR_ERROR. Nilai tidak bermakna untuk kontrak pengukuran ini. |
| PH_OUTSIDE_PROVISIONAL_RANGE (0–14), TEMP_OUTSIDE_PROVISIONAL_RANGE (0–50 °C) | SUSPICIOUS; kebijakan plausibilitas sementara, bukan spesifikasi sensor terverifikasi, batas fisik universal, atau ambang biologis. |
| TURBIDITY_CLIPPING_REVIEW (0 atau ≥100 NTU) | SUSPICIOUS berdasarkan pola clipping historis; nilai ≥100 NTU tidak dianggap secara universal mustahil. |
| FLATLINE_20_* | SUSPICIOUS setelah 20 pembacaan identik berurutan. Tidak membuktikan sensor mati. |
| JUMP_REVIEW_* | SUSPICIOUS bila perubahan >1 pH / >3 °C / >30 NTU dalam ≤10 menit. Aturan teknik provisional, perlu review lapangan. |
| GAP_GT_10_MIN, NO_RECENT_OBSERVATION, NO_READINGS | STALE saat pascagap atau tidak ada observasi segar. Freshness menggunakan clock replay eksplisit. |

Jika perangkat mati sehari, sistem menahan forecast; ketika kembali, baris pascagap ditandai STALE lalu history valid dikumpulkan ulang. Tidak ada forward-fill melewati gangguan. Perubahan ke QA v2 menyebabkan hasil dan coverage berbeda dari v1.

IF 300 trees, contamination 0.01, seed 42, fitted hanya train valid; memakai 36 fitur kausal. Statistik pembanding menggunakan median/MAD delta train. Lihat `research/model_a_results.json`, `anomaly_daily.csv`, `anomaly_review.csv`. Semua alert belum dilabeli independen. Precision, recall, false alarms/day **tidak diketahui**. Angka contamination bukan prevalensi gangguan sesungguhnya.

IF tidak masuk models/. Untuk review riset eksplisit, gunakan `WaterQualityEngine(experimental_anomaly_path='research/isolation_forest_v2.joblib')`. Output berlabel EXPERIMENTAL_RESEARCH_OPT_IN; QA tetap menentukan kelayakan forecast. Jalur ini tidak menjadikan IF komponen aplikasi yang telah lolos validasi.

## Seleksi dan uncertainty

Protokol, grid, split, embargo dan gate lengkap berada di `research/protocol.json`. Model B membandingkan HGB/XGBoost/LightGBM, dua konfigurasi unik masing-masing, sembilan parameter-horizon. CatBoost/RF/ExtraTrees sudah ada di benchmark +30 lama; tidak diulang. Ensemble/stacking opsional tidak dijalankan.

Selection hanya memakai validation. HGB diprioritaskan bila MAE ≤2% dari kandidat terbaik. Gain ≥10%, stability ≥2/3 blok, ukuran ≤10 MiB, latency prepared-row p95 ≤100 ms adalah kriteria engineering demo. Kandidat gagal gate historis → persistence; tidak mengambil pemenang historis lain. Dengan data yang pernah diteliti, gate ini bersifat retrospektif dan tidak membuktikan generalisasi.

Refit train+validation, tanpa calibration. Calibration 18–22 Oktober untuk setiap model/baseline terpilih, evaluation sejak 22 Oktober. Quantile absolut residual order ceil((n+1)×0.90); minimum 200 calibration rows. Coverage historis <80% menonaktifkan interval tanpa retuning. Output menyediakan angka coverage/width hasil pengukuran; tidak menjamin coverage 90% pada data temporal baru. Interval tidak diclip ke batas QA agar coverage tidak berubah diam-diam.

`research/benchmarks.csv` memuat 27 kandidat final family, `trials.csv` 54 tuning runs, `temporal_blocks.csv` stabilitas, `selected_summary.csv` sembilan konfigurasi aplikasi, `splits.csv` denominator coverage. Memory yang dilaporkan adalah perubahan RSS proses saat refit, bukan peak/ukuran model individual. Latency measured machine-specific, model load dikecualikan dari hot-path E2E; parsing, QA, fitur, sembilan forecast, interval dan Decision Support disertakan.

## Decision Support

Semua aturan bawaan adalah **PROVISIONAL_ENGINEERING_RULE**, berbasis perilaku sistem dan instruksi produk, belum review ahli akuakultur. Tidak ada universal biological threshold, rekomendasi dosis, kontrol aerator, feeding otomatis, diagnosis penyakit, atau estimasi amonia.

| ID | Kondisi | Penjelasan / tindakan |
|---|---|---|
| C01_INPUT_QA | Input non-VALID | Periksa sensor, timestamp dan kelengkapan; forecast ditahan. |
| C02_UNUSUAL_PATTERN | IF opt-in flag | Pola statistik tidak biasa; verifikasi, bukan diagnosis. |
| C03_INTERVAL_UNAVAILABLE | Forecast ada, interval tidak tersedia | Informasi belum cukup; tampilkan “Rentang prediksi belum tersedia.” |
| C04_CHANGE_OUTSIDE_RESIDUAL_BAND | Nilai kini di luar interval forecast | Pantau perubahan dan verifikasi pembacaan berikutnya; bukan danger threshold. |
| C05_REVIEWED_THRESHOLD | Forecast/band melintasi batas yang punya status REVIEWED, reviewer dan reference | Verifikasi kondisi lapangan. Default tidak memiliki threshold. Backend harus membatasi siapa yang boleh menetapkan konfigurasi ini. |
| C06_INSUFFICIENT_HISTORY | Tidak ada forecast eligible | Kumpulkan history valid setelah gangguan. |

`decision_support.trends` menyatakan selisih numerik dan arah per horizon. `parameter_status` tidak pernah menyatakan kolam biologis aman. Field recommendations memiliki reason dan rule_id, insights memiliki basis. Konfigurasi contoh synthetic threshold hanya terdapat dalam tests, bukan konfigurasi aplikasi.

## Replay dan panduan frontend

```python
from water_quality import HistoricalReplay, load_local
replay = HistoricalReplay(engine, load_local(), start='2026-10-23', end='2026-10-23T05:00:00')
replay.start()
first = replay.next()   # warm-up: belum tentu ada forecast
replay.stop()          # cursor tetap; start() melanjutkan
```

Replay mengekspos hanya prefix history. actual dicocokkan setelah seluruh jendela target ±90 detik lewat; tie atau QA/gap sepanjang origin–target → unavailable. Match ini tidak mengubah prediksi terdahulu. Prediction yang belum jatuh tempo tetap pending. Pilih segmen kontinu tanggal ≥22 Oktober; perubahan kecepatan dapat dilakukan scheduler UI pemanggil `next()`, tidak menambah timestamp palsu. Versi minimal tidak memakai thread streaming atau infrastruktur IoT.

Integrasi **Detail Kolam → Kualitas Air**:

- Banner tetap “Simulasi Data Historis — IoT belum aktif”; tampilkan original timestamp, jangan gunakan tanggal November sebagai waktu pengukuran Oktober.
- Monitoring: pH, °C, NTU, timestamp, QA dan reasons. Indikasi statistik ditampilkan terpisah dari input error.
- Pilihan horizon 30 menit, 1 jam, 2 jam; tampilkan hanya response aktual backend. Beri label persistence bila baseline.
- Grafik history, tiga titik forecast pada waktu target (tidak mengarang kurva halus), band hanya jika interval tersedia, dan actual-vs-prediction dari completed comparisons.
- Tampilkan target coverage 90% sebagai sasaran interval, empirical coverage sebagai hasil retrospektif, bukan confidence satu prediksi.
- Model version di detail teknis; tampilkan insight, alasan, tindakan verifikasi, parameter, basis rule dan informasi yang belum tersedia.
- Error/null/UNAVAILABLE ditampilkan apa adanya; jangan mengganti dengan angka contoh atau angka model v1.

Tidak ada frontend/dashboard yang dibangun di repository model ini; file ini adalah panduan integrasi yang diminta.

## Batas dan rujukan

Satu kolam, IoT nonaktif, tanpa data independen setelah 28 Oktober; timezone WIB sudah dikonfirmasi; NTU sudah dikonfirmasi tetapi kalibrasi/conversion/clipping belum. Tidak ada DO/TAN, ground truth anomali, atau hasil rekomendasi operasional yang diverifikasi. Perlu data baru, audit sensor, expert-reviewed thresholds dan validasi prospective sebelum live production.

- [IsolationForest, dokumentasi scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html): arti score/flag, bukan label kausal gangguan.
- [Xu & Xie, ICML 2023](https://proceedings.mlr.press/v202/xu23r.html): uncertainty time series memerlukan perhatian terhadap ketergantungan waktu. V2 ini memakai residual split sederhana, **bukan** implementasi SPCI dari paper.

Tidak ada ambang biologis yang diklaim bersumber dari dua rujukan metodologis tersebut. Laporan hasil aktual: `FINAL_REPORT.md`; seluruh tabel dapat diaudit dari notebook dan research/.
