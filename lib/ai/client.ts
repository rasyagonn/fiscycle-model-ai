import type { FishOrder } from '@/lib/types';
import { aiRequest, aiPost, type JsonObject, type WaterResult } from './service-client';

export type WaterAnalysisResponse = WaterResult;
export type BsfForecastResponse = JsonObject & { predicted_next_weight_mg: number | null };
export interface AiHealthResponse { ok: boolean; mode: 'MODEL_SERVICE' | 'UNAVAILABLE'; upstream?: unknown; }

async function localRequest(path: string, init?: RequestInit): Promise<JsonObject> {
  const response = await fetch(path, { ...init, cache: 'no-store' });
  const body = await response.json();
  if (!response.ok) throw new Error(body.message || body.error || `Permintaan gagal (HTTP ${response.status})`);
  return body;
}

/** Typed entry points for actual inference. Demo business APIs disclose their provenance. */
export const FiscycleAiClient = {
  async checkHealth(): Promise<AiHealthResponse> {
    try { return await localRequest('/api/ai/bridge') as unknown as AiHealthResponse; }
    catch { return { ok: false, mode: 'UNAVAILABLE' }; }
  },
  fetchWaterAnalysis(payload: JsonObject): Promise<WaterAnalysisResponse> {
    return aiPost<WaterResult>('api/v1/water/analyze', payload);
  },
  fetchBsfForecast(payload: JsonObject): Promise<BsfForecastResponse> {
    return aiPost<BsfForecastResponse>('api/v1/bsf/forecast', payload);
  },
  fetchSupplyMatching(orderOrId: string | Partial<FishOrder>) {
    return localRequest('/api/ai/match-supply', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(typeof orderOrId === 'string' ? { orderId: orderOrId } : { order: orderOrId }) });
  },
  fetchTelemetry(pondId?: string) {
    return localRequest('/api/iot/telemetry'+(pondId ? '?pondId='+encodeURIComponent(pondId) : ''));
  },
  postTelemetry(payload: JsonObject) {
    return localRequest('/api/iot/telemetry', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  },
  request: aiRequest,
};
