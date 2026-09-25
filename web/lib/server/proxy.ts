// Route-handler helpers. Each proxied route forwards a fixed set of fields to one
// resolver endpoint, as this persona. Nothing takes a persona, and there is no
// route that turns an identifier into document bytes. docs/decisions/0021, 0027.

import { NextResponse } from 'next/server';
import { call } from './resolver';

type Shape = Record<string, 'string' | 'string?' | 'text' | 'strings' | 'record'>;

/** Keep only the declared fields, of the declared types; drop everything else. */
export function pick(raw: unknown, shape: Shape): Record<string, unknown> | string {
  const body = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
  const out: Record<string, unknown> = {};
  for (const [name, kind] of Object.entries(shape)) {
    const v = body[name];
    if (kind === 'string') {
      if (typeof v !== 'string') return `${name}: expected a string`;
      out[name] = v;
    } else if (kind === 'string?') {
      if (v === undefined || v === null || v === '') out[name] = null;
      else if (typeof v === 'string') out[name] = v;
      else return `${name}: expected a string`;
    } else if (kind === 'text') {
      out[name] = typeof v === 'string' ? v : '';
    } else if (kind === 'strings') {
      out[name] = Array.isArray(v) ? v.filter((x) => typeof x === 'string') : [];
    } else if (kind === 'record') {
      const rec: Record<string, string> = {};
      if (v && typeof v === 'object' && !Array.isArray(v)) {
        for (const [k, x] of Object.entries(v)) if (typeof x === 'string' && x !== '') rec[k] = x;
      }
      out[name] = rec;
    }
  }
  return out;
}

export function forward(path: string, shape: Shape) {
  return async function POST(request: Request) {
    const body = pick(await request.json().catch(() => ({})), shape);
    if (typeof body === 'string') {
      return NextResponse.json({ outcome: 'refused-invalid', reason: body }, { status: 400 });
    }
    return NextResponse.json(await call('POST', path, body));
  };
}
