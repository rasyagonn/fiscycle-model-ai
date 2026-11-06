# Laporan final Water Quality Intelligence MVP v2
Tanggal eksekusi: 4 November 2026. Bahasa laporan: Indonesia. Status: **GO bersyarat untuk historical replay; NO-GO untuk live production.**

## 1. Ringkasan Hasil

Implementasi selesai dan dieksekusi: QA kausal, Isolation Forest research, benchmark multi-horizon, interval residual, Decision Support, inferensi independen dari notebook, replay, manifest dan acceptance tests. Terdapat **7 estimator ML terpilih + 2 konfigurasi persistence fallback** untuk sembilan kombinasi parameter/horizon.

Notebook `notebook/final_water_quality_mvp.ipynb` berhasil top-to-bottom (6 code cells, exit 0). **24 tests passed**. Run pertama menemukan bug replay tanpa date bounds dan satu asumsi fixture recovery; keduanya diperbaiki sebelum run final. Environment memunculkan deprecation warning joblib/NumPy 2.5 (array shape), tidak ada error inferensi; versi dicatat untuk reproduksi.

Audit terukur: **23.905** baris lokal 22 Agustus–28 Oktober 2026, 11 CSV eksternal diinventarisasi, **tidak digunakan training v2**. Unit lokal NTU berdasarkan konfirmasi Product Owner. Timezone kemudian dikonfirmasi sebagai **WIB (`Asia/Jakarta`, UTC+07:00)** pada 5 November 2026; timestamp historis dipertahankan sebagai wall-clock lokal tanpa pergeseran. Seluruh **20 file** raw/riset/model lama memiliki hash sama sebelum/sesudah. Hash CSV lokal: `17924f76484c9a5efe6f127a37a667da113603f8873e32575a6686c5fc7e92b8`.

Perbedaan instruksi/file aktual: AGENTS/skill lama menyebut fase awal dan dua notebook root, sedangkan sudah ada lima notebook dan artefak v1 di .agents/skills/fiscycle-water-ai. Instruksi final pengguna mengizinkan perluasan ini. Sesuai koreksi pengguna, implementasi dan hasil baru disatukan ke `.agents/skills/fiscycle-water-ai/`; notebook final berada di `notebook/`, sedangkan paket v2 berada di `models/mvp_v2/`. Artefak lama tetap utuh. `models/mvp_v2/` di dalam folder water AI khusus paket terpilih sesuai koreksi lokasi terbaru dari pengguna.

## 2. Model A

QA v2 menghasilkan VALID **21.143**, SUSPICIOUS **2.335**, SENSOR_ERROR **416**, STALE **11**. Seluruh **414/414** sentinel suhu -127°C ditandai SENSOR_ERROR. Ini cakupan rule sentinel yang diketahui, **bukan** precision/recall deteksi semua gangguan dunia nyata. Ada 20 reason gap >10 menit; sebagian memiliki status prioritas lebih tinggi. Dua pH dan satu suhu malformed/missing, dengan kemungkinan overlap alasan.

Aturan meliputi malformed/non-finite, sentinel, timestamp dan duplicate secara kausal, batas plausibilitas provisional, clipping, jump dan 20 flatline. Semua non-VALID memutus jendela forecasting. pH di luar 0–14 dan suhu di luar 0–50 bukan lagi klaim batas fisik universal; diperiksa sebagai SUSPICIOUS. Turbidity ≥100 NTU ditinjau sebagai kemungkinan clipping, bukan mustahil secara fisik. Daftar ID, alasan dan angka provisional terdapat di README.

Isolation Forest dilatih pada **12.645** baris train valid dengan 36 fitur, 300 trees, contamination .01. Pada evaluasi akhir **0/3.158 alert**; statistical baseline median/MAD delta menghasilkan **14** indikasi. Validation dan calibration juga nol alert IF. Pada blok train, evaluasi yang menyertakan suspicious rows menghasilkan 252 alert, 125 overlap QA dan 127 indikasi tambahan belum diverifikasi. Denominator train evaluasi 14.357 berbeda dari train fitted 12.645 karena hanya fitted pada VALID.

