# Model A — finalisasi working dataset dan readiness

Status: RESEARCH_PROTOTYPE / NOT_FIELD_VALIDATED. Tanggal kerja 5 November 2026 WIB. Keputusan saat paket dibuat: **NO-GO untuk training image A1/A2**, karena belum ada keputusan review manusia. Persiapan dan alat review tersedia. Tidak ada model yang dilatih, termasuk baseline.

## Integritas dan provenance

Sumber raw, manifest dan checksum preparation v1, artefak QA v1 serta Model B1 diverifikasi. Keanggotaan train/validation/test tidak diubah. Semua keluaran baru berada pada `hasil/model_a_finalization_v1`; kode pembangun berada di domain BSF yang sama. `input_integrity.json` merekam verifikasi penuh raw; `PACKAGE_RECEIPT.json` mengikat kode dan artefak paket. Verifier dapat mengulang checksum seluruh raw termasuk ZIP.

Data publik BSF sumber Zenodo record 13359376, versi 1, Quentin Geissmann, 27 Agustus 2024, CC-BY-4.0; provenance/attribution sebelumnya tetap berlaku. Tidak ada gambar kamera operasional Fiscycle. Tidak ada klaim generalisasi lapangan atau total biomassa batch.

## A1: kebijakan dan hasil terukur

Pemetaan source 0 → target 0 dan source 1 → target 0, nama `visible_bsf_larva`, mengikuti keputusan pengguna. Ini keputusan rekayasa, **bukan bukti kesamaan biologis**. Audit trail mempertahankan 4.713 instance source 0 dan 1.899 source 1. Salinan mapping berisi 321 gambar dan 6.612 instance; seluruh koordinat sumber tetap identik. Polygon per larva tidak digabung.

Reservasi tetap 204 train, 61 validation, 46 test, 8 quarantine dan 2 excluded. Dua excluded berisi tray terisi tetapi label kosong; tidak dijadikan negative image. Tidak ada gambar yang human-approved pada train/validation/test.

Proposal terpisah memuat 17 penghapusan **kandidat** instance duplikat (raster IoU ≥ 0,90); overlap tinggi saja tidak membuktikan satu larva. Untuk 6.595 instance tersisa, penulisan titik penutup yang berulang dibersihkan. Pembersihan titik tidak mengubah kontur/luas; itu normalisasi serialisasi, bukan penemuan kesalahan biologis. Sumber dan mapped label tetap menyimpan titik asli. Semua proposal lolos pemeriksaan geometri dasar setelah normalisasi; itu tidak membuktikan kelengkapan anotasi.

Kebijakan mask: hanya bagian terlihat. Batas minimum teknis 16 piksel² native dan sisi bbox pendek 3 piksel, diterapkan konsisten pada penerimaan; ini bukan estimasi ukuran fisik atau persentase tubuh terlihat. Bagian invisible tidak bisa dipakai sebagai denominator. Objek kecil/ambigu menyebabkan hold seluruh gambar, bukan dihapus lalu diam-diam dianggap background. Fragment visible terpisah dari satu larva ditahan jika format polygon tunggal tidak bisa merepresentasikannya tanpa jembatan palsu. Truncation A1 hanya boleh diterima bila identitas dan kontur yang terlihat jelas, disahkan manusia.

QA visual terdahulu memeriksa 36 gambar: 26 perlu correction, 3 adjudication, 5 tanpa cacat mencolok saat triage, 2 tetap excluded; 285 belum diperiksa visual satu per satu. Pemeriksaan baru meliputi seluruh struktur/lineage dan proposal, bukan sertifikasi kelengkapan 321 gambar. Larva terlewat, batas occlusion dan instance ambigu tetap membutuhkan pemeriksaan manusia setiap gambar. UI menyediakan foto asli, source class, proposal, highlight perubahan, editing titik, serta keputusan yang terikat hash. Daftar unresolved tetap memuat seluruh 321 gambar; hard hold sumber tidak dapat dilepas di versi ini.

