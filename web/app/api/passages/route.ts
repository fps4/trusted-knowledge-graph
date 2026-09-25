import { forward } from '@/lib/server/proxy';

export const dynamic = 'force-dynamic';

export const POST = forward('/passages', { permit: 'string', text: 'text' });
