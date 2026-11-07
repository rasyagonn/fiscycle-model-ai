import { NextResponse, type NextRequest } from 'next/server';
import { SEED_ORDERS, SEED_PONDS, SEED_FARM } from '@/mocks/seed';
import { rankPondsForOrder } from '@/lib/matching';
import type { FishOrder } from '@/lib/types';



interface MatchSupplyRequestBody {
  orderId?: string;
  order?: Partial<FishOrder>;
}

export async function POST(req: NextRequest) {
  let body: MatchSupplyRequestBody = {};
  try {
    body = (await req.json()) as MatchSupplyRequestBody;
  } catch {
    // If empty body, fall back to default pending order
  }

  const { orderId, order: customOrder } = body;

  // Determine target order
  let targetOrder: FishOrder | undefined;

  if (orderId) {
    targetOrder = SEED_ORDERS.find(
      (o) => o.id.toUpperCase() === orderId.toUpperCase()
    );
  }

  if (!targetOrder && customOrder) {
    const baseOrder = SEED_ORDERS[0];
    const qty = customOrder.quantityKg ?? 500;
    const price = customOrder.pricePerKgIdr ?? 32000;
    const subtotal = qty * price;

    targetOrder = {
      ...baseOrder,
      ...customOrder,
      id: customOrder.id || 'ORD-CUSTOM',
      buyerUserId: customOrder.buyerUserId || 'USR-B2B-01',
      buyerName: customOrder.buyerName || 'ABC Restaurant',
      buyerChannel: customOrder.buyerChannel || 'b2b',
      species: customOrder.species || 'Nila',
      sizeGradeLabel: customOrder.sizeGradeLabel || '300-400g/ekor',
      quantityKg: qty,
      pricePerKgIdr: price,
      subtotalIdr: subtotal,
      totalIdr: subtotal,
      deliveryAddress: customOrder.deliveryAddress || 'Jl. Basuki Rahmat No. 45, Surabaya',
      deliveryDate: customOrder.deliveryDate || '2026-11-16',
      status: customOrder.status || 'Menunggu Alokasi',
    };
  }

  // Fallback to Golden Thread order ORD-0241 or first pending B2B order
  if (!targetOrder) {
    targetOrder =
      SEED_ORDERS.find((o) => o.id === 'ORD-0241') ||
      SEED_ORDERS.find((o) => o.buyerChannel === 'b2b') ||
      SEED_ORDERS[0];
  }

  // Business ranking over demo seed data; this is not a trained model.
  const rankedSuggestions = rankPondsForOrder(targetOrder, SEED_PONDS, SEED_FARM);

  return NextResponse.json({
    ok: true,
    mode: 'BUSINESS_RULE_DEMO',
    provenance: 'SIMULATED_APPLICATION_SEED',
    model_inference: false,
    orderId: targetOrder.id,
    order: {
      id: targetOrder.id,
      buyerName: targetOrder.buyerName,
      species: targetOrder.species,
      sizeGradeLabel: targetOrder.sizeGradeLabel,
      quantityKg: targetOrder.quantityKg,
      deliveryDate: targetOrder.deliveryDate,
    },
    topMatch: rankedSuggestions[0] ?? null,
    recommendations: rankedSuggestions,
  });
}