Riset terdahulu juga nol alert IF akhir, tetapi memakai 12 fitur/split/QA berbeda; tidak membuktikan v2 lebih baik. Statistik harian dan contoh score terendah tersedia di `research/anomaly_daily.csv` serta `anomaly_review.csv`. Tidak ada confirmed incremental finding, precision, recall, atau false-alert rate yang dapat ditetapkan.

**Keputusan:** deterministic QA berfungsi; IF **EXPERIMENTAL_ONLY**, tidak dipaketkan dalam models/mvp_v2/. Estimator riset dipertahankan di `research/isolation_forest_v2.joblib`, dengan opt-in eksplisit untuk review riset. Tidak mengklasifikasikan stress ikan, bahaya air, atau sensor rusak secara pasti.

## 3. Model B

Direct forecasting pH/suhu/NTU pada +30/+60/+120 menit. Benchmark **54 tuning fits** (3 algoritma × 2 konfigurasi × 9 kombinasi), lalu 27 refit keluarga terpilih; grid terbatas. Semua kandidat memakai definisi fitur dan split yang sama per horizon. CatBoost/RF/ExtraTrees tidak diulang karena benchmark terdahulu dipertahankan; ensemble optional tidak dijalankan.

Split kalender: train sebelum **12 Oktober**, validation **12–18 Oktober**, calibration **18–22 Oktober**, evaluasi historis **22–28 Oktober**. Warm-up 61,5 menit dan embargo akhir 121,5 menit berlaku pada setiap split/horizon. Model refit hanya train+validation. Tidak ada calibration target untuk fitting/tuning. Target matched actual timestamp ±90 detik, tie ditolak dan QA/gap memutus segmen.

| Horizon | Train | Validation | Calibration | Historical evaluation | Coverage terhadap seluruh input pada periode evaluasi |
|---|---:|---:|---:|---:|---:|
| 30 menit | 10.863 | 2.697 | 1.844 | 3.144 | 98,81% |
| 60 menit | 10.704 | 2.687 | 1.844 | 3.134 | 98,49% |
| 120 menit | 10.487 | 2.667 | 1.844 | 3.114 | 97,86% |

Denominator coverage evaluasi 3.182 baris dalam rentang origin setelah split warm-up/embargo; numerator juga mensyaratkan target tersedia. Coverage train jauh lebih rendah, sekitar 66–68%, akibat QA dan kontinuitas. Seluruh hitungan/timestamp tepat ada di `research/splits.csv`. Fitur lengkap keseluruhan 18.989 baris. Usable training +30/+60 baru dimulai 5 September, +120 pada 6 September; tidak menyembunyikan penolakan data awal.

**Metrik paket terpilih**, retrospektif. Bias = prediction minus actual. Latency prepared-row dalam ms p50/p95; tanda — berarti persistence tanpa estimator terlatih, bukan latency pipeline nol.

