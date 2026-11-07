import { aiError, forwardAi } from '@/lib/ai/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 120;

export async function GET(request: Request) {
  const response = await forwardAi(request, 'health');
  if (!response.ok) return response;
  const upstream = await response.json();
  return Response.json({ ok: upstream.ready === true, mode: 'MODEL_SERVICE', upstream },
    { status: upstream.ready ? 200 : 503, headers: { 'Cache-Control': 'no-store' } });
}

export async function POST(request: Request) {
  let body;
  try { body = await request.json(); }
  catch { return aiError(400, 'INVALID_JSON', 'Format JSON tidak valid.'); }
  if (!body || typeof body !== 'object' || !body.payload || typeof body.payload !== 'object' || Array.isArray(body.payload)) {
    return aiError(400, 'INVALID_PAYLOAD', 'Isi domain dan payload sesuai kontrak API.');
  }
  const paths: Record<string, string> = { bsf_b1: 'api/v1/bsf/forecast', water_analyze: 'api/v1/water/analyze' };
  if (typeof body.domain !== 'string' || !Object.hasOwn(paths, body.domain)) {
    return aiError(400, 'UNSUPPORTED_DOMAIN', 'Domain analisis tidak didukung.');
  }
  const path = paths[body.domain];
  if (!path) return aiError(400, 'UNSUPPORTED_DOMAIN', 'Domain analisis tidak didukung.');
  const outgoing = new Request(request.url, { method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(request.headers.get('origin') ? { Origin: request.headers.get('origin')! } : {}),
      ...(request.headers.get('host') ? { Host: request.headers.get('host')! } : {}) }, body: JSON.stringify(body.payload) });
  return forwardAi(outgoing, path);
}
