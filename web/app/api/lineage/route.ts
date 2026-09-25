import { forward } from '@/lib/server/proxy';

export const dynamic = 'force-dynamic';

export const POST = forward('/lineage', { graph: 'string' });
