# Deploy manual ke Azure — mulai dari image

Status: login Azure lokal telah berhasil, subscription Azure for Students Enabled,
spending limit On. Belum ada resource/image Azure atau URL API yang dibuat.
Konfigurasi akun dan token lokal berada di cache yang diabaikan Git.

## Tahap 1 — build dan uji image di GitHub

Tidak perlu Docker di laptop dan tidak memakai ACR Tasks. Workflow manual di
`.github/workflows/build-ai-service.yml` membangun Dockerfile yang ada, menjalankan
tes container, lalu memublikasikan image ke GitHub Container Registry (GHCR).
Workflow tidak menjalankan training dan tidak membuat resource Azure.

Dari root repository:

```powershell
git add .github/workflows/build-ai-service.yml ai-service/tools/verify_container.py ai-service/deploy/azure/README.md
git commit -m "Add manual AI container build for Azure"
git push origin main
```

Di GitHub: **Actions → Build AI Service untuk Azure → Run workflow → main → Run workflow**.
Jika Actions meminta pengaktifan workflow, aktifkan untuk repository sendiri.
Jika izin publish package ditolak, periksa Settings → Actions → General → Workflow
permissions dan kebijakan akun/organisasi. Jangan memasukkan token ke chat atau kode.

Tunggu workflow hijau. Buka Summary untuk alamat image dengan tag commit SHA.
Periksa di profil GitHub → Packages bahwa package `fiscycle-ai-service` tetap **PRIVATE**.
Jangan mengubah visibility menjadi public untuk mengatasi kesalahan autentikasi.

Pengujian Linux/Docker belum dijalankan di laptop ini karena Docker Engine tidak
tersedia. YAML dan kode helper hanya diperiksa statis sebelum commit. Build dan
pengujian nyata baru dibuktikan oleh hasil workflow, bukan keberadaan file ini.
Data Water privat tidak diunggah: dua tes pytest dan dua pemeriksaan HTTP terkait
fixture privat di-skip secara eksplisit. Semua pemeriksaan lain harus lulus sebelum push image.

## Tahap 2 — siapkan Azure Container Apps

Lanjutkan setelah image berhasil dibuat. Rencana awal: Consumption, region
Southeast Asia (diizinkan pada subscription yang diperiksa), 2 vCPU/4 GiB,
min replicas 0, max replicas 1, target port 8000, HTTPS dan service token.
Pilihan region tetap perlu diperiksa ulang ketika deploy.

Azure mendukung image GHCR private. Untuk pull, buat GitHub PAT **classic** dengan
scope `read:packages` dan simpan sebagai credential registry di Azure; jangan kirim
di chat atau commit. Token ini terpisah dari `FISCYCLE_AI_SERVICE_TOKEN` milik API.
Pengeluaran Azure perlu disetujui sebelum membuat resource. Spending limit kredit
bukan batas anggaran kecil yang otomatis menghentikan resource.

GHCR saat pemeriksaan dokumentasi masih membebaskan biaya storage/bandwidth image;
kuota/biaya GitHub Actions bergantung pada jenis akun dan repository. Azure Container
Apps memiliki free grant tetapi bukan layanan gratis tanpa batas. Tarif dan jatah
gratis harus diperiksa sebelum provisioning; jangan mengubah subscription menjadi
Pay-As-You-Go untuk melewati batas kredit.

## Tahap 3 — verifikasi API sebelum handover

Sesudah deployment: uji `/health`, empat model, inferensi nyata, autentikasi,
galeri, DSS dan replay. Jangan membagikan URL sebagai layanan siap sebelum tes lulus.
Replay Water memerlukan persetujuan dan pemasangan data privat di cloud secara terpisah.
Tanpa seed, endpoint replay Water 503; inferensi dari request valid tetap tersedia.

Scale-to-zero/restart mengakhiri sesi replay. Riwayat SQLite pada filesystem
container sementara juga dapat hilang; backend produk harus menyimpan business
history sendiri. Jangan mengklaim persistensi cloud sebelum storage diuji.
DSS BSF saat ini adalah aturan verifikasi teknis manual, belum aturan budidaya
berbasis paper/ahli yang tervalidasi. Semua batas riset tetap berlaku.

## Rujukan resmi

- [GHCR dan autentikasi](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [Biaya GitHub Packages/GHCR](https://docs.github.com/en/billing/concepts/product-billing/github-packages)
- [Azure Container Apps dengan GHCR](https://learn.microsoft.com/en-us/azure/container-apps/github-actions)
- [Billing Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/billing)
- [Batas ACR Tasks pada kredit gratis](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-tasks-overview)
