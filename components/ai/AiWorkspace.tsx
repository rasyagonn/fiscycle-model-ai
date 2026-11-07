'use client';

/* eslint-disable @next/next/no-img-element -- Original proxied images and scientific base64 previews must not be resized by Next Image. */
import { useEffect, useState, type ReactNode } from 'react';
import { Activity, Camera, History, RefreshCw, Waves } from 'lucide-react';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { AI_PROXY, aiRequest, aiPost, type JsonObject, type Health, type GalleryImage,
  type Period, type Trajectory, type BsfReplay, type WaterReplay, type WaterResult } from '@/lib/ai/service-client';

const button = 'inline-flex items-center justify-center gap-2 rounded-xl bg-[#00629B] px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-40 disabled:cursor-not-allowed hover:bg-[#1A365D]';
const field = 'w-full min-w-0 rounded-xl border border-[#d5e3ec] bg-white px-3 py-2.5 text-sm text-[#173251]';
const labels: Record<string, string> = { ph: 'pH', temperature_c: 'Suhu (°C)', turbidity_ntu: 'Kekeruhan (NTU)',
  A1_SEGMENT: 'Segmentasi A1', A2_WEIGHT: 'Estimasi berat A2', A1_A2_PHOTO: 'Analisis foto A1 → A2',
  B1_FORECAST: 'Prediksi pertumbuhan B1', DSS_DECISION: 'Penjelasan DSS', CURATED_DEMO_ANALYSIS: 'Analisis foto demo',
  WATER_ANALYSIS: 'Analisis Water', SYNTHETIC_SCENARIO: 'Skenario simulasi', HISTORICAL_RESEARCH: 'Penelitian historis',
  RULE_DERIVED: 'Hasil aturan', SIMULATED: 'Simulasi', USER_ENTERED: 'Masukan pengguna' };
const name = (value: string) => labels[value] || value;
const num = (value: unknown, digits = 2) => typeof value === 'number' && Number.isFinite(value)
  ? value.toLocaleString('id-ID', { maximumFractionDigits: digits }) : '—';
const obj = (value: unknown): JsonObject => value && typeof value === 'object' && !Array.isArray(value) ? value as JsonObject : {};
const list = (value: unknown): unknown[] => Array.isArray(value) ? value : [];
const text = (value: unknown): string => typeof value === 'string' ? value : '';

function Card({ title, children }: { title: string; children: ReactNode }) {
  return <section className="min-w-0 rounded-3xl border border-[#e7eff4] bg-white p-4 shadow-sm sm:p-6">
    <h2 className="mb-4 text-lg font-bold text-[#1A365D]">{title}</h2>{children}</section>;
}
function Failure({ error }: { error: string }) {
  return error ? <p role="alert" className="my-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{error}</p> : null;
}
function useTask() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function run(task: () => Promise<void>) {
    setBusy(true); setError('');
    try { await task(); } catch (e) { setError(e instanceof Error ? e.message : 'Permintaan gagal.'); }
    finally { setBusy(false); }
  }
  return { busy, error, run };
}
function Stat({ title, value }: { title: string; value: ReactNode }) {
  return <div className="min-w-0 rounded-2xl bg-[#f3f9fc] p-3"><p className="text-xs text-slate-600">{title}</p>
    <p className="mt-1 break-words text-lg font-bold text-[#1A365D]">{value}</p></div>;
}

