# Model A finalization v1 — cara review

RESEARCH_PROTOTYPE · NOT_FIELD_VALIDATED. Paket ini berisi proposal, bukan dataset training yang telah disahkan.

1. Buka `review.html` langsung di Chrome/Edge. Semua gambar berada lokal; tidak ada server/API atau upload.
2. Isi nama reviewer. Pilih A1/A2 dan split. A1 dimulai dari urutan prioritas QA (test, validation, lalu risiko train); pemeriksaan test hanya untuk kelengkapan label.
3. A1: bandingkan foto, anotasi asli, proposal dan perubahan. Pilih instance untuk menggeser titik; tambah polygon hanya untuk larva yang jelas terlihat. Jangan menghubungkan mask melewati occluder. Jika tidak bisa menetapkan instance/batas, pilih Needs revision dan tulis alasannya.
4. A2: pastikan objek benar, tubuh sumber lengkap, kedua ujung tetap ada, tidak ada ID/sex/penggaris, dan background tidak menjadi shortcut. Crop yang jelas salah dikunci HOLD; perubahan crop memerlukan proposal versi baru. Crop 512 berasal dari gambar penuh tanpa mengubah rasio. Context 1014 hanya untuk review; bila detail tidak pasti, jangan approve.
5. Centang setiap pemeriksaan setelah benar-benar memeriksanya, lalu Approve/Reject/Needs revision. Simpan keputusan **sebelum pindah gambar**; perubahan tanpa keputusan dapat hilang saat navigasi. Perubahan setelah keputusan membatalkan keputusan lama untuk gambar itu.
6. Unduh keputusan JSON. Browser biasanya menaruhnya di Downloads. Restore JSON tersedia untuk melanjutkan review. Nama reviewer dan waktu adalah audit log yang dinyatakan reviewer, bukan tanda tangan kriptografis.
7. Dari root repository, impor file hasil manusia:

```powershell
python -B .agents/skills/fiscycle-bsf-ai/finalize_model_a.py import-reviews "C:/Users/ASUS/Downloads/model_a_human_decisions.json"
```

Importer menolak checksum/proposal/split yang berubah, checklist belum lengkap, polygon invalid/terlalu kecil, dan hard hold. Approval di browser masih keputusan sementara sampai importer lolos. Jangan mengubah JSON untuk meloloskan kasus yang ditahan.

Setiap impor menghasilkan folder append-only `review_snapshots/<hash-json>/`. Hanya approval sah yang masuk `approved_working_manifest.csv`; `FREEZE.json` dibuat hanya bila ada subset accepted. Ekspor semua keputusan terbaru bila ingin snapshot kumulatif. Snapshot lama tidak diubah; tidak ada penggabungan diam-diam. Semua keputusan non-approve ada di `decisions_manifest.csv`; semua gambar tanpa keputusan tetap pending di paket asal.

Verifikasi dan uji:

```powershell
python -B .agents/skills/fiscycle-bsf-ai/finalize_model_a.py verify
python -B .agents/skills/fiscycle-bsf-ai/test_model_a_finalization.py
```

Reproduksi pembangunan: `prepare` (mapping + subset 43), `expand` (1.114 development), `package` (UI/laporan/receipt). Perintah pembangunan menolak paket yang sudah diberi receipt. Untuk percobaan baru, buat versi output baru dan catat perubahan konfigurasi; jangan menghapus receipt untuk menimpa versi ini. Script Python berada dua direktori di atas folder ini.

File utama:

- `annotation_policy.json`, `class_mapping.json`: keputusan target dan eligibility.
- `a1_mapped_labels/`: semua 6.612 instance, geometry dan keanggotaan asli dipertahankan; class diganti 0.
- `a1_proposed_labels/`, `a1_proposed_corrections.csv`: proposal terpisah, belum accepted.
- `a1_instance_lineage.csv`, `a1_working_manifest.csv`, `a1_unresolved_review_queue.csv`: jejak kelas asli, hash, status dan split.
- `a2_candidate_crops/`, `a2_context/`, `a2_comparison/`: proposal dan visual development, bukan test.
- `a2_working_manifest.csv`, `a2_eligibility_ledger.csv`: kandidat dan semua reservasi, termasuk test yang tidak diproses.
- `a2_held_excluded_or_reserved.csv`, `a2_visual_comparison.csv`: alasan hold dan perbandingan 43 kasus.
- `a2_coverage_by_batch_weight.csv`, `a2_baseline_population.csv`, `baseline_readiness.json`: coverage dan populasi baseline; metadata tidak masuk algoritme crop.
- `readiness_summary.json`, `FINALIZATION_REPORT.md`: angka hasil dan batas klaim.
- `PACKAGE_RECEIPT.json`: checksum paket review; **bukan** freeze training-ready.

Tidak ada model yang dilatih dan tidak ada A1/A2 yang dapat dianggap human-approved hanya karena ada di folder ini.
