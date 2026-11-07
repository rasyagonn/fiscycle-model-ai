export async function GET(_request: Request, context: { params: Promise<{ pondId: string }> }) {
  const { pondId } = await context.params;
  return Response.json({ ok: false, code: 'MEASUREMENTS_REQUIRED', pondId,
    message: 'Analisis memerlukan riwayat pengukuran. ID kolam demo tidak dipetakan ke dataset historis.',
    analysisPath: '/api/ai/service/api/v1/water/analyze', workspacePath: '/mitra/ai' },
    { status: 409, headers: { 'Cache-Control': 'no-store' } });
}
