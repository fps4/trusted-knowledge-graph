import { forward } from '@/lib/server/proxy';

export const dynamic = 'force-dynamic';

export const POST = forward('/explain', { trace: 'string' });
