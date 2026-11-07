// Actual Next.js -> FastAPI -> frozen-model smoke checks. No mocked predictions.
import assert from 'node:assert/strict';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const base = process.env.FISCYCLE_AI_TEST_URL || 'http://127.0.0.1:3000';
const prefix = '/api/ai/service/';
const checks = [];
async function check(label, task) { await task(); checks.push({ check: label, status: 'PASS' }); console.log('PASS', label); }
async function request(path, init) { return fetch(base+path, { ...init, signal: AbortSignal.timeout(120_000) }); }
async function json(path, init) { const r = await request(path, init); assert.equal(r.status, 200, path+': HTTP '+r.status); return r.json(); }
const post = (value) => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) });
const close = (a,b,tolerance=1e-4) => assert.ok(typeof a === 'number' && Math.abs(a-b) <= tolerance);
const golden = JSON.parse(await readFile(resolve(root,'ai-service/tests/fixtures/golden_reference.json')));
const meta = JSON.parse(await readFile(resolve(root,'ai-service/tests/fixtures/fixture_metadata.json')));
const a1 = await readFile(resolve(root,'ai-service/tests/fixtures/a1_development_train.jpg'));
const a2 = await readFile(resolve(root,'ai-service/tests/fixtures/a2_development_train.jpg'));
const raw = (body) => ({ method: 'POST', headers: { 'Content-Type': 'image/jpeg' }, body });
let gallery;

