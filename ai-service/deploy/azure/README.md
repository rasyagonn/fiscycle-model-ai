# Deployment Azure Fiscycle AI Service

Runtime tetap `ai-service/`; model dan preprocessing A2 v3 tidak diubah.

## Jalur deployment aktif

1. Push perubahan runtime/workflow ke `main` atau jalankan workflow manual **Build AI Service untuk Azure**.
2. GitHub membangun image Linux, menjalankan tiga tes retry startup, lalu tes container dan inferensi nyata.
3. Setelah lulus, GitHub login Azure melalui OIDC dan push ke ACR privat
   `ca9edb09a3d8acr.azurecr.io/fiscycle-ai-service:<commit-SHA>`.
4. Operator deploy image berdasarkan **digest** ke Container Apps dan menjalankan pemeriksaan HTTP.
   Push kode saja belum mengganti container produksi.

GitHub memakai identitas `fiscycle-github-build`, dengan AcrPush hanya pada registry ini.
Federasi terikat pada repository pemilik dan branch main; subject aktual GitHub menyertakan
ID pemilik/repository. Runtime memakai identitas berbeda, `fiscycle-runtime-pull`, dengan AcrPull.
Tidak diperlukan PAT GitHub, secret client Azure, atau password registry dalam repository.
Client ID, tenant ID dan subscription ID dalam workflow adalah identifier, bukan secret.

## Resource dan batas

- Resource group: `rg-fiscycle-ai`, region `southeastasia`.
- Environment: `fiscycle-ai-env`, Consumption.
- Container App: `fiscycle-ai-service` (status aktual lihat laporan deployment).
- CPU/RAM: 2 vCPU / 4 GiB; min replicas 0, max replicas 1; satu worker.
- HTTPS port target 8000; endpoint inferensi memerlukan Bearer service token.
- Template tanpa secret: [containerapp.template.json](containerapp.template.json).

Registry Basic dan environment sudah ada sebelum deployment ini. Pemakaian Azure tetap
mengonsumsi kredit subscription; scale-to-zero bukan jaminan seluruh layanan gratis.
Jangan mengubah subscription Students menjadi Pay-As-You-Go untuk melewati batas kredit.

## Batas data dan operasi

Data Water privat tidak masuk Git, image, atau upload cloud. Tanpa mount privat, replay Water
mengembalikan 503; Water tetap menerima request inferensi valid. Dua tes pytest dan dua
pemeriksaan HTTP yang memerlukan fixture Water privat di-skip secara eksplisit.

Sesi replay ada di memori; SQLite history berada pada filesystem sementara container.
Scale-to-zero/restart dapat menghilangkannya. Backend produk harus menyimpan riwayat bisnis.
Token service hanya untuk backend, tidak untuk bundle frontend. Model BSF tetap
RESEARCH_PROTOTYPE / NOT_FIELD_VALIDATED. DSS adalah aturan pemeriksaan teknis manual,
bukan rekomendasi budidaya berbasis paper/ahli yang tervalidasi.

## Bukti pengujian

Perbaikan retry menangani ConnectionResetError saat port Docker tersedia lebih awal daripada
HTTP service. Tiga tes regresi host lulus. Run GitHub `42388365781` lulus build dan seluruh
pemeriksaan container yang diwajibkan, lalu gagal login OIDC karena subject tidak cocok.
Federasi sudah disesuaikan dengan subject aktual; hasil deploy berikutnya dicatat terpisah.
Tidak ada pemeriksaan model yang dihapus untuk meloloskan deployment.

## Referensi resmi

- [Azure OIDC dari GitHub](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect)
- [Managed identity untuk pull image](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity-image-pull)
- [Billing Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/billing)
- [Batas storage sementara](https://learn.microsoft.com/en-us/azure/container-apps/storage-mounts)
