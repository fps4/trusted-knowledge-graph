import { forward } from '@/lib/server/proxy';

export const dynamic = 'force-dynamic';

export const POST = forward('/ask', { template_id: 'string', slots: 'record', terms: 'strings' });
