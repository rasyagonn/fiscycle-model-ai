'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  Menu,
  Home,
  Waves,
  RefreshCw,
  BarChart3,
  ListChecks,
  PackageCheck,
  TrendingUp,
  Cpu,
  ClipboardList,
  Sparkles,
  User,
  LogOut,
  ChevronRight,
  ShieldCheck,
} from 'lucide-react';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';
import { useAuthStore } from '@/store/useAuthStore';
import { useMitraStore } from '@/store/useMitraStore';

interface MenuLink {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
}

const OPERASIONAL_LINKS: MenuLink[] = [
  { label: 'Beranda Dashboard', href: '/mitra/dashboard', icon: Home },
  { label: 'Daftar Tambak Saya', href: '/mitra/farms', icon: ShieldCheck },
  { label: 'Daftar Kolam Tambak', href: '/mitra/ponds', icon: Waves },
  { label: 'Siklus Budidaya', href: '/mitra/cycles', icon: RefreshCw },
  { label: 'Ringkasan Produksi', href: '/mitra/production', icon: BarChart3 },
  { label: 'Pakan & Pertumbuhan', href: '/mitra/feed', icon: ListChecks },
];

const SIRKULAR_LINKS: MenuLink[] = [
  { label: 'BSF & Pakan Sirkular', href: '/mitra/bsf', icon: PackageCheck },
  { label: 'Pasar & Penjualan Panen', href: '/mitra/harvest', icon: TrendingUp },
];

const ANALITIK_LINKS: MenuLink[] = [
  { label: 'Pusat AI ? Water & BSF', href: '/mitra/ai', icon: Sparkles },
  { label: 'Perangkat IoT Tambak', href: '/mitra/devices', icon: Cpu },
  { label: 'Laporan & Analitik', href: '/mitra/reports', icon: ClipboardList },
  { label: 'Insight & Rekomendasi AI', href: '/mitra/insights', icon: Sparkles },
  { label: 'Profil & Tambak Saya', href: '/mitra/profile', icon: User },
];

export function MitraDrawerMenu() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const router = useRouter();
  const currentUser = useAuthStore((s) => s.currentUser);
  const logout = useAuthStore((s) => s.logout);
  const farm = useMitraStore((s) => s.farm);

  const handleLogout = () => {
    setOpen(false);
    logout();
    router.replace('/auth/login');
  };

  const renderLinkItem = (item: MenuLink) => {
    const isActive =
      item.href === '/mitra/dashboard'
        ? pathname === '/mitra/dashboard' || pathname === '/mitra'
        : pathname.startsWith(item.href);
    const Icon = item.icon;

    return (
      <Link
        key={item.href}
        href={item.href}
        onClick={() => setOpen(false)}
        className={`flex items-center justify-between px-3 py-2.5 rounded-xl text-xs font-medium transition-all ${
          isActive
            ? 'bg-[#00566b] text-white shadow-sm'
            : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/70'
        }`}
      >
        <div className="flex items-center gap-2.5">
          <Icon className={`size-4 ${isActive ? 'text-white' : 'text-slate-400'}`} />
          <span>{item.label}</span>
        </div>
        <ChevronRight className={`size-3.5 opacity-60 ${isActive ? 'text-white' : 'text-slate-400'}`} />
      </Link>
    );
  };

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger
        className="p-1.5 -ml-1 text-slate-700 hover:bg-slate-100 rounded-lg transition-colors inline-flex items-center justify-center"
        aria-label="Buka Menu Operasional"
      >
        <Menu className="size-5 text-[#163252]" />
      </SheetTrigger>
      <SheetContent
        side="left"
        className="w-[300px] sm:w-[320px] p-0 flex flex-col bg-white border-r border-slate-200"
      >
        <SheetHeader className="p-4 border-b border-slate-100 bg-slate-50/50">
          <div className="flex items-center gap-2 mb-2">
            <div className="size-8 rounded-lg bg-[#00566b] text-white flex items-center justify-center font-bold text-sm shadow-sm">
              F
            </div>
            <div>
              <SheetTitle className="text-sm font-bold text-[#163252]">
                Fiscycle Mitra
              </SheetTitle>
              <p className="text-[11px] text-slate-500">Workspace Pembudidaya Cerdas</p>
            </div>
          </div>

          <div className="mt-2 p-2.5 rounded-xl bg-white border border-slate-200/80 shadow-xs">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-bold text-slate-900 leading-tight">
                  {currentUser?.name || 'Budi Santoso'}
                </p>
                <p className="text-[10px] text-slate-500">{farm.name}</p>
              </div>
              <span className="inline-flex items-center gap-1 text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                <ShieldCheck className="size-3" />
                {farm.partnerToken || 'FSC-FARM-0028'}
              </span>
            </div>
          </div>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-3 py-3 space-y-4 text-xs">
          <div>
            <p className="px-3 pb-1 text-[10px] font-bold tracking-wider text-slate-400 uppercase">
              Operasional Tambak
            </p>
            <div className="space-y-0.5">{OPERASIONAL_LINKS.map(renderLinkItem)}</div>
          </div>

          <div>
            <p className="px-3 pb-1 text-[10px] font-bold tracking-wider text-slate-400 uppercase">
              Sirkular &amp; Bisnis
            </p>
            <div className="space-y-0.5">{SIRKULAR_LINKS.map(renderLinkItem)}</div>
          </div>

          <div>
            <p className="px-3 pb-1 text-[10px] font-bold tracking-wider text-slate-400 uppercase">
              Hardware &amp; Analitik
            </p>
            <div className="space-y-0.5">{ANALITIK_LINKS.map(renderLinkItem)}</div>
          </div>
        </div>

        <div className="p-3 border-t border-slate-100 bg-slate-50/50">
          <button
            onClick={handleLogout}
            className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-xl text-xs font-semibold text-rose-600 hover:bg-rose-50 border border-rose-200 transition-colors"
          >
            <LogOut className="size-4" />
            Keluar Akun
          </button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