| Parameter | Menit | Algoritma | MAE | RMSE | Bias | Persistence MAE | Perbaikan MAE | Latensi p50/p95 | Kesiapan |
|---|---:|---|---:|---:|---:|---:|---:|---|---|
| pH | 30 | HistGradientBoosting | 0.1057 | 0.1507 | 0.0177 | 0.1233 | 14.25% | 3.04/4.07 | REPLAY GO |
| pH | 60 | XGBoost | 0.1140 | 0.1572 | 0.0198 | 0.1304 | 12.59% | 3.12/4.79 | REPLAY GO |
| pH | 120 | HistGradientBoosting | 0.1177 | 0.1610 | 0.0043 | 0.1419 | 17.02% | 4.75/7.10 | REPLAY GO |
| Suhu (°C) | 30 | Persistence | 0.1744 | 0.2458 | -0.0080 | 0.1744 | 0.00% | — | BASELINE |
| Suhu (°C) | 60 | HistGradientBoosting | 0.2423 | 0.3418 | -0.0522 | 0.2820 | 14.09% | 3.39/4.73 | REPLAY GO |
| Suhu (°C) | 120 | LightGBM | 0.3601 | 0.4943 | -0.1086 | 0.4908 | 26.63% | 1.16/1.61 | REPLAY GO |
| Turbidity (NTU) | 30 | HistGradientBoosting | 2.2201 | 2.8642 | -0.0741 | 2.5639 | 13.41% | 5.39/6.81 | REPLAY GO |
| Turbidity (NTU) | 60 | HistGradientBoosting | 2.3022 | 2.9671 | -0.1091 | 2.6941 | 14.55% | 4.58/6.72 | REPLAY GO |
| Turbidity (NTU) | 120 | Persistence | 2.8046 | 3.6175 | -0.1739 | 2.8046 | 0.00% | — | BASELINE |

Metrik v2 tidak boleh diklaim peningkatan langsung terhadap v1: QA, fitur waktu aktual, strict segmentation, split dan calibration berubah. Hasil v1 pH 0,1002 dan NTU 2,1748 tetap bukti penelitian lama.

## 4. Prediction Uncertainty

Metode: quantile residual absolut kronologis, rank ceil((n+1)×0,90), calibration terpisah **1.844 baris** per kombinasi. Semua interval target coverage **90%**, dihitung atas residual model/baseline yang benar-benar dipakai. Evaluation tidak digunakan memilih quantile.

| Parameter | Menit | Coverage empiris historis | Lebar interval rata-rata | Status |
|---|---:|---:|---:|---|
| pH | 30 | 83.11% | 0.3423 | EXPERIMENTAL_CALIBRATED |
| pH | 60 | 80.86% | 0.3477 | EXPERIMENTAL_CALIBRATED |
| pH | 120 | 82.08% | 0.3795 | EXPERIMENTAL_CALIBRATED |
| Suhu (°C) | 30 | 90.55% | 0.6600 | EXPERIMENTAL_CALIBRATED |
| Suhu (°C) | 60 | 85.64% | 0.8091 | EXPERIMENTAL_CALIBRATED |
| Suhu (°C) | 120 | 81.63% | 1.1548 | EXPERIMENTAL_CALIBRATED |
| Turbidity (NTU) | 30 | 88.26% | 8.3735 | EXPERIMENTAL_CALIBRATED |
| Turbidity (NTU) | 60 | 88.35% | 8.8109 | EXPERIMENTAL_CALIBRATED |
| Turbidity (NTU) | 120 | 90.66% | 11.8000 | EXPERIMENTAL_CALIBRATED |

Semua kasus memenuhi gate demonstrasi minimal 200 calibration rows dan empirical coverage ≥80%; tidak ada yang berstatus UNAVAILABLE pada evaluasi ini. Namun **7/9 interval berada di bawah target 90%**. Undercoverage paling jelas pH +60 (80,86%) dan suhu +120 (81,63%). Interval tetap **eksperimental**, tidak dijamin 90%, dan bukan confidence prediksi tunggal. Pada invalid/kurang history atau metadata interval tidak layak, inferensi mengembalikan null/UNAVAILABLE.

