# Galeri demo terpilih

Buka BUKA_GALERI_TERPILIH.html. Terdapat 8 A1 dari ID eksplisit pengguna dan 8 A2 yang diacak dari 178 kandidat dengan seed 20261107, tanpa filter error/status dan tanpa resampling.

images/ memuat 16 foto asli dengan ukuran native (A2 tetap 4056×3040); thumbnails/ hanya untuk preview. competition_gallery_selection.json adalah manifest kanonis beserta SHA256, provenance dan metode pemilihan.

DEMO_APPROVED hanya berarti pilihan galeri; bukan sertifikasi label, crop, atau prediksi. Tidak ada inferensi/training pada tahap ini. API galeri service baru masih perlu diintegrasikan dan diuji. Full research gallery tetap terpisah dan utuh. Atribusi ada di ATTRIBUTION.txt.

Pembaruan: endpoint curated gallery dan inferensi aktual seluruh16 foto telah diuji secara lokal. A1:2SUCCESS/6PARTIAL; A2:7SUCCESS/1REJECTED (SHORTCUT_SCREEN). Status ini bukan metrik akurasi.
