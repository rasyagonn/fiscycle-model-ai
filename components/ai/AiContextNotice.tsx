'use client';
import { usePathname } from 'next/navigation';
import { AiEntry } from './AiEntry';

export function AiContextNotice() {
  const path = usePathname();
  if (!/^\/(mitra|desktop)\/(dashboard|ponds|bsf|insights)(\/|$)/.test(path)) return null;
  return <AiEntry desktop={path.startsWith('/desktop/')} />;
}