function Explain({ data }: { data: JsonObject }) {
  const recommendations = list(data.recommendations);
  const traces = list(data.traces);
  const factors = list(data.factors);
  return <div className="space-y-3 text-sm">
    <p>{text(data.assessment) || text(data.explanation) || 'Aturan meminta pemeriksaan dan konfirmasi manusia.'}</p>
    <p className="rounded-xl bg-amber-50 p-3 text-amber-900">DSS belum mengesahkan tindakan budidaya otomatis. Ambang biologis, kalibrasi, dan kondisi lapangan perlu verifikasi manusia.</p>
    {recommendations.map((item, i) => { const row = obj(item); return <article key={i} className="rounded-xl border border-[#e7eff4] p-3">
      <h3 className="font-semibold">{typeof item === 'string' ? item : text(row.title) || text(row.action) || 'Perlu diperiksa'}</h3>
      <p className="mt-1 text-slate-600">{text(row.summary) || text(row.explanation)}</p>
      {list(row.recommended_actions).map((action, j) => <p key={j} className="mt-1">• {text(action)}</p>)}
      {row.evidence_references != null && <details className="mt-2"><summary className="cursor-pointer text-[#00629B]">Sumber dan keterbatasan aturan</summary>
        {list(row.evidence_references).map((e, j) => <p key={j} className="mt-2 break-words text-xs">{typeof e === 'string' ? e : Object.values(obj(e)).filter(v => typeof v === 'string').join(' · ')}</p>)}
        <p className="mt-2 text-xs">{text(row.limitations)}</p></details>}
    </article>; })}
    {traces.length > 0 && <details><summary className="cursor-pointer font-semibold text-[#00629B]">Penelusuran aturan ({traces.length})</summary>
      {traces.map((v, i) => { const r = obj(v); return <div key={i} className="mt-2 rounded-xl bg-slate-50 p-3">
        <p className="font-semibold">{text(r.id) || text(r.rule_id)} · {r.triggered ? 'Terpicu' : 'Tidak terpicu'}</p>
        <p className="mt-1">{text(r.condition) || text(r.action) || text(r.name)}</p>
        <p className="mt-1 text-xs text-slate-600">Sumber: {text(r.evidence) || 'Kontrak inferensi dan aturan versi yang tercatat'}</p>
      </div>; })}</details>}
    {factors.length > 0 && <details><summary className="cursor-pointer font-semibold text-[#00629B]">Faktor dan asal data ({factors.length})</summary>
      <div className="mt-2 space-y-2">{factors.map((v, i) => { const f = obj(v); return <p key={i} className="rounded-xl bg-slate-50 p-3">
        <b>{text(f.name)}</b>: {f.current_value == null ? 'Belum tersedia' : typeof f.current_value === 'number' ? num(f.current_value) : String(f.current_value)} {text(f.unit)}
        <span className="block text-xs text-slate-600">Asal: {name(text(f.data_source))} · {text(f.availability)}</span></p>; })}</div></details>}
  </div>;
}

function PhotoResult({ result }: { result: JsonObject }) {
  const summary = obj(result.summary);
  const image = text(result.overlay_png_base64) || text(result.processed_png_base64);
  const estimated = result.predicted_measured_weight_mg ?? result.predicted_weight_mg ?? summary.mean_estimated_weight_mg;
  const processLabels: Record<string, string> = { SUCCESS: 'Berhasil', PARTIAL: 'Sebagian dianalisis', REJECTED: 'Ditolak' };
  const rejectionLabels: Record<string, string> = { SHORTCUT_SCREEN: 'ROI diduga memuat penanda/tulisan; perlu ditinjau.',
    SOURCE_EDGE_CONTACT: 'ROI bersentuhan dengan batas foto.', NO_CANDIDATE: 'ROI belum ditemukan.',
    OUT_OF_BOUNDS: 'Koordinat ROI melampaui foto.', FULL_ROI_EXCEEDS_TRAIN_SELECTED_CANVAS: 'ROI melebihi ukuran kanvas yang didukung.',
    INVALID_MODEL_WEIGHT: 'Prediksi berat tidak valid.' };
  return <div data-testid="photo-result" className="mt-4 space-y-4">
    <div className="grid grid-cols-2 gap-3">
      <Stat title="Larva terlihat terdeteksi" value={num(result.visible_instance_count ?? summary.detected, 0)} />
      <Stat title="Estimasi berat per larva (mg)" value={num(estimated)} />
      {result.reference_measured_weight_mg != null && <Stat title="Berat referensi terukur (mg)" value={num(result.reference_measured_weight_mg)} />}
      {summary.rejected != null && <Stat title="Larva tidak dianalisis / ditolak" value={num(summary.rejected, 0)} />}
    </div>
    {result.inference_status != null && <p className="text-sm font-semibold">Status proses: {processLabels[text(result.inference_status)] || text(result.inference_status)} ({text(result.inference_status)}) {rejectionLabels[text(result.rejection_reason)] || text(result.rejection_reason)}</p>}
    {image && <img alt="Hasil segmentasi atau preprocessing dari model" src={'data:image/png;base64,'+image} className="max-h-96 w-full rounded-2xl bg-slate-50 object-contain" />}
    <p className="text-xs text-slate-600">Prediksi AI · berat basah/kering belum terkonfirmasi · piksel bukan milimeter. Jumlah terdeteksi bukan jumlah seluruh populasi; massa terlihat bukan biomassa batch.</p>
    {result.decision_support != null && <Explain data={obj(result.decision_support)} />}
  </div>;
}

