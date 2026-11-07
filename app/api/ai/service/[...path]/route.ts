import { forwardAi } from '@/lib/ai/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 120;

async function handle(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  return forwardAi(request, path.join('/'));
}

export const GET = handle;
export const POST = handle;
