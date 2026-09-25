// The record's three questions and its chain status. Proxied for every persona:
// whether the caller may read the record is the resolver's decision (OPA, rule in
// barriers.yaml), not this screen's. docs/decisions/0018.

import { NextResponse } from 'next/server';
import { forward } from '@/lib/server/proxy';

export const dynamic = 'force-dynamic';

const ROUTES = {
  subject: forward('/audit/subject', { matter: 'string' }),
  person: forward('/audit/person', { person: 'string', since: 'string?', until: 'string?' }),
  trace: forward('/audit/trace', { trace: 'string' }),
  verify: forward('/audit/verify', {}),
} as const;

export async function POST(request: Request, context: { params: Promise<{ kind: string }> }) {
  const { kind } = await context.params;
  const handler = ROUTES[kind as keyof typeof ROUTES];
  if (!handler) return NextResponse.json({ outcome: 'not-found' }, { status: 404 });
  return handler(request);
}