function Photos() {
  const [images, setImages] = useState<GalleryImage[]>([]);
  const [track, setTrack] = useState('A1');
  const [result, setResult] = useState<JsonObject | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [pipeline, setPipeline] = useState('analyze-photo');
  const [roi, setRoi] = useState(['', '', '', '']);
  const [reviewed, setReviewed] = useState(false);
  const task = useTask();
  const [loadError, setLoadError] = useState('');
  useEffect(() => { aiRequest<{ items: GalleryImage[] }>('api/v1/bsf/demo-gallery').then(d => setImages(d.items)).catch(e => setLoadError(e.message)); }, []);
  async function analyze(id: string) {
    await task.run(async () => { setResult(null); setResult(await aiRequest('api/v1/bsf/demo-gallery/'+id+'/analyze', { method: 'POST' })); });
  }
  return <div className="space-y-5"><Card title="Analisis foto BSF — A1 dan A2 v3">
    <p className="mb-4 text-sm text-slate-600">8 foto A1 pilihan pengguna dan 8 foto A2 acak dari penelitian publik. Data final sudah dilepas; galeri bukan uji blind atau bukti akurasi baru.</p>
    <p className="mb-4 text-xs text-slate-600">Sumber foto: <a className="underline" href="https://doi.org/10.5281/zenodo.13359376" target="_blank" rel="noreferrer">dataset publik Zenodo</a> · lisensi CC BY 4.0.</p>
    <div className="mb-4 flex gap-2">{['A1', 'A2'].map(t => <button key={t} className={button} aria-pressed={track === t} onClick={() => setTrack(t)}>{t === 'A1' ? 'A1 · Banyak larva' : 'A2 · Satu larva'}</button>)}</div>
    <Failure error={loadError} />
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{images.filter(i => i.track === track).map((image, i) => <button key={image.id} disabled={task.busy} onClick={() => analyze(image.id)} className="min-w-0 rounded-2xl border border-[#e7eff4] p-2 text-left hover:border-[#00B4D8] disabled:opacity-40" aria-label={`Analisis foto ${image.track} nomor ${i+1}`}>
      <img src={AI_PROXY+image.thumbnail_url.slice(1)} alt={`Foto penelitian ${image.track} nomor ${i+1}`} loading="lazy" className="aspect-square w-full rounded-xl bg-slate-50 object-contain" />
      <span className="mt-2 block text-xs font-semibold">Foto {i+1} · {image.track}</span></button>)}</div>
    <Failure error={task.error} />{task.busy && <p role="status" className="mt-4 text-sm">Model sedang menganalisis foto…</p>}
    {result && <PhotoResult result={result} />}
  </Card><Card title="Unggah foto sendiri">
    <form className="space-y-3" onSubmit={event => { event.preventDefault(); void task.run(async () => {
      if (!file) throw new Error('Pilih foto terlebih dahulu.');
      if (file.size > 8 * 1024 * 1024) throw new Error('Ukuran foto maksimal 8 MB.');
      const query = pipeline === 'estimate-weight' ? '?'+new URLSearchParams({ x0: roi[0], y0: roi[1], x1: roi[2], y1: roi[3], reviewed_roi: String(reviewed) }) : '';
      const body = new FormData(); body.set('file', file);
      setResult(null); setResult(await aiRequest('api/v1/bsf/'+pipeline+query, { method: 'POST', body }));
    }); }}>
      <label className="block text-sm">Foto asli JPEG, PNG, atau WebP (maksimal 8 MB)<input aria-label="Foto BSF" type="file" accept="image/jpeg,image/png,image/webp" required className={field+' mt-1'} onChange={e => setFile(e.target.files?.[0] || null)} /></label>
      <label className="block text-sm">Analisis<select aria-label="Jenis analisis foto" className={field+' mt-1'} value={pipeline} onChange={e => setPipeline(e.target.value)}>
        <option value="analyze-photo">A1 → A2 · Eksperimen foto multi-larva</option><option value="segment">A1 · Segmentasi saja</option><option value="estimate-weight">A2 v3 · Satu larva dengan ROI ditinjau</option></select></label>
      {pipeline === 'estimate-weight' && <div className="space-y-3"><p className="text-xs text-slate-600">A2 memerlukan foto asli 4056 × 3040. Isi ROI piksel sumber yang memuat larva utuh tanpa tulisan; jangan resize foto.</p>
        <div className="grid grid-cols-2 gap-2">{['x0', 'y0', 'x1', 'y1'].map((label, i) => <label key={label} className="text-sm">{label}<input className={field} aria-label={'ROI '+label} type="number" min="0" step="1" required value={roi[i]} onChange={e => setRoi(v => v.map((n, j) => j === i ? e.target.value : n))} /></label>)}</div>
        <label className="flex gap-2 text-sm"><input type="checkbox" required checked={reviewed} onChange={e => setReviewed(e.target.checked)} />Saya meninjau ROI: larva utuh dan tanpa penanda tertulis.</label></div>}
      <button className={button} disabled={task.busy}>Jalankan analisis foto</button>
    </form>
  </Card></div>;
}

