// Browser → this process's route handlers. Never the resolver, never a key.

import type { Answer, ChatEvent } from './types';

export async function post<T = Answer>(path: string, body: unknown = {}): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return (await response.json()) as T;
}

export async function get<T = Answer>(path: string): Promise<T> {
  const response = await fetch(path, { cache: 'no-store' });
  return (await response.json()) as T;
}

/** Read an NDJSON stream line by line. A malformed line is skipped, not fatal. */
export async function* readNdjson(response: Response): AsyncGenerator<ChatEvent> {
  if (!response.body) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let newline;
      while ((newline = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, newline).trim();
        buf = buf.slice(newline + 1);
        if (!line) continue;
        try {
          yield JSON.parse(line) as ChatEvent;
        } catch {
          /* skip a malformed line */
        }
      }
    }
    const tail = buf.trim();
    if (tail) {
      try {
        yield JSON.parse(tail) as ChatEvent;
      } catch {
        /* swallow */
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/** What the CLI calls the two provenance columns. */
export const COLUMN_LABELS: Record<string, string> = { g: 'source', fg: 'told in' };

export function isAsk(a: Answer | null | undefined): boolean {
  return !!a && (typeof a.route === 'object' || 'rows' in a || typeof a.template === 'string');
}
