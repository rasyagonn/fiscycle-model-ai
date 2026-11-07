export const AI_PROXY = '/api/ai/service/';
export type JsonObject = Record<string, unknown>;

export async function aiRequest<T = JsonObject>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(AI_PROXY+path.replace(/^\//, ''), { ...init, cache: 'no-store' });
  const data = await response.json();
  if (!response.ok) {
    const detail = data.message || (typeof data.detail === 'string' ? data.detail : null);
    throw new Error(detail || `Permintaan ditolak (HTTP ${response.status}). Periksa data dan status layanan.`);
  }
  return data as T;
}

export function aiPost<T = JsonObject>(path: string, payload: unknown): Promise<T> {
  return aiRequest<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
}

export interface ModelState { loaded: boolean; artifacts_verified: boolean; model_source: string; model_version: string; }
export interface Health { ready: boolean; services: Record<string, unknown>; runtime_models: Record<string, ModelState>; }
export interface GalleryImage { id: string; sample_id: string; track: 'A1' | 'A2'; thumbnail_url: string; content_url: string; width: number; height: number; }
export interface Period { id: string; start: string; end: string; pond_id: string; label: string; }
export interface Trajectory { trajectory_id: string; moisture_percent: number; observation_count: number; }
export interface BsfReplay {
  revealed: number; total_observations: number; source: string; limitation: string;
  observations: { day: number; measured_weight_mg: number }[];
  forecast: { target_day: number; result: { predicted_next_weight_mg: number | null } } | null;
}
export interface WaterResult {
  current_readings: Record<string, number | null>;
  data_quality: { status: string; reasons: string[] };
  forecasts: Record<string, Record<string, { value: number | null; unit: string; method?: string; reason?: string }>>;
  decision_support: JsonObject;
}
export interface WaterReplay {
  session_id: string; status: string; finished: boolean;
  processed_observations: number; total_observations: number;
  latest_result: WaterResult | null;
  observations: { timestamp: string; ph: number | null; temperature_c: number | null; turbidity_ntu: number | null }[];
  metrics: { rows: { parameter: string; horizon_minutes: number; matched: number; prediction: { mae: number | null }; persistence_same_pairs: { mae: number | null } }[] };
}