function ForecastTable({ result }: { result: WaterResult }) {
  return <div className="space-y-3"><p className="text-sm">Kualitas data: <b>{result.data_quality.status}</b>. DO dan TAN tidak tersedia.</p>
    {result.data_quality.reasons.length > 0 && <p className="break-words text-xs">Alasan: {result.data_quality.reasons.join(' · ')}</p>}
    <div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr><th className="p-2">Parameter</th><th>Terukur</th><th>+30 menit</th><th>+60 menit</th><th>+120 menit</th></tr></thead>
      <tbody>{Object.entries(result.forecasts).map(([p, forecasts]) => <tr key={p} className="border-t border-[#e7eff4]"><th className="p-2">{name(p)}</th><td>{num(result.current_readings[p])}</td>{['30','60','120'].map(h => <td key={h}>{num(forecasts[h]?.value)}</td>)}</tr>)}</tbody></table></div>
    <p className="text-xs text-slate-600">Kolom ke depan adalah prediksi. Tanda — berarti tidak tersedia atau model abstain; bukan nilai nol. Prediksi dapat memakai model ML atau baseline persistence sesuai kontrak.</p>
    <Explain data={result.decision_support} /></div>;
}

function Water() {
  const [periods, setPeriods] = useState<Period[]>([]);
  const [periodId, setPeriodId] = useState('');
  const [state, setState] = useState<WaterReplay | null>(null);
  const [parameter, setParameter] = useState('ph');
  const [loadError, setLoadError] = useState('');
  const [payload, setPayload] = useState('');
  const [manual, setManual] = useState<WaterResult | null>(null);
  const task = useTask();
  useEffect(() => { aiRequest<{ periods: Period[] }>('api/v1/water/replay/periods').then(d => { setPeriods(d.periods); setPeriodId(d.periods[0]?.id || ''); }).catch(e => setLoadError(e.message)); }, []);
  return <div className="space-y-5"><Card title="Water Quality — replay historis lokal">
    <p className="mb-3 text-sm text-slate-600">Rekaman lokal satu kolam · WIB · bukan sensor live. Pilihan periode berasal dari seed privat, tanpa pemetaan ke kolam demo aplikasi.</p>
    <Failure error={loadError} /><Failure error={task.error} />
    <label className="block text-sm">Periode rekaman<select className={field+' my-2'} aria-label="Periode Water" value={periodId} disabled={task.busy} onChange={e => { setPeriodId(e.target.value); setState(null); }}><option value="" disabled>Pilih periode</option>{periods.map(p => <option key={p.id} value={p.id}>{p.label} WIB</option>)}</select></label>
    <div className="my-3 flex flex-wrap gap-2"><button className={button} disabled={task.busy || !periodId} onClick={() => void task.run(async () => {
      const p = periods.find(p => p.id === periodId)!;
      setState(await aiPost<WaterReplay>('api/v1/water/replay/sessions', { start: p.start, end: p.end, pond_id: p.pond_id, ...(state ? { replace_session_id: state.session_id } : {}) }));
    })}>Mulai / ulang replay Water</button>
    <button className={button} disabled={task.busy || !state || state.finished} onClick={() => void task.run(async () => { setState(await aiRequest<WaterReplay>('api/v1/water/replay/sessions/'+state!.session_id+'/advance?steps=25', { method: 'POST' })); })}>Lanjutkan 25 observasi</button></div>
    {task.busy && <p role="status">Mengolah riwayat pengukuran…</p>}
    {state && <div className="space-y-4" data-testid="water-result"><p className="text-sm">{state.processed_observations}/{state.total_observations} observasi · {state.status}</p>
      <select aria-label="Parameter grafik Water" className={field} value={parameter} onChange={e => setParameter(e.target.value)}>{['ph','temperature_c','turbidity_ntu'].map(p => <option key={p} value={p}>{name(p)}</option>)}</select>
      <div className="h-52 w-full min-w-0"><ResponsiveContainer width="100%" height="100%"><LineChart data={state.observations.map(o => ({ ...o, time: o.timestamp.slice(11,16) }))}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="time" tick={{ fontSize: 10 }} /><YAxis domain={['auto','auto']} width={45} tick={{ fontSize: 10 }} /><Tooltip /><Line type="linear" dataKey={parameter} name={'Terukur · '+name(parameter)} stroke="#00629B" dot={false} connectNulls={false} /></LineChart></ResponsiveContainer></div>
      <p className="text-xs text-slate-600">Grafik pengukuran historis · sumbu waktu WIB</p>
      {state.latest_result && <ForecastTable result={state.latest_result} />}
      <details><summary className="cursor-pointer text-sm font-semibold text-[#00629B]">Galat pasangan replay dan baseline</summary><div className="overflow-x-auto"><table className="mt-3 w-full text-left text-xs"><thead><tr><th>Target</th><th>Pasangan</th><th>MAE prediksi</th><th>MAE persistence</th></tr></thead><tbody>{state.metrics.rows.map(r => <tr key={r.parameter+r.horizon_minutes} className="border-t"><td className="py-2">{name(r.parameter)} +{r.horizon_minutes}m</td><td>{r.matched}</td><td>{num(r.prediction.mae)}</td><td>{num(r.persistence_same_pairs.mae)}</td></tr>)}</tbody></table></div><p className="mt-2 text-xs">Evaluasi retrospektif pada pasangan waktu yang cocok; bukan validasi independen baru.</p></details>
    </div>}
  </Card><Card title="Analisis riwayat yang kamu kirim">
    <p className="mb-3 text-xs text-slate-600">Gunakan kontrak AnalyzeRequest di dokumentasi AI Service. Input harus memuat mode historical_replay, pond_id, current_timestamp WIB, dan readings. Riwayat yang belum cukup akan menghasilkan abstention.</p>
    <form onSubmit={e => { e.preventDefault(); void task.run(async () => { setManual(null); setManual(await aiPost<WaterResult>('api/v1/water/analyze', JSON.parse(payload))); }); }} className="space-y-3">
      <label className="block text-sm">JSON riwayat pengukuran<textarea aria-label="JSON riwayat Water" className={field+' mt-1 h-40 font-mono text-xs'} required value={payload} onChange={e => setPayload(e.target.value)} /></label>
      <button className={button} disabled={task.busy}>Analisis riwayat Water</button>
    </form>{manual && <div className="mt-4"><ForecastTable result={manual} /></div>}
  </Card></div>;
}

