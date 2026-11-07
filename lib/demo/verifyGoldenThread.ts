import { resetAllStores } from './resetAllStores';
import { useWastePointStore } from '@/store/useWastePointStore';
import { useMitraStore } from '@/store/useMitraStore';
import { useAdminStore } from '@/store/useAdminStore';
import { useB2BCartStore } from '@/store/useB2BCartStore';
import type { User } from '@/lib/types';

export interface VerificationStepResult {
  step: number;
  name: string;
  passed: boolean;
  detail: string;
}

export interface GoldenThreadVerificationReport {
  passed: boolean;
  timestamp: string;
  steps: VerificationStepResult[];
}

/**
 * Deterministic automated assertion runner for the 6-Step Circular Economy Golden Thread.
 * Resets stores to baseline, executes each state transition sequentially,
 * and rigorously asserts state changes in real Zustand stores.
 */
export function runGoldenThreadVerification(): GoldenThreadVerificationReport {
  // 0. Clean reset
  resetAllStores();

  const results: VerificationStepResult[] = [];

  // --------------------------------------------------------------------------
  // Step 1: B2B Setor Limbah 42 kg (IN-0045)
  // --------------------------------------------------------------------------
  const wasteStore = useWastePointStore.getState();
  const contrib = wasteStore.submitWaste({
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

  const step1Passed = contrib.id === 'IN-0045' && contrib.status === 'Menunggu Verifikasi';
  results.push({
    step: 1,
    name: 'B2B Setor Limbah 42 kg (IN-0045)',
    passed: step1Passed,
    detail: step1Passed
      ? `IN-0045 terbuat dengan status 'Menunggu Verifikasi', estimasi 42 kg.`
      : `GAGAL: Ditemukan id=${contrib.id}, status=${contrib.status}`,
  });

  // --------------------------------------------------------------------------
  // Step 2: Admin Verifikasi (+420 Poin -> 3.000 Poin & BSF-04 +42 kg -> 142 kg)
  // --------------------------------------------------------------------------
  useWastePointStore.getState().verifyWaste('IN-0045', 42, 'A', 'BSF-04');

  const walletAfterVerify = useWastePointStore.getState().wallets['WAL-0007'];
  const bsfBatches = useMitraStore.getState().bsfBatches;
  const bsf04 = bsfBatches.find((b) => b.id === 'BSF-04');

  const step2PointsOk = walletAfterVerify?.balancePoints === 3000;
  const step2BsfOk = bsf04?.organicInputTotalKg === 142;
  const step2Passed = step2PointsOk && step2BsfOk;

  results.push({
    step: 2,
    name: 'Admin Verifikasi Limbah (+420 Poin & BSF-04 +42 kg)',
    passed: step2Passed,
    detail: step2Passed
      ? `Saldo WAL-0007 = 3.000 Poin (tepat), Input BSF-04 = 142 kg (tepat).`
      : `GAGAL: Poin=${walletAfterVerify?.balancePoints ?? 'null'} (harap 3000), BSF Input=${bsf04?.organicInputTotalKg ?? 'null'} (harap 142)`,
  });

  // --------------------------------------------------------------------------
  // Step 3: Mitra Pulihkan DO Kolam 2 & Alokasi 20 kg Pakan BSF
  // --------------------------------------------------------------------------
  const mitraStore = useMitraStore.getState();
  mitraStore.resolvePondAlert('POND-02');
  mitraStore.allocateBsfToPond('BSF-04', 'POND-02', 20);

  const pond2 = useMitraStore.getState().ponds.find((p) => p.id === 'POND-02');
  const allocations = useMitraStore.getState().bsfFeedAllocations;
  const pond2Alloc = allocations.find((a) => a.pondId === 'POND-02' && a.batchId === 'BSF-04');

  const step3StatusOk = pond2?.status === 'Baik' && (pond2.telemetry.dissolvedOxygenMgL >= 5.0);
  const step3AllocOk = pond2Alloc !== undefined && pond2Alloc.maggotKg === 20;
  const step3Passed = step3StatusOk && step3AllocOk;

  results.push({
    step: 3,
    name: 'Mitra Pulihkan DO Kolam 2 & Alokasikan Pakan BSF',
    passed: step3Passed,
    detail: step3Passed
      ? `Kolam 2 status='Baik', DO=${pond2?.telemetry.dissolvedOxygenMgL} mg/L, Alokasi Maggot=${pond2Alloc?.maggotKg} kg.`
      : `GAGAL: Kolam status=${pond2?.status}, DO=${pond2?.telemetry.dissolvedOxygenMgL}, Alokasi=${pond2Alloc?.maggotKg}`,
  });

  // --------------------------------------------------------------------------
  // Step 4: B2B Order 500 kg Nila (-Rp 300.000 Poin -> Rp 15.950.000)
  // --------------------------------------------------------------------------
  const cartStore = useB2BCartStore.getState();
  cartStore.updateB2BDraft({
    species: 'Nila',
    sizeGradeLabel: '300-400g/ekor',
    quantityKg: 500,
    pricePerKgIdr: 32000,
    frequency: 'Sekali',
  });
  cartStore.setB2BRedeemPoints(true);

  const buyerUser: User = {
    id: 'USR-B2B-01',
    name: 'Hendro Wijaya',
    email: 'procurement@abcrestaurant.id',
    phone: '081355550007',
    role: 'b2b',
    organizationName: 'ABC Restaurant',
    avatarInitials: 'AR',
    walletId: 'WAL-0007',
  };

  const currentWallet = useWastePointStore.getState().wallets['WAL-0007'];
  const balance = currentWallet?.balancePoints ?? 3000;
  const order = cartStore.submitB2BOrder(buyerUser, balance);

  if (order.pointsRedeemed > 0 && currentWallet) {
    useWastePointStore.getState().deductPointsForOrder(currentWallet.id, order.pointsRedeemed, order.id);
  }

  const walletAfterOrder = useWastePointStore.getState().wallets['WAL-0007'];
  const step4OrderOk = order.id === 'ORD-0241' && order.pointsRedeemed === 3000 && order.totalIdr === 15950000;
  const step4WalletOk = walletAfterOrder?.balancePoints === 0;
  const step4Passed = step4OrderOk && step4WalletOk;

  results.push({
    step: 4,
    name: 'B2B Pesan 500 kg Nila dengan Redeem 3.000 Poin',
    passed: step4Passed,
    detail: step4Passed
      ? `ORD-0241 dibuat, redeem 3.000 Poin (-Rp 300.000), total Rp 15.950.000, sisa poin = 0.`
      : `GAGAL: Order=${order.id}, Redeem=${order.pointsRedeemed}, Total=${order.totalIdr}, Sisa Poin=${walletAfterOrder?.balancePoints}`,
  });

  // --------------------------------------------------------------------------
  // Step 5: Admin Alokasi Kolam 4 (skor aturan 96%, ID baru tidak menimpa seed)
  // --------------------------------------------------------------------------
  const adminStore = useAdminStore.getState();
  const previousOfferIds = new Set(useMitraStore.getState().allocationOffers.map(o => o.id));
  const offers = adminStore.approveSupplyAllocation(order.id, [
    {
      farmId: 'FARM-0028',
      pondId: 'POND-04',
      allocatedKg: 500,
    },
  ]);

  const alcOffer = offers.find((o) => o.orderId === order.id);
  const updatedOrder = useB2BCartStore.getState().orders.find((o) => o.id === order.id);

  const step5OfferOk = alcOffer !== undefined && !previousOfferIds.has(alcOffer.id) && /^ALC-\d{4}$/.test(alcOffer.id) && alcOffer.pondId === 'POND-04' && alcOffer.allocatedKg === 500 && alcOffer.aiMatchScorePct === 96 && alcOffer.estimatedPayoutIdr === 16000000;
  const step5OrderOk = updatedOrder?.status === 'Dialokasikan' &&
    useMitraStore.getState().allocationOffers.length === previousOfferIds.size + 1 &&
    [...previousOfferIds].every(id => useMitraStore.getState().allocationOffers.some(o => o.id === id));
  const step5Passed = step5OfferOk && step5OrderOk;

  results.push({
    step: 5,
    name: 'Admin Alokasi Pasokan ke Kolam 4 (Skor Kecocokan 96%)',
    passed: step5Passed,
    detail: step5Passed
      ? `${alcOffer?.id} diterbitkan tanpa menimpa alokasi lama, skor kecocokan 96%, estimasi payout Rp 16.000.000, status order='Dialokasikan'.`
      : `GAGAL: ALC=${alcOffer?.id}, skor=${alcOffer?.aiMatchScorePct}, payout=${alcOffer?.estimatedPayoutIdr}, orderStatus=${updatedOrder?.status}`,
  });

  // --------------------------------------------------------------------------
  // Step 6: Mitra Terima Kontrak Panen (ORD-0241 -> Menunggu Panen)
  // --------------------------------------------------------------------------
  if (alcOffer) {
    useMitraStore.getState().respondToAllocation(alcOffer.id, true);
  }

  const finalOffer = useMitraStore.getState().allocationOffers.find((o) => o.id === alcOffer?.id && o.orderId === order.id);
  const finalOrder = useB2BCartStore.getState().orders.find((o) => o.id === order.id);

  const step6OfferOk = finalOffer?.status === 'Diterima';
  const step6OrderOk = finalOrder?.status === 'Menunggu Panen';
  const step6Passed = step6OfferOk && step6OrderOk;

  results.push({
    step: 6,
    name: 'Mitra Terima Kontrak Panen (Alokasi Sukses)',
    passed: step6Passed,
    detail: step6Passed
      ? `Kontrak ${alcOffer?.id} status='Diterima', ORD-0241 beralih ke status='Menunggu Panen'.`
      : `GAGAL: Offer status=${finalOffer?.status}, Order status=${finalOrder?.status}`,
  });

  const allPassed = results.every((r) => r.passed);

  return {
    passed: allPassed,
    timestamp: new Date().toISOString(),
    steps: results,
  };
}