Validation/test belum memiliki label evaluasi yang disahkan lengkap. **A1 validation hanya satu primary split group**; 61 gambar bukan 61 replikasi biologis independen. Jangan gunakan test overlay untuk memilih arsitektur atau preprocessing; kegiatan test di UI hanya perbaikan ground truth yang konsisten dengan kebijakan.

## A2: eksperimen crop development

Metode v2 memakai ranking connected components dari piksel: batas warna/saturasi, area, fill, aspect dan penalti menyentuh tepi. Margin dihitung dari komponen, crop dari source penuh, lalu letterbox 512. Tidak ada central crop, distortion, rekonstruksi tubuh, inpainting, atau pengubahan sumber. Weight/Length/Width/Sex/ID/batch/filename tidak masuk fungsi lokalizer. ID hanya dipakai untuk menghubungkan hasil dan hasil triage, bukan menentukan koordinat.

Perbandingan memakai **43 ID development yang sama** dengan QA sebelumnya (35 representatif + 8 stress cases), bukan sampel acak dan bukan estimasi akurasi populasi. Tidak ada test yang diproses untuk seleksi metode. Agent memeriksa 11 lembar perbandingan dan crop failure individual; hasil ini bukan human approval.

Hasil v2 pada 43 gambar:

- 24 tanpa cacat jelas pada triage, tetap belum accepted.
- 12 mengandung ruler (107, 723, 724, 773, 815, 907, 908, 954, 1000, 1002, 1041, 1080).
- 1 source truncated (253), juga masih memperlihatkan ruler. Total kasus ruler terlihat termasuk ini: 13.
- 1 wrong-object (1460: noda), kegagalan baru dibanding v1 yang mencakup larva dan ID.
- 1 crop memotong tubuh (18), kegagalan baru dibanding v1.
- 4 background perlu review (62, 1372, 1461, 1474).

Perbaikan terbatas: 773 kini memilih larva, tetapi masih mengandung ruler; 107 menghilangkan tulisan ID/sex tetapi mempertahankan garis ukur; 1474 menghilangkan ID, masih ada debris. Jumlah wrong-object tetap 1/43 karena kasus baru 1460. Tidak dapat menyimpulkan v2 lebih baik secara menyeluruh. Screen garis/ink juga memiliki false alarm pada larva dan false negative pada kasus 107/1460; screen bukan sertifikat bebas shortcut.

V2 diekspansi sebagai **proposal untuk review** pada 1.114 development (924 train, 190 validation), dengan konfigurasi dikunci dari eksperimen ini. Terdapat 1.102 kandidat crop dan 12 abstain/no-candidate. Status: 569 pending human review dan 545 hold (termasuk 28 hard hold); 526 flag shortcut otomatis dan 2 flag source-edge. Flag otomatis bukan confirmed failure. 1.071 gambar di luar subset 43 belum ditriage visual. Kasus gagal yang terlihat dikunci hold. Tidak ada 316 quarantine yang dipakai, dan 178 test tidak dibuat crop. Daftar seluruh 1.608 reservasi ada dalam eligibility ledger.

Rekomendasi: gunakan subset kecil dengan crop yang benar-benar diterima manusia; jangan menganggap semua kandidat layak. Untuk kasus ruler dekat badan yang tak bisa dibersihkan dengan crop, hold. Metode lanjutan atau manual ROI memerlukan working version baru dan review ulang, bukan memodifikasi crop di paket ini.

Coverage tersedia per split/batch dengan count, minimum, maximum, mean dan median **measured weight** untuk development penuh, screen-pending, hold, dan human-approved. Populasi approved masih nol di semua batch: penurunan coverage eligible 100% saat ini, bukan penghapusan raw. Screen-pending bukan distribusi training final. Seleksi crop dapat menghilangkan batch/kisaran berat tertentu; ukur ulang coverage setelah setiap snapshot review.

## Baseline dan risiko leakage