function Growth() {
  const [trajectories, setTrajectories] = useState<Trajectory[]>([]);
  const [id, setId] = useState('');
  const [replay, setReplay] = useState<BsfReplay | null>(null);
  const [loadError, setLoadError] = useState('');
  const [forecast, setForecast] = useState<JsonObject | null>(null);
  const [provenance, setProvenance] = useState('SYNTHETIC_SCENARIO');
  const fields = [['moisture_percent','Kelembapan substrat (%)'],['elapsed_days','Hari pengamatan'],['current_weight_mg','Rerata berat terukur saat ini (mg/individu)'],['previous_weight_mg','Rerata berat terukur sebelumnya (mg/individu)'],['recent_growth_mg_per_day','Pertumbuhan terakhir (mg/hari)'],['forecast_horizon_days','Horizon prediksi (hari)']];
  const [values, setValues] = useState<Record<string,string>>({});
  const task = useTask();
  useEffect(() => { aiRequest<{ trajectories: Trajectory[] }>('api/v1/bsf/replay/trajectories').then(d => { setTrajectories(d.trajectories); setId(d.trajectories[0]?.trajectory_id || ''); }).catch(e => setLoadError(e.message)); }, []);
  const rows: { day: number; measured?: number; predicted?: number | null }[] = replay?.observations.map(o => ({ day: o.day, measured: o.measured_weight_mg })) || [];
  if (replay?.forecast) rows.push({ day: replay.forecast.target_day, predicted: replay.forecast.result.predicted_next_weight_mg });
  async function load(revealed: number) { await task.run(async () => { setReplay(await aiRequest<BsfReplay>('api/v1/bsf/replay/'+encodeURIComponent(id)+'?revealed='+revealed)); }); }
  return <div className="space-y-5"><Card title="B1 — replay pertumbuhan historis">
    <p className="mb-3 text-sm text-slate-600">Data publik Mendeley · 16 trajektori development/in-sample. Prediksi rerata berat basah per individu untuk observasi berikutnya; bukan prediksi biomassa panen.</p>
    <p className="mb-3 text-xs text-slate-600">Sumber: <a className="underline" href="https://doi.org/10.17632/k435zc736t.1" target="_blank" rel="noreferrer">Mendeley Data v1</a> · lisensi CC BY 4.0.</p>
    <Failure error={loadError} /><Failure error={task.error} />
    <label className="text-sm">Trajektori penelitian<select aria-label="Trajektori B1" className={field+' my-2'} value={id} disabled={task.busy} onChange={e => { setId(e.target.value); setReplay(null); }}>{trajectories.map(t => <option key={t.trajectory_id} value={t.trajectory_id}>{t.trajectory_id} · Kelembapan {t.moisture_percent}%</option>)}</select></label>
    <div className="my-3 flex flex-wrap gap-2"><button className={button} disabled={task.busy || !id} onClick={() => void load(2)}>Buka replay B1</button><button className={button} disabled={task.busy || !replay || replay.revealed >= replay.total_observations} onClick={() => void load(replay!.revealed+1)}>Observasi berikutnya</button></div>
    {replay && <div className="space-y-3" data-testid="b1-result"><p className="text-sm">{replay.revealed}/{replay.total_observations} observasi terungkap</p>
      <Stat title="Prediksi B1 observasi berikutnya (mg/individu)" value={num(replay.forecast?.result.predicted_next_weight_mg)} />
      <div className="h-56 min-w-0"><ResponsiveContainer width="100%" height="100%"><LineChart data={rows}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="day" name="Hari" /><YAxis width={45} /><Tooltip /><Line dataKey="measured" name="Terukur (mg)" stroke="#00629B" /><Line dataKey="predicted" name="Prediksi B1 (mg)" stroke="#0F766E" dot={{ r: 5 }} /></LineChart></ResponsiveContainer></div>
      <p className="text-xs text-slate-600">Sumbu X: hari · Sumbu Y: mg/individu. {replay.limitation}</p></div>}
  </Card><Card title="B1 — masukan manual atau skenario">
    <form className="space-y-3" onSubmit={e => { e.preventDefault(); void task.run(async () => { setForecast(null); setForecast(await aiPost('api/v1/bsf/forecast', { input_provenance: provenance, ...Object.fromEntries(fields.map(([key]) => [key, Number(values[key])])) })); }); }}>
      <label className="block text-sm">Asal data<select aria-label="Asal data B1" className={field+' mt-1'} value={provenance} onChange={e => setProvenance(e.target.value)}><option value="SYNTHETIC_SCENARIO">Skenario simulasi (bukan pengukuran)</option><option value="USER_ENTERED_MEASURED_HISTORY">Riwayat terukur yang saya masukkan (belum diverifikasi)</option></select></label>
      <div className="grid gap-3 sm:grid-cols-2">{fields.map(([key,label]) => <label key={key} className="text-sm">{label}<input aria-label={label} className={field+' mt-1'} type="number" step="any" required value={values[key] || ''} onChange={e => setValues(v => ({ ...v, [key]: e.target.value }))} /></label>)}</div>
      <button className={button} disabled={task.busy}>Prediksi B1</button>
    </form>{forecast && <div className="mt-4"><Stat title="Prediksi rerata berat berikutnya (mg/individu)" value={num(forecast.predicted_next_weight_mg)} /><p className="mt-2 text-xs">Asal input: {provenance === 'SYNTHETIC_SCENARIO' ? 'Simulasi' : 'Pengukuran dinyatakan pengguna; belum diverifikasi'}. Tidak memakai hasil A2 secara otomatis.</p></div>}
  </Card></div>;
}

