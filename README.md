# Fiscycle ? aplikasi utama + AI Service

Modul AI tersedia di **/mitra/ai** dan **/desktop/ai** melalui menu Pusat AI.
Water, A1, A2 v3, B1, DSS, kedua historical replay dan galeri 16 foto memakai model asli.
Panduan menjalankan dua service, environment, kontrak dan batas integrasi:
[docs/AI_INTEGRATION.md](docs/AI_INTEGRATION.md).

```powershell
pnpm.cmd install --frozen-lockfile
# Siapkan Python dan environment AI sesuai panduan, lalu dua terminal:
pnpm.cmd ai:dev
pnpm.cmd dev
```

Tes: `pnpm.cmd typecheck`, `pnpm.cmd lint`, `pnpm.cmd build`, `pnpm.cmd test:ai`.
Data operasional lama adalah simulasi; halaman Pusat AI menandai provenance model/replay.
Token layanan hanya berada di server. Proxy produksi tertutup secara default sampai
pengelola mengaktifkannya pada lingkungan internal atau memasang otorisasi backend.

---

This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
