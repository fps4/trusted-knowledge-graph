import { NextResponse } from 'next/server';
import { call } from '@/lib/server/resolver';

export const dynamic = 'force-dynamic';

export async function GET() {
  return NextResponse.json(await call('GET', '/templates'));
}