function Decisions() {
  const [trajectories, setTrajectories] = useState<Trajectory[]>([]);
  const [id, setId] = useState('');
  const [result, setResult] = useState<JsonObject | null>(null);
  const task = useTask();
  const [loadError, setLoadError] = useState('');
  useEffect(() => { aiRequest<{ trajectories: Trajectory[] }>('api/v1/bsf/replay/trajectories').then(d => { setTrajectories(d.trajectories); setId(d.trajectories[0]?.trajectory_id || ''); }).catch(e => setLoadError(e.message)); }, []);
  return <Card title="DSS — alasan dan asal data">
    <p className="mb-4 text-sm text-slate-600">Penilaian aturan dari enam observasi historis pertama pada trajektori pilihan. DSS Water juga ditampilkan bersama hasil replay Water.</p>
    <Failure error={loadError} /><Failure error={task.error} />
    <label className="block text-sm">Sumber riwayat<select aria-label="Trajektori DSS" className={field+' my-2'} disabled={task.busy} value={id} onChange={e => { setId(e.target.value); setResult(null); }}>{trajectories.map(t => <option key={t.trajectory_id} value={t.trajectory_id}>{t.trajectory_id}</option>)}</select></label>
    <button className={button} disabled={task.busy || !id} onClick={() => void task.run(async () => { setResult(null); setResult(await aiPost('api/v1/bsf/decision-support', { data_mode: 'HISTORICAL_RESEARCH', trajectory_id: id, revealed: 6 })); })}>Jelaskan penilaian DSS</button>
    {result && <div className="mt-4" data-testid="dss-result"><Explain data={result} /></div>}
  </Card>;
}

