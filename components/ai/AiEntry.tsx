import Link from 'next/link';

export function AiEntry({ desktop = false }: { desktop?: boolean }) {
  return <aside className="m-4 rounded-2xl border border-[#a9c9db] bg-[#e2f3fc] p-4 text-[#173251]">
    <p className="text-xs">Ringkasan operasional pada halaman ini memakai data demo/simulasi aplikasi. Angkanya bukan hasil model atau sensor live.</p>
    <Link href={desktop ? '/desktop/ai' : '/mitra/ai'} className="mt-2 inline-block text-sm font-bold text-[#00629B]">Buka analisis model asli, replay historis &amp; DSS →</Link>
  </aside>;
}
