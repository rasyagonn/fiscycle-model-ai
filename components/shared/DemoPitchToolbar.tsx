'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import {
  Zap,
  X,
  RotateCcw,
  Sparkles,
} from 'lucide-react';
import { useHydrated } from '@/hooks/useHydrated';
import { useAuthStore } from '@/store/useAuthStore';
import { useWastePointStore } from '@/store/useWastePointStore';
import { useMitraStore } from '@/store/useMitraStore';
import { useAdminStore } from '@/store/useAdminStore';
import { useB2BCartStore } from '@/store/useB2BCartStore';
import { resetAllStores } from '@/lib/demo/resetAllStores';
import { runGoldenThreadVerification } from '@/lib/demo/verifyGoldenThread';
import type { Role } from '@/lib/types';

interface GoldenThreadStep {
  step: number;
  role: Role;
  roleLabel: string;
  title: string;
  subtitle: string;
  route: string;
}

const GOLDEN_THREAD_STEPS: GoldenThreadStep[] = [
  {
    step: 1,
    role: 'b2b',
    roleLabel: 'B2B Resto',
    title: '1. B2B Setor Limbah 42 kg (IN-0045)',
    subtitle: 'ABC Restaurant setor 42 kg sisa dapur',
    route: '/b2b/waste',
  },
  {
    step: 2,
    role: 'admin',
    roleLabel: 'Admin',
    title: '2. Admin Verifikasi (+420 Poin -> 3.000)',
    subtitle: 'Verifikasi limbah & alokasi ke BSF-04',
    route: '/admin/waste',
  },
  {
    step: 3,
    role: 'mitra',
    roleLabel: 'Mitra',
    title: '3. Mitra Pulihkan DO Kolam 2 & BSF',
    subtitle: 'Atasi anomali aerasi & substitusi pakan',
    route: '/mitra/ponds/POND-02',
  },
  {
    step: 4,
    role: 'b2b',
    roleLabel: 'B2B Resto',
    title: '4. B2B Pesan 500 kg Nila (-Rp 300rb Poin)',
    subtitle: 'Redeem 3.000 Poin untuk pasokan segar',
    route: '/b2b/orders',
  },
  {
    step: 5,
    role: 'admin',
    roleLabel: 'Admin',
    title: '5. Admin Alokasi Kolam 4 (Skor 96%)',
    subtitle: 'Orkestrasi AI match pasokan panen',
    route: '/admin/supply',
  },
  {
    step: 6,
    role: 'mitra',
    roleLabel: 'Mitra',
    title: '6. Mitra Terima Kontrak Panen',
    subtitle: 'Konfirmasi kontrak panen Rp 16.000.000',
    route: '/mitra/harvest?tab=penawaran',
  },
];