function AnalysisHistory() {
  const [domain, setDomain] = useState('bsf');
  const [records, setRecords] = useState<{ id: number; kind: string; provenance: string; created_at_wib: string; result: JsonObject }[]>([]);
  const task = useTask();
  return <Card title="Riwayat analisis AI">
    <p className="mb-3 text-sm text-slate-600">Jejak hasil di layanan AI dengan versi perhitungan aslinya. Riwayat bisnis dan kepemilikan data tetap dikelola backend utama.</p>
    <div className="flex flex-wrap gap-2"><select aria-label="Domain riwayat" className={field+' sm:w-auto'} value={domain} onChange={e => { setDomain(e.target.value); setRecords([]); }}><option value="bsf">Smart BSF</option><option value="water">Water Quality</option></select>
      <button className={button} disabled={task.busy} onClick={() => void task.run(async () => { const data = await aiRequest<{ records: typeof records }>('api/v1/'+domain+'/history?limit=30'); setRecords(data.records); })}><RefreshCw size={16} />Muat riwayat</button></div>
    <Failure error={task.error} />
    <div className="mt-4 space-y-3">{records.map(row => <details key={row.id} className="rounded-2xl border border-[#e7eff4] p-3"><summary className="cursor-pointer text-sm"><b>{name(row.kind)} #{row.id}</b><span className="mt-1 block text-xs text-slate-600">{row.created_at_wib.replace('T',' ').slice(0,19)} WIB · {name(row.provenance)}</span></summary>
      <div className="mt-3">{row.kind === 'WATER_ANALYSIS' ? <ForecastTable result={row.result as unknown as WaterResult} /> : row.kind === 'DSS_DECISION' ? <Explain data={row.result} /> : row.kind === 'B1_FORECAST' ? <Stat title="Prediksi B1 (mg/individu)" value={num(row.result.predicted_next_weight_mg ?? obj(row.result.forecast).predicted_next_weight_mg)} /> : <PhotoResult result={row.result} />}</div>
    </details>)}</div>
  </Card>;
}