Gate 80% adalah aturan demonstrasi provisional yang dideklarasikan sebelum run, bukan standar ilmiah validasi. Auto-correlation, overlapping horizons dan distribution shift tetap batas metodologi. Tidak ada retuning interval menggunakan periode evaluasi. Tidak ada clipping rentang diam-diam. [Xu & Xie (ICML 2023)](https://proceedings.mlr.press/v202/xu23r.html) membahas ketergantungan temporal untuk conformal inference; implementasi ini split residual sederhana, bukan implementasi algoritma SPCI mereka.

## 5. Decision Support

Engine deterministik dengan rule IDs dan status **PROVISIONAL_ENGINEERING_RULE**:

- C01_INPUT_QA: input bermasalah → periksa sensor/timestamp, tahan forecast.
- C02_UNUSUAL_PATTERN: IF opt-in flag → pola statistik perlu pemeriksaan, bukan bahaya air.
- C03_INTERVAL_UNAVAILABLE: “Informasi belum cukup untuk memberikan rekomendasi yang andal”; “Rentang prediksi belum tersedia.”
- C04_CHANGE_OUTSIDE_RESIDUAL_BAND: nilai kini di luar band → pantau tren dan verifikasi pembacaan berikutnya.
- C05_REVIEWED_THRESHOLD: forecast/band melintasi konfigurasi yang memiliki REVIEWED + reviewer + reference → verifikasi kondisi lapangan.
- C06_INSUFFICIENT_HISTORY: kumpulkan history valid setelah gangguan.

Tidak ada ambang operasional ahli dalam konfigurasi bawaan. Test threshold menggunakan fixture sintetis berlabel, bukan guidance produksi. Output memiliki parameter status, tren numerik, explanation, action, reason dan basis. Missing DO/TAN selalu disclosed; tidak ada dosis, estimasi amonia, diagnosis, atau kontrol hardware.

Contoh aktual pada pH 6,60: forecast +30 sebesar 6,891, rentang 6,720–7,062. Karena current di bawah band, C04 menyarankan memantau perubahan dan memverifikasi pembacaan berikutnya, tidak menyatakan air berbahaya.

Tests mencakup seluruh keenam scenario rule, termasuk review gate untuk threshold. Hasil rekomendasi lapangan belum diverifikasi ahli/operator.

## 6. Historical Replay

Inferensi end-to-end bekerja dari trained models yang di-load terpisah dari training. Origin minimum **22 Oktober 2026**, setelah calibration berakhir; origin sebelumnya ditolak agar tidak menampilkan model dengan informasi masa depan sebagai simulasi out-of-sample.

Run demonstrasi **80 observasi**, **540 forecast**, **321 completed comparisons**, seluruh **321 MATCHED**. Forecast lain belum matang pada akhir replay. Start/stop/resume dan pemilihan interval tersedia. Pembandingan actual menunggu seluruh target tolerance window selesai; QA/gap/tie menghasilkan unavailable. Prefix-only input dan penolakan future rows diuji.

Contoh data lokal aktual:
- Timestamp replay **22 Oktober 2026 05:01:21**, pH **6,60**, suhu **28,22 °C**, turbidity **18,4 NTU**, QA VALID.
- pH +30 target **05:31:21**: HGB menghasilkan **6,891136**, interval **[6,719963; 7,062309]**.
- Observasi baru ketika replay mencapai target: pH **6,73** pada **05:31:20**; error **+0,161136**.
- Nilai actual ini baru masuk evaluasi setelah waktu target; bukan input saat forecast dibuat.

Input/output lengkap ada di `research/replay_input_example.json` dan `replay_output_example.json`; pasangan completed di `replay_comparisons.csv`.

Latency E2E: **p50 101.70 ms**, **p95 111.47 ms**, 40 repetisi, 60 input rows. Mencakup parsing, QA, fitur, sembilan forecast, interval dan Decision Support; load model sekali di luar hot path. RSS proses saat benchmark sekitar 281.5 MiB, bukan peak/model-only. Nilai machine-specific, bukan SLA layanan.

## 7. Application Integration

Gunakan `WaterQualityEngine().infer(payload)` dari `water_quality.py`. Tidak perlu notebook/training saat inference. Input: pond_id, mode historical_replay, clock ISO naive wall-clock WIB, history readings. Output: sensor timestamp/quality, metadata `Asia/Jakarta`/WIB/UTC+07:00, anomaly status, parameter+horizon+target timestamp, point/interval atau unavailable, model ID/version, Decision Support, warnings dan limitations.

Backend dapat menerima response JSON yang ketat tanpa NaN. Future rows dan campuran pond_id pada inferensi ditolak. Frontend tidak membaca joblib. Contoh executable dan kontrak, aturan, panduan **Detail Kolam → Kualitas Air** lengkap di README.md.

UI wajib “Simulasi Data Historis”, timestamp asli, label persistence, status experimental interval, serta interval coverage empiris. Jangan mengarang kurva future di antara tiga horizon. Yang disiapkan adalah **panduan frontend dan modul backend callable**; tidak ada dashboard/HTTP API/full IoT yang dibangun.

## 8. Models Directory

Isi tepat `models/mvp_v2/` di dalam folder water AI pada run final:

| File | Ukuran | Fungsi |
|---|---:|---|
| `manifest.json` | 43.4 KiB | Registry, schema, hash, metrik, provenance, interval calibration dan fallback. |
| `ph_120m_v2.joblib` | 235.9 KiB | Estimator terpilih untuk parameter/horizon sesuai nama file. |
| `ph_30m_v2.joblib` | 170.2 KiB | Estimator terpilih untuk parameter/horizon sesuai nama file. |
| `ph_60m_v2.joblib` | 104.3 KiB | Estimator terpilih untuk parameter/horizon sesuai nama file. |
| `temperature_c_120m_v2.joblib` | 321.8 KiB | Estimator terpilih untuk parameter/horizon sesuai nama file. |
| `temperature_c_60m_v2.joblib` | 172.4 KiB | Estimator terpilih untuk parameter/horizon sesuai nama file. |
| `turbidity_ntu_30m_v2.joblib` | 237.6 KiB | Estimator terpilih untuk parameter/horizon sesuai nama file. |
| `turbidity_ntu_60m_v2.joblib` | 171.5 KiB | Estimator terpilih untuk parameter/horizon sesuai nama file. |

Total paket 1.42 MiB. Tujuh joblib diperlukan untuk tujuh model terpilih. Manifest membawa feature order, versions, SHA256 tiap file, provenance, split, selected metrics, calibrated radius, coverage dan konfigurasi dua persistence. Tidak memerlukan serialized scaler; fitur deterministik dikerjakan modul bersama.

IF/LOF, model v1, kandidat algoritma nonterpilih, dataset, notebook, plots dan hasil intermediate tidak disertakan di models/mvp_v2/. IF berada di research; v1 tetap arsip lama. Dua kandidat HGB yang gagal gate aplikasi (suhu +30 dan turbidity +120) tidak diekspor. Tidak ada stacking.

Daftar lengkap kombinasi algoritma nonterpilih dari benchmark v2: pH +30 XGBoost; pH +30 LightGBM; Suhu (°C) +30 HistGradientBoosting; Suhu (°C) +30 XGBoost; Suhu (°C) +30 LightGBM; Turbidity (NTU) +30 XGBoost; Turbidity (NTU) +30 LightGBM; pH +60 HistGradientBoosting; pH +60 LightGBM; Suhu (°C) +60 XGBoost; Suhu (°C) +60 LightGBM; Turbidity (NTU) +60 XGBoost; Turbidity (NTU) +60 LightGBM; pH +120 XGBoost; pH +120 LightGBM; Suhu (°C) +120 HistGradientBoosting; Suhu (°C) +120 XGBoost; Turbidity (NTU) +120 HistGradientBoosting; Turbidity (NTU) +120 XGBoost; Turbidity (NTU) +120 LightGBM.

## 9. Model Selection

Pemilihan konfigurasi per keluarga hanya validation. Kandidat dengan validation MAE terbaik dipertimbangkan, HGB dipilih jika bedanya ≤2% untuk kesederhanaan. Gate: gain validation ≥10%, ≥2/3 blok positif, historical gain ≥10%, ≥2/3 blok historis positif, model ≤10 MiB, prepared-row p95 ≤100 ms. Hasil historis hanya menerima/menolak kandidat, tidak memilih ulang algoritma yang unggul di test.

HGB memenuhi kompromi akurasi/kompleksitas untuk lima kombinasi, XGBoost untuk pH +60 dan LightGBM untuk suhu +120. Seluruh ML terpilih kecil dan cepat pada hardware ini; latensi end-to-end juga diukur. Detail config, runtime, RSS delta dan temporal stability semua kandidat di `benchmarks.csv`, `trials.csv`, `temporal_blocks.csv`.

Suhu +30: kandidat HGB hanya **3,90%** gain historis, di bawah gate 10%; persistence direkomendasikan. Turbidity +120: HGB **9,38%**, juga gagal; tetap diteliti, aplikasi memakai persistence. Ini bukan klaim baseline lebih akurat; pilihan konservatif karena keuntungan kandidat belum memenuhi kriteria yang dideklarasikan.

Istilah REPLAY GO hanya penerimaan teknis demo historis yang terbatas. Tidak ada bukti baru untuk live production atau biological safety.

## 10. Known Limitations

Satu kolam lokal dengan ID asli belum terverifikasi, tidak ada data independen baru setelah 28 Oktober, dan IoT tidak aktif. Timezone WIB sudah dikonfirmasi, tetapi kontrak v2 masih memakai timestamp naive wall-clock; integrasi lintas sistem perlu memastikan tidak ada konversi ganda. Sensor calibration/conversion/clipping belum terverifikasi walaupun unit NTU sudah dikonfirmasi. Data historis pernah memengaruhi penelitian sebelumnya sehingga bukan untouched final test.

QA engineering thresholds provisional dapat mengecualikan kejadian air nyata; semua non-VALID membuat forecast coverage berkurang dan recovery perlu sekitar 60 menit valid. Fitur v2 tidak kompatibel langsung dengan model v1. IF tidak memiliki label insiden atau bukti incremental value. Interval undercoverage dan dependence belum terselesaikan. DO/TAN tidak ada. Operational thresholds dan hasil rekomendasi belum direview/divalidasi ahli.

Replay minimal dipakai pada segmen terbatas; state history/prediction tersimpan di memori, bukan streaming service yang dioptimalkan untuk retensi panjang. Tidak ada deployment eksternal, API server, frontend lengkap, kontrol hardware atau stacking. Environment harus dipin untuk kompatibilitas joblib; deprecation warning NumPy/joblib dicatat di notebook.

## 11. Next Steps

Bekukan konfigurasi dan paket ini untuk demo replay. Sebelum live production: aktifkan kembali IoT; verifikasi identitas kolam, unit/kalibrasi, dan serialisasi WIB pada seluruh sistem; kumpulkan data baru tanpa tuning pada evaluation period; review alert dan false-alarm load bersama operator; tinjau threshold oleh ahli; lakukan evaluasi prospective lintas kolam, coverage interval serta drift; baru integrasikan ingestion/API, observability, retraining dan fail-safe sesuai hasil.

File baru: `water_quality.py`, `train_validate.py`, `test_water_quality.py`, `notebook/final_water_quality_mvp.ipynb`, `README.md`, `FINAL_REPORT.md`; `research/` memuat hasil aktual, contoh, plot, IF riset dan integritas; `models/mvp_v2/` berisi paket yang dicantumkan di atas. File lama/raw tidak diubah.

**GO:** demo replay yang diberi label jelas, QA, tujuh forecast ML terpilih, dua baseline, interval eksperimental, Decision Support verifikasi. **NO-GO:** live/production claims, IF sebagai detektor gangguan tervalidasi, coverage dijamin, diagnosis biologis atau intervensi otomatis.