export function DemoPitchToolbar() {
  const isHydrated = useHydrated();
  const router = useRouter();
  const [isOpen, setIsOpen] = useState(false);

  const { currentUser, quickLoginAsRole } = useAuthStore();

  if (!isHydrated) return null;

  const handleStepJump = (step: GoldenThreadStep) => {
    quickLoginAsRole(step.role);
    router.push(step.route);
    setIsOpen(false);
  };

  const handleAutoRun = () => {
    // 1. Submit waste 42kg (IN-0045)
    const wasteStore = useWastePointStore.getState();
    let contrib = wasteStore.contributions.find((c) => c.id === 'IN-0045');
    if (!contrib) {
      contrib = wasteStore.submitWaste({
        contributorUserId: 'USR-B2B-01',
        contributorName: 'ABC Restaurant',
        contributorRole: 'b2b',
        category: 'sisa_dapur',
        categoryLabel: 'Sisa Makanan Dapur',
        estimatedKg: 42,
        pickupDate: '2026-11-06',
        pickupSlot: '08:00 - 10:00 WIB',
        pickupAddress: 'ABC Restaurant - Jl. Raya Darmo No. 88, Surabaya',
      });
    }

    // 2. Admin verify waste (+420 Poin -> 3.000)
    if (contrib.status !== 'Diterima') {
      useWastePointStore.getState().verifyWaste(contrib.id, 42, 'A', 'BSF-04');
    }

    // 3. Mitra resolve DO Kolam 2 & BSF
    const mitraStore = useMitraStore.getState();
    const pond2 = mitraStore.ponds.find((p) => p.id === 'POND-02');
    if (pond2 && pond2.status !== 'Baik') {
      mitraStore.resolvePondAlert('POND-02');
    }
    const hasAllocatedBsf = mitraStore.bsfFeedAllocations.some((a) => a.pondId === 'POND-02');
    if (!hasAllocatedBsf) {
      try {
        mitraStore.allocateBsfToPond('BSF-04', 'POND-02', 20);
      } catch {
        // Stock already applied or safe bypass
      }
    }

    // 4. B2B Order 500kg Nila with points redeem
    const cartStore = useB2BCartStore.getState();
    let order = cartStore.orders.find((o) => o.id === 'ORD-0241');
    if (!order) {
      cartStore.updateB2BDraft({
        species: 'Nila',
        sizeGradeLabel: '300-400g/ekor',
        quantityKg: 500,
        pricePerKgIdr: 32000,
        frequency: 'Sekali',
      });
      cartStore.setB2BRedeemPoints(true);
      const buyerUser = {
        id: 'USR-B2B-01',
        name: 'Hendro Wijaya',
        email: 'procurement@abcrestaurant.id',
        phone: '081355550007',
        role: 'b2b' as const,
        organizationName: 'ABC Restaurant',
        avatarInitials: 'AR',
        walletId: 'WAL-0007',
      };
      const wallet = useWastePointStore.getState().wallets['WAL-0007'];
      const balance = wallet?.balancePoints ?? 3000;
      order = cartStore.submitB2BOrder(buyerUser, balance);
      if (order.pointsRedeemed > 0 && wallet) {
        useWastePointStore.getState().deductPointsForOrder(wallet.id, order.pointsRedeemed, order.id);
      }
    }

    // 5. Admin allocate Kolam 4
    const adminStore = useAdminStore.getState();
    let offers = useMitraStore.getState().allocationOffers.filter((o) => o.orderId === order?.id);
    if (offers.length === 0 && order) {
      offers = adminStore.approveSupplyAllocation(order.id, [
        {
          farmId: 'FARM-0028',
          pondId: 'POND-04',
          allocatedKg: 500,
        },
      ]);
    }

    // 6. Mitra accept harvest contract
    if (offers.length > 0) {
      const offerId = offers[0].id;
      useMitraStore.getState().respondToAllocation(offerId, true);
    }

    toast.success('🚀 Auto-Run 6-Step Golden Thread Sukses!', {
      description: 'Limbah 42 kg terverifikasi (+420 pts), DO Kolam 2 pulih, pesanan ORD-0241 dialokasikan, dan kontrak panen Rp 16.000.000 diterima!',
    });
  };

  const handleSelfTest = () => {
    const report = runGoldenThreadVerification();
    if (report.passed) {
      toast.success('✅ Seluruh 6 Assertion Golden Thread LULUS 100%!', {
        description:
          '1. IN-0045 terbuat · 2. Admin verify +420 pts & BSF-04 +42kg · 3. DO Kolam 2 pulih & pakan BSF 20kg · 4. ORD-0241 redeem 3.000 pts · 5. Alokasi baru unik, skor aturan 96% · 6. Mitra terima panen',
      });
    } else {
      const failed = report.steps.find((s) => !s.passed);
      toast.error(`❌ Self-Test Gagal di Step ${failed?.step}: ${failed?.name}`, {
        description: failed?.detail,
      });
    }
  };

  const handleReset = () => {
    resetAllStores({ keepSession: true });
    toast.success('Semua data demo berhasil di-reset ke kondisi awal!');
  };

  return (
    <div className="fixed top-3 right-3 z-[100] font-sans antialiased">
      {!isOpen ? (
        <button
          onClick={() => setIsOpen(true)}
          className="bg-[#1A365D]/95 hover:bg-[#1A365D] text-white text-[11px] font-bold px-3 py-1.5 rounded-full shadow-lg border border-white/20 flex items-center gap-1.5 backdrop-blur-md cursor-pointer transition active:scale-95"
        >
          <Zap className="size-3.5 text-[#00B4D8] fill-[#00B4D8]" />
          <span>⚡ Pitch Mode</span>
        </button>
      ) : (
        <div className="w-80 max-h-[90vh] overflow-y-auto bg-white border border-slate-200 rounded-2xl shadow-2xl p-3.5 text-[#173251] space-y-3">
          {/* Header */}
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <span className="p-1 rounded-full bg-[#1A365D] text-[#00B4D8]">
                <Zap className="size-3.5 fill-[#00B4D8]" />
              </span>
              <div>
                <h4 className="text-[12.5px] font-extrabold text-[#1A365D] leading-tight">
                  Demo Pitch Controller
                </h4>
                <p className="text-[10px] text-slate-500">
                  Role: <span className="font-bold text-[#00629b] uppercase">{currentUser?.role ?? 'GUEST'}</span> ({currentUser?.name ?? 'Belum login'})
                </p>
              </div>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="p-1 text-slate-400 hover:text-slate-600 rounded-md hover:bg-slate-100 transition"
              aria-label="Tutup Toolbar"
            >
              <X className="size-4" />
            </button>
          </div>

          {/* Navigator Showcase Shortcut */}
          <button
            onClick={() => {
              router.push('/showcase');
              setIsOpen(false);
            }}
            className="w-full py-2 px-3 rounded-[9px] bg-gradient-to-r from-[#1A365D] to-[#00629b] hover:brightness-105 active:scale-95 text-white font-extrabold text-[11px] shadow-xs flex items-center justify-center gap-1.5 transition"
          >
            <span>🧭 Buka Navigator 47 Screen (/showcase)</span>
          </button>

          {/* Quick 1-Click Role Switcher */}
          <div>
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">
              Role Switcher Cepat
            </p>
            <div className="grid grid-cols-4 gap-1">
              {(
                [
                  { role: 'b2b', label: 'B2B' },
                  { role: 'admin', label: 'Admin' },
                  { role: 'mitra', label: 'Mitra' },
                  { role: 'b2c', label: 'B2C' },
                ] as const
              ).map((r) => (
                <button
                  key={r.role}
                  onClick={() => quickLoginAsRole(r.role)}
                  className={`py-1 text-[10px] font-bold rounded-[6px] border transition ${
                    currentUser?.role === r.role
                      ? 'bg-[#1A365D] text-white border-[#1A365D]'
                      : 'bg-[#f8fafc] text-slate-600 border-slate-200 hover:bg-slate-100'
                  }`}
                >
                  {r.label}
                </button>
              ))}
            </div>
          </div>

          {/* 6 Guided Golden Thread Steps */}
          <div className="space-y-1.5">
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
              6-Step Golden Thread
            </p>
            <div className="space-y-1 max-h-56 overflow-y-auto pr-0.5">
              {GOLDEN_THREAD_STEPS.map((s) => (
                <button
                  key={s.step}
                  onClick={() => handleStepJump(s)}
                  className="w-full text-left p-2 rounded-[9px] border border-slate-150 hover:border-[#00629b] bg-[#fbfdfd] hover:bg-[#eef8fc] transition group"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold text-[#1A365D] group-hover:text-[#00629b] line-clamp-1">
                      {s.title}
                    </span>
                    <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-slate-100 text-slate-600 uppercase shrink-0 ml-1">
                      {s.roleLabel}
                    </span>
                  </div>
                  <p className="text-[9.5px] text-slate-500 mt-0.5 line-clamp-1">
                    {s.subtitle}
                  </p>
                </button>
              ))}
            </div>
          </div>

          {/* Actions: Auto-Run & Reset */}
          <div className="pt-2 border-t border-slate-100 space-y-1.5">
            <button
              onClick={handleSelfTest}
              className="w-full py-2 px-3 rounded-[9px] bg-emerald-600 hover:bg-emerald-700 active:scale-95 text-white font-bold text-[11px] shadow-xs flex items-center justify-center gap-1.5 transition"
            >
              <span>✅ Self-Test 6 Assertions</span>
            </button>

            <button
              onClick={handleAutoRun}
              className="w-full py-2 px-3 rounded-[9px] bg-gradient-to-r from-[#00629b] to-[#008d91] hover:brightness-105 active:scale-95 text-white font-bold text-[11px] shadow-xs flex items-center justify-center gap-1.5 transition"
            >
              <Sparkles className="size-3.5 text-[#a1f3de]" />
              <span>🚀 Auto-Run 6 Steps State</span>
            </button>

            <button
              onClick={handleReset}
              className="w-full py-1.5 px-3 rounded-[9px] bg-[#f8fafc] hover:bg-rose-50 hover:border-rose-200 hover:text-rose-700 text-slate-600 border border-slate-200 font-semibold text-[10.5px] flex items-center justify-center gap-1.5 transition"
            >
              <RotateCcw className="size-3 text-slate-400" />
              <span>🔄 Reset Demo Data</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