export default function AiWorkspace() {
  const [tab, setTab] = useState('water');
  const [health, setHealth] = useState<Health | null>(null);
  const task = useTask();
  useEffect(() => { aiRequest<Health>('health').then(setHealth).catch(() => setHealth(null)); }, []);
  const tabs = [['water','Water Quality'],['photo','Analisis foto'],['growth','Pertumbuhan BSF'],['dss','Penjelasan DSS'],['history','Riwayat']];
  return <div className="mx-auto w-full max-w-6xl min-w-0 space-y-5 p-4 pb-28 text-[#173251] sm:p-6">
    <header className="rounded-3xl bg-[#1A365D] p-5 text-white sm:p-7"><div className="flex items-center gap-2"><Activity size={24} /><h1 className="text-2xl font-bold">Pusat AI Fiscycle</h1></div>
      <p className="mt-2 text-sm text-sky-100">Water Quality dan Smart BSF · model riset asli · sumber data terlihat.</p>
      <p className="mt-3 text-xs text-sky-100">Prototipe riset · belum divalidasi di lapangan. Data historis, prediksi, dan simulasi ditampilkan terpisah.</p></header>
    <div className="rounded-3xl border border-[#e7eff4] bg-white p-4"><div className="flex flex-wrap items-center justify-between gap-3"><p className="text-sm font-semibold" data-testid="ai-status">{health?.ready ? 'AI Service tersambung' : 'Status AI belum siap / belum tersambung'}</p>
      <button className={button} disabled={task.busy} onClick={() => void task.run(async () => { setHealth(null); setHealth(await aiRequest<Health>('health')); })}><RefreshCw size={16} />Cek koneksi</button></div>
      <Failure error={task.error} /><div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">{['water','bsf_a1','bsf_a2','bsf_b1'].map(k => <p key={k} className="rounded-xl bg-[#f3f9fc] p-2 text-xs"><b>{({water:'Water',bsf_a1:'A1',bsf_a2:'A2 v3',bsf_b1:'B1'} as Record<string,string>)[k]}</b><span className="mt-1 block">{health?.runtime_models[k]?.loaded && health.runtime_models[k]?.artifacts_verified ? 'Model terverifikasi dan dimuat' : 'Belum terverifikasi / belum dimuat'}</span></p>)}</div></div>
    <nav aria-label="Fitur AI" className="flex flex-wrap gap-2 rounded-2xl bg-white/70 p-2 backdrop-blur-xl">{tabs.map(([key,label]) => <button key={key} aria-pressed={tab === key} className={'rounded-xl px-3 py-2.5 text-sm font-semibold '+(tab === key ? 'bg-[#00629B] text-white' : 'text-[#173251] hover:bg-sky-50')} onClick={() => setTab(key)}>{key === 'water' ? <Waves className="mr-1 inline" size={14} /> : key === 'photo' ? <Camera className="mr-1 inline" size={14} /> : key === 'history' ? <History className="mr-1 inline" size={14} /> : null}{label}</button>)}</nav>
    <div hidden={tab !== 'water'}><Water /></div><div hidden={tab !== 'photo'}><Photos /></div><div hidden={tab !== 'growth'}><Growth /></div><div hidden={tab !== 'dss'}><Decisions /></div><div hidden={tab !== 'history'}><AnalysisHistory /></div>
  </div>;
}
