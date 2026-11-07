// Server-side only: imported exclusively by Route Handlers, never by UI modules.
import routes from './routes.json';

const MAX_BODY = 10 * 1024 * 1024;
const headers = { 'Cache-Control': 'no-store' };

export function aiError(status: number, code: string, message: string) {
  return Response.json({ ok: false, mode: 'UNAVAILABLE', code, message }, { status, headers });
}

function permitted(path: string, method: string) {
  const segments = path.split('/');
  if (!segments.every((s) => /^[a-zA-Z0-9_-]+$/.test(s)) && path !== 'openapi.json') return false;
  return routes.some((route) => {
    const pattern = route.path.slice(1).split('/');
    return route.methods.includes(method.toLowerCase()) && pattern.length === segments.length &&
      pattern.every((part, index) => part.startsWith('{') || part === segments[index]);
  });
}

async function readBody(request: Request): Promise<ArrayBuffer | undefined> {
  if (request.method === 'GET' || request.method === 'HEAD' || !request.body) return undefined;
  const declared = request.headers.get('content-length');
  if (declared && (!/^\d+$/.test(declared) || Number(declared) > MAX_BODY)) throw new RangeError();
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_BODY) { await reader.cancel(); throw new RangeError(); }
    chunks.push(value);
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  return bytes.buffer;
}

export async function forwardAi(request: Request, path: string): Promise<Response> {
  if (process.env.NODE_ENV === 'production' && process.env.FISCYCLE_AI_PROXY_ENABLED !== 'true') {
    return aiError(503, 'AI_PROXY_DISABLED', 'Akses AI belum diaktifkan oleh pengelola aplikasi.');
  }
  if (!permitted(path, request.method)) return aiError(404, 'AI_ROUTE_NOT_ALLOWED', 'Endpoint AI tidak tersedia.');
  const origin = request.headers.get('origin');
  if (origin && request.method !== 'GET') {
    try {
      if (new URL(origin).host !== request.headers.get('host')) {
        return aiError(403, 'ORIGIN_REJECTED', 'Asal permintaan tidak diizinkan.');
      }
    } catch { return aiError(403, 'ORIGIN_REJECTED', 'Asal permintaan tidak valid.'); }
  }
  try {
    const base = new URL(process.env.FISCYCLE_AI_API_URL || process.env.FISCYCLE_AI_URL || 'http://127.0.0.1:8001');
    if (!['http:', 'https:'].includes(base.protocol) || base.username || base.password || base.pathname !== '/') {
      return aiError(503, 'AI_CONFIGURATION_INVALID', 'Konfigurasi alamat AI Service tidak valid.');
    }
    const target = new URL('/'+path, base);
    target.search = new URL(request.url).search;
    const outgoing = new Headers();
    const token = process.env.FISCYCLE_AI_API_KEY;
    if (token) outgoing.set('Authorization', 'Bearer '+token);
    const contentType = request.headers.get('content-type');
    if (contentType) outgoing.set('Content-Type', contentType);
    const body = await readBody(request);
    const upstream = await fetch(target, { method: request.method, headers: outgoing, body,
      cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(120_000) });
    const responseHeaders = new Headers(headers);
    responseHeaders.set('Content-Type', upstream.headers.get('content-type') || 'application/json');
    responseHeaders.set('X-Fiscycle-AI-Source', 'REAL_MODEL_SERVICE');
    const requestId = upstream.headers.get('x-request-id');
    if (requestId) responseHeaders.set('X-Request-ID', requestId);
    return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
  } catch (error) {
    if (error instanceof RangeError) return aiError(413, 'AI_UPLOAD_TOO_LARGE', 'Permintaan melebihi batas 10 MB.');
    const timeout = error instanceof Error && ['TimeoutError', 'AbortError'].includes(error.name);
    return aiError(timeout ? 504 : 503, timeout ? 'AI_TIMEOUT' : 'AI_SERVICE_UNAVAILABLE',
      timeout ? 'Analisis melewati batas waktu. Silakan coba lagi.' : 'AI Service tidak tersambung. Jalankan layanan AI terlebih dahulu.');
  }
}