await check('Health: four verified local models through Next.js', async () => {
  const health = await json(prefix+'health'); assert.equal(health.ready,true);
  assert.equal(Object.keys(health.runtime_models).length,4);
  assert.ok(Object.values(health.runtime_models).every(m => m.loaded && m.artifacts_verified && m.model_source === 'local'));
});
await check('Bridge health has real readiness, no invented fallback', async () => {
  const data = await json('/api/ai/bridge'); assert.equal(data.ok,true); assert.equal(data.mode,'MODEL_SERVICE');
});
await check('A1 real raw-image inference equals golden', async () => {
  const result = await json(prefix+'api/v1/bsf/segment',raw(a1)); assert.equal(result.visible_instance_count,golden.a1_visible_instance_count);
});
await check('A1 multipart upload preserved', async () => {
  const form = new FormData();form.set('file',new Blob([a1],{type:'image/jpeg'}),'dev.jpg');
  assert.equal((await json(prefix+'api/v1/bsf/segment',{method:'POST',body:form})).visible_instance_count,golden.a1_visible_instance_count);
});
await check('A2 exact v3 preprocessing/weight through proxy', async () => {
  const q = new URLSearchParams(Object.fromEntries(['x0','y0','x1','y1'].map((k,i)=>[k,String(meta.a2.roi_bbox[i])])));q.set('reviewed_roi','true');
  const result = await json(prefix+'api/v1/bsf/estimate-weight?'+q,raw(a2));close(result.predicted_measured_weight_mg,golden.a2_predicted_measured_weight_mg);
});
await check('A1 to A2 real orchestration preserves scientific abstention', async () => {
  const r = await json(prefix+'api/v1/bsf/analyze-photo',raw(a1));assert.ok(r.summary.analyzed > 0);assert.equal(r.decision_support.status,'ABSTAIN_OPERATIONAL');assert.equal(r.b1_link,'NOT_USED_NOT_SCIENTIFICALLY_VALIDATED');
});
await check('B1 frozen estimator numeric golden', async () => {
  const data = await json(prefix+'api/v1/bsf/forecast',post({...golden.b1_features,input_provenance:'SYNTHETIC_SCENARIO'}));close(data.predicted_next_weight_mg,golden.b1_predicted_next_weight_mg,1e-8);
});
await check('Legacy bridge forwards actual model, does not generate predictions', async () => {
  const result = await json('/api/ai/bridge',post({domain:'bsf_b1',payload:{...golden.b1_features,input_provenance:'SYNTHETIC_SCENARIO'}}));close(result.predicted_next_weight_mg,golden.b1_predicted_next_weight_mg,1e-8);
  assert.equal((await request('/api/ai/bridge',post({domain:'bsf_b1',payload:{}}))).status,422);
});
await check('B1 development replay and DSS', async () => {
  const list = await json(prefix+'api/v1/bsf/replay/trajectories');assert.equal(list.trajectories.length,16);
  const trajectory_id = list.trajectories[0].trajectory_id;
  const replay = await json(prefix+'api/v1/bsf/replay/'+trajectory_id+'?revealed=6');assert.equal(replay.independent_validation,false);assert.equal(replay.revealed,6);assert.ok(replay.forecast.result.predicted_next_weight_mg !== null);
  const dss = await json(prefix+'api/v1/bsf/decision-support',post({data_mode:'HISTORICAL_RESEARCH',trajectory_id,revealed:6}));assert.equal(dss.decision_status,'ABSTAIN_OPERATIONAL');assert.ok(dss.factors.length>0 && dss.triggered_rule_ids.length>0);
});
await check('Curated gallery contains exactly 16 approved images', async () => {
  gallery = await json(prefix+'api/v1/bsf/demo-gallery');assert.equal(gallery.total,16);assert.equal(gallery.items.filter(r=>r.track==='A1').length,8);
});
for (const track of ['A1','A2']) await check(track+' gallery original bytes and actual inference', async () => {
  const row = gallery.items.find(r=>r.track===track);
  const image = await request(prefix+row.content_url.slice(1));assert.equal(image.status,200);
  assert.equal(createHash('sha256').update(Buffer.from(await image.arrayBuffer())).digest('hex'),row.sha256);
  const r = await json(prefix+'api/v1/bsf/demo-gallery/'+row.id+'/analyze',{method:'POST'});assert.ok(['SUCCESS','PARTIAL','REJECTED'].includes(r.inference_status));assert.ok(r.status.includes('NOT_FIELD_VALIDATED'));
});
await check('Input validation preserves errors rather than fallback success', async () => {
  assert.equal((await request(prefix+'api/v1/water/analyze',post({}))).status,422);
  assert.equal((await request(prefix+'api/v1/bsf/segment',raw(Buffer.from('bad')))).status,422);
  assert.equal((await request(prefix+'api/v1/bsf/estimate-weight?x0=0&y0=0&x1=100&y1=100&reviewed_roi=false',raw(a2))).status,422);
  for (const domain of ['__proto__','constructor',null,{},'unsupported']) {
    assert.equal((await request('/api/ai/bridge',post({domain,payload:{}}))).status,400);
  }
});
await check('Allowlist rejects arbitrary paths and outbound target injection', async () => {
  assert.equal((await request(prefix+'private/config')).status,404);
  assert.equal((await request(prefix+'api/v1/bsf/demo-gallery/not-a-photo/content')).status,404);
});
await check('Oversize upload and cross-origin mutation rejected', async () => {
  assert.equal((await request(prefix+'api/v1/bsf/segment',raw(Buffer.alloc(10*1024*1024+1)))).status,413);
  assert.equal((await request(prefix+'api/v1/bsf/forecast',{...post({}),headers:{'Content-Type':'application/json',Origin:'https://untrusted.invalid'}})).status,403);
});
await check('Browser bearer cannot replace server credential', async () => {
  const r = await request(prefix+'api/v1/models',{headers:{Authorization:'Bearer incorrect-browser-token'}});assert.equal(r.status,200);
});
await check('AI history contains actual analysis traces', async () => {
  const history = await json(prefix+'api/v1/bsf/history');assert.ok(history.records.length>0);assert.ok(history.records[0].result.calculation_model_trace);
});
await check('Demo pond ID does not impersonate local sensor dataset', async () => {
  const r = await request('/api/ai/recommend/POND-02');assert.equal(r.status,409);assert.equal((await r.json()).code,'MEASUREMENTS_REQUIRED');
});
await check('Existing telemetry and business matching stay explicitly simulated', async () => {
  const telemetry = await json('/api/iot/telemetry?pondId=POND-02');assert.equal(telemetry.live_sensor_connected,false);assert.equal(telemetry.provenance,'SIMULATED_APPLICATION_SEED');
  const matching = await json('/api/ai/match-supply',post({orderId:'ORD-0241'}));assert.equal(matching.mode,'BUSINESS_RULE_DEMO');assert.equal(matching.model_inference,false);assert.ok(matching.recommendations.length>0);
});
const privateCsv = process.env.FISCYCLE_WATER_REPLAY_CSV;
if (!privateCsv) throw new Error('Set FISCYCLE_WATER_REPLAY_CSV agar tes Water tidak dilewati.');
const reference = JSON.parse(await readFile(resolve(root,dirname(privateCsv),'water_reference.json')));
await check('Water nine predictions match frozen golden through Next.js', async () => {
  const r = await json(prefix+'api/v1/water/analyze',post(reference.input));
  for (const [p,hs] of Object.entries(r.forecasts)) for (const [h,f] of Object.entries(hs)) close(f.value,reference.expected_forecasts[p][h].value,1e-8);
  assert.equal(r.decision_support.traces.length,6);assert.equal(r.independent_validation,false);
});
await check('Private Water replay and matched baseline metrics', async () => {
  const periods = await json(prefix+'api/v1/water/replay/periods');const p = periods.periods[0];
  const made = await request(prefix+'api/v1/water/replay/sessions',post({start:p.start,end:p.end,pond_id:p.pond_id}));assert.equal(made.status,201);
  const session = await made.json();const advanced = await json(prefix+'api/v1/water/replay/sessions/'+session.session_id+'/advance?steps=55',{method:'POST'});
  assert.equal(advanced.metrics.rows.length,9);assert.ok(advanced.metrics.rows.every(r=>r.matched>0 && r.persistence_same_pairs.mae!==null));
});
await check('Water history and schema stay available through same-origin API', async () => {
  assert.ok((await json(prefix+'api/v1/water/history')).records.length>0);
  const schema=await json(prefix+'openapi.json');assert.ok(schema.paths['/api/v1/bsf/estimate-weight']);
});
const report = {status:'PASS',scope:'ACTUAL_NEXTJS_TO_FASTAPI_TO_LOCAL_MODELS',checks,remote_deployment:false};
const output = resolve(root,'ai-service/.cache/MAIN_INTEGRATION_HTTP.json');await mkdir(dirname(output),{recursive:true});await writeFile(output,JSON.stringify(report,null,2)+'\n');
console.log('PASS',checks.length,'actual integrated HTTP checks');
