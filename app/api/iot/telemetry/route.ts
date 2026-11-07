import { NextResponse, type NextRequest } from 'next/server';
import { SEED_PONDS, SEED_DEVICES } from '@/mocks/seed';
import { derivePondStatus, METRIC_META } from '@/lib/telemetry';
import type { WaterTelemetry } from '@/lib/types';

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const pondId = searchParams.get('pondId');

  if (pondId) {
    const normalized = pondId.toUpperCase();
    const pond = SEED_PONDS.find(
      (p) => p.id.toUpperCase() === normalized || p.id.replace('-', '').toUpperCase() === normalized.replace('-', '')
    );

    if (!pond) {
      return NextResponse.json(
        { ok: false, error: `Pond '${pondId}' not found` },
        { status: 404 }
      );
    }

    const connectedDevices = SEED_DEVICES.filter((d) => d.pondId === pond.id);
    const status = derivePondStatus(pond.telemetry);

    return NextResponse.json({
      ok: true,
    provenance: 'SIMULATED_APPLICATION_SEED',
    live_sensor_connected: false,
    persisted: false,
      pondId: pond.id,
      pondName: pond.name,
      species: pond.species,
      status,
      telemetry: pond.telemetry,
      thresholds: METRIC_META,
      devices: connectedDevices,
      lastSynced: pond.telemetry.recordedAt,
    });
  }

  // If no pondId specified, return all ponds telemetry overview
  const pondsOverview = SEED_PONDS.map((p) => ({
    pondId: p.id,
    pondName: p.name,
    species: p.species,
    status: derivePondStatus(p.telemetry),
    telemetry: p.telemetry,
    devicesCount: SEED_DEVICES.filter((d) => d.pondId === p.id).length,
  }));

  return NextResponse.json({
    ok: true,
    provenance: 'SIMULATED_APPLICATION_SEED',
    live_sensor_connected: false,
    persisted: false,
    totalPonds: SEED_PONDS.length,
    ponds: pondsOverview,
    devicesTotal: SEED_DEVICES.length,
    activeGateway: SEED_DEVICES.find((d) => d.type === 'Gateway LoRa') ?? null,
  });
}

interface TelemetryUpdatePayload {
  pondId: string;
  ph?: number;
  temperatureC?: number;
  dissolvedOxygenMgL?: number;
  turbidityNtu?: number;
  ammoniaMgL?: number;
}

export async function POST(req: NextRequest) {
  let body: TelemetryUpdatePayload;
  try {
    body = (await req.json()) as TelemetryUpdatePayload;
  } catch {
    return NextResponse.json(
      { ok: false, error: 'Invalid JSON payload' },
      { status: 400 }
    );
  }

  const { pondId, ph, temperatureC, dissolvedOxygenMgL, turbidityNtu, ammoniaMgL } = body;

  if (!pondId) {
    return NextResponse.json(
      { ok: false, error: 'Parameter pondId wajib diisi' },
      { status: 400 }
    );
  }

  const pond = SEED_PONDS.find(
    (p) => p.id.toUpperCase() === pondId.toUpperCase()
  );

  if (!pond) {
    return NextResponse.json(
      { ok: false, error: `Kolam '${pondId}' tidak ditemukan.` },
      { status: 404 }
    );
  }

  const updatedTelemetry: WaterTelemetry = {
    ...pond.telemetry,
    recordedAt: new Date().toISOString(),
    ph: ph ?? pond.telemetry.ph,
    temperatureC: temperatureC ?? pond.telemetry.temperatureC,
    dissolvedOxygenMgL: dissolvedOxygenMgL ?? pond.telemetry.dissolvedOxygenMgL,
    turbidityNtu: turbidityNtu ?? pond.telemetry.turbidityNtu,
    ammoniaMgL: ammoniaMgL ?? pond.telemetry.ammoniaMgL,
  };

  const newStatus = derivePondStatus(updatedTelemetry);

  return NextResponse.json({
    ok: true,
    provenance: 'SIMULATED_APPLICATION_SEED',
    live_sensor_connected: false,
    persisted: false,
    message: 'Simulasi telemetri dihitung; tidak disimpan dan tidak dikirim ke perangkat IoT.',
    pondId: pond.id,
    pondName: pond.name,
    telemetry: updatedTelemetry,
    status: newStatus,
  });
}