Mean-weight dan Length → measured Weight: 924 train / 190 validation. Length + valid Width: 905 train / 190 validation. Width invalid tidak diisi secara diam-diam. Units Weight g, Length mm, Width belum terkonfirmasi. Wet/dry protocol belum diketahui; image pixels bukan millimeter. Image-to-weight belum punya accepted population.

Bandingkan mean vs Length pada populasi lengkap, lalu ketiga baseline pada ID valid-width yang persis sama. Untuk image comparison, subset setiap baseline ke ID crop accepted yang sama; bila membandingkan ke Length+Width gunakan intersection accepted+valid-width. Fit mean/scaler/regressor pada train saja. Laporkan MAE, RMSE dan bias dalam g, coverage dan per-batch error; jangan membandingkan model yang dievaluasi pada baris berbeda.

**A2 final test hanya satu primary split group** (B011); train punya tiga dan validation dua. Count gambar tidak sama dengan sampel biologis independen. Parentage, batch, sesi, near-duplicate dan desain foto terkontrol masih membatasi generalisasi. Quarantine tetap berlaku. Penggunaan validation pada penelitian crop ini harus diungkap sebagai development reuse.

Riwayat paparan: pada QA sebelumnya, satu contact sheet lama sempat menampilkan ID 1102 (sekarang test), plus beberapa quarantine. Paparan sudah dicatat; bukan evaluasi model dan tidak dipakai menentukan threshold v2. Jangan mengklaim seluruh test sepenuhnya belum pernah dilihat. Tahap finalisasi ini tidak memproses test A2 atau menghitung hasil final test.

## Gate dan eksperimen berikutnya

Validasi implementasi: 10 tes lulus untuk mapping geometry seluruh 6.612 instance, original split, gate keputusan, geometri invalid, crop berubah, dan freeze/import pada fixture sintetis di folder temporer. Tes browser Chrome 156 lulus untuk rendering lokal A1/A2, hard hold, filter kosong, penolakan reviewer/checklist kosong, editing/undo dan pembatalan keputusan setelah edit. Approval sintetis hanya dibuat pada fixture terpisah; tidak ada approval data asli yang ditulis. `verify` memeriksa receipt paket dan kembali memeriksa raw, frozen preparation/QA, serta B1.

Yang masih harus disahkan: kelengkapan/batas/instance seluruh label A1, tiap proposal duplikat, ambiguity dan truncation; tiap crop A2 beserta keutuhan tubuh, kedua ujung dan absennya shortcut. Persetujuan kebijakan mapping sudah ada dan tidak perlu diminta ulang. Belum ada keputusan per gambar, sehingga tidak ada training-ready FREEZE yang dibuat.

Dataset morphometric siap untuk eksperimen terkontrol berikutnya, tetapi fitting tidak dijalankan dalam tugas ini. Eksperimen pertama yang disarankan setelah instruksi training terpisah: train-only mean-weight vs ordinary least squares Length → measured_weight_g; seed 42 untuk prosedur yang memerlukannya, frozen 924/190 split, tanpa tuning pada test. Bandingkan Length+valid Width sebagai analisis kedua pada 905/190 matched IDs. Laporkan MAE/RMSE/bias/coverage dan error per group. Kriteria manfaat minimum yang diusulkan: MAE validation Length lebih rendah daripada mean pada ID sama, tanpa klaim signifikansi dari hanya dua group; bila tidak, pertahankan mean sebagai baseline terpilih. Bekukan spesifikasi dan keputusan sebelum evaluasi final test di tugas lain.

A1/A2 neural training menunggu accepted train dan accepted validation yang cukup untuk tujuan eksperimen, audit coverage per group, serta instruksi training terpisah. Setelah approval, importer membuat snapshot berhash, annotation/crop version, reviewer/waktu, keputusan, lineage dan original split. Test tetap reserved dan tidak menjadi training. Tidak ada pemenuhan gate melalui approval agent atau checkbox otomatis.
