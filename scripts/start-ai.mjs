import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const service = resolve(root, 'ai-service');
const python = process.env.FISCYCLE_AI_PYTHON || resolve(service, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
if (!existsSync(python)) {
  console.error('Environment AI belum tersedia. Ikuti docs/AI_INTEGRATION.md untuk membuat ai-service/.venv dengan Python 3.13.');
  process.exit(1);
}
const env = { ...process.env, FISCYCLE_MODEL_SOURCE: 'local' };
delete env.FISCYCLE_SKIP_REGISTRY_BOOTSTRAP;
delete env.FISCYCLE_LOCAL_MODEL_PATH;
delete env.FISCYCLE_MODEL_REGISTRY;
delete env.FISCYCLE_WATER_ROOT;
delete env.FISCYCLE_BSF_ROOT;
if (env.FISCYCLE_WATER_REPLAY_CSV) env.FISCYCLE_WATER_REPLAY_CSV = resolve(root, env.FISCYCLE_WATER_REPLAY_CSV);
if (env.FISCYCLE_AI_API_KEY) env.FISCYCLE_AI_SERVICE_TOKEN = env.FISCYCLE_AI_API_KEY;
const address = new URL(env.FISCYCLE_AI_API_URL || 'http://127.0.0.1:8001');
if (!['127.0.0.1', 'localhost'].includes(address.hostname)) {
  console.error('ai:dev hanya menjalankan server lokal. Untuk layanan remote, jalankan frontend tanpa ai:dev.');
  process.exit(1);
}
const child = spawn(python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', address.port || '8001', '--workers', '1'],
  { cwd: service, env, stdio: 'inherit', windowsHide: true });
child.on('error', () => { console.error('Gagal menjalankan Python AI Service.'); process.exitCode = 1; });
child.on('exit', code => { process.exitCode = code ?? 1; });
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
