// The backend-for-frontend's only way out: the resolver, as this process's person.
//
// The process is started as one persona (TKG_PERSONA) with that persona's key and
// no other. It mints the same short-lived HS256 assertion the MCP container mints
// (src/tkg/identity.py): header kid = persona; claims persona, aud, iat, exp = iat+60.
// The browser never sees the key and never reaches the resolver. docs/decisions/0011
// and 0027.

import { readFileSync } from 'node:fs';
import { SignJWT } from 'jose';

const AUDIENCE = 'tkg-resolver';
const TTL_SECONDS = 60;
const KEY_FILE = process.env.TKG_PERSONA_KEY_FILE || '/run/secrets/persona.key';

export function persona(): string {
  return process.env.TKG_PERSONA || '';
}

function resolverUrl(): string {
  return (process.env.TKG_RESOLVER_URL || 'http://resolver:8080').replace(/\/$/, '');
}

let cachedKey: Uint8Array | null = null;

function key(): Uint8Array {
  if (cachedKey) return cachedKey;
  let text: string;
  try {
    text = readFileSync(KEY_FILE, 'utf8').trim();
  } catch {
    throw new IdentityUnavailable('no key file for this persona — is the secret mounted?');
  }
  if (text.length < 32) throw new IdentityUnavailable('key too short — run `make init`');
  cachedKey = new TextEncoder().encode(text);
  return cachedKey;
}

export class IdentityUnavailable extends Error {}

export async function mint(now: number = Date.now()): Promise<string> {
  const who = persona();
  if (!who) throw new IdentityUnavailable('TKG_PERSONA is not set');
  const issued = Math.floor(now / 1000);
  return new SignJWT({ persona: who })
    .setProtectedHeader({ alg: 'HS256', kid: who })
    .setAudience(AUDIENCE)
    .setIssuedAt(issued)
    .setExpirationTime(issued + TTL_SECONDS)
    .sign(key());
}

export type Json = Record<string, unknown> | unknown[];

/** Call the resolver as this persona. Mirrors the MCP server's call(): a refusal at
 *  the door (401) comes back as its body, and an unreachable resolver as an outcome. */
export async function call(method: 'GET' | 'POST', path: string, body?: unknown): Promise<Json> {
  let token: string;
  try {
    token = await mint();
  } catch (err) {
    return { outcome: 'unavailable', reason: (err as Error).message };
  }
  let response: Response;
  try {
    response = await fetch(resolverUrl() + path, {
      method,
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: method === 'POST' ? JSON.stringify(body ?? {}) : undefined,
      cache: 'no-store',
      signal: AbortSignal.timeout(60_000),
    });
  } catch (err) {
    return { outcome: 'unavailable', reason: `the resolver did not answer: ${(err as Error).message}` };
  }
  if (response.status === 401) {
    const detail = (await response.json().catch(() => ({}))) as { detail?: Json };
    return detail.detail ?? { outcome: 'refused-identity' };
  }
  if (!response.ok) {
    return { outcome: 'unavailable', reason: `the resolver answered ${response.status}` };
  }
  return (await response.json()) as Json;
}
