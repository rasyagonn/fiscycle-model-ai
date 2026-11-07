// Node 20+ main-backend example; credentials stay on the backend.
import { readFile } from 'node:fs/promises';
import { basename } from 'node:path';

function headers() {
  const service = process.env.FISCYCLE_AI_API_KEY;
  const proxy = process.env.FISCYCLE_HF_SPACE_TOKEN;
  if (!service) throw new Error('FISCYCLE_AI_API_KEY is required');
  return proxy
    ? { Authorization: `Bearer ${proxy}`, 'X-Fiscycle-Service-Token': service }
    : { Authorization: `Bearer ${service}` };
}

async function call(path, options) {
  const response = await fetch(`${process.env.FISCYCLE_AI_API_URL}${path}`, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(`${response.status}: ${payload.detail}; request_id=${payload.request_id}`);
  return payload;
}

export async function analyzePhoto(imagePath, mime = 'image/jpeg') {
  const form = new FormData();
  form.append('file', new Blob([await readFile(imagePath)], { type: mime }), basename(imagePath));
  return call('/api/v1/bsf/analyze-photo', {
    method: 'POST', headers: headers(), body: form, signal: AbortSignal.timeout(120000),
  });
}

export async function analyzeWater(recordedPayload) {
  return call('/api/v1/water/analyze', {
    method: 'POST', headers: { ...headers(), 'Content-Type': 'application/json' },
    body: JSON.stringify(recordedPayload), signal: AbortSignal.timeout(30000),
  });
}
