'use client';

import * as React from 'react';
import { ExternalLink } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { OutcomeBadge } from '@/components/outcome';
import { Empty, Mono, TUNNEL_NOTE } from '@/components/inspector/parts';
import { post } from '@/lib/client';
import type { Answer } from '@/lib/types';

type Source = { document: string; key: string; url: string; expires: string };
type Passage = {
  chunk_id: string;
  doc_id: string;
  matter_id: string;
  doc_type: string;
  text: string;
  source_url?: string;
};

export function SourcesPanel({ answer }: { answer: Answer }) {
  const sources = (answer.sources as Source[] | undefined) ?? [];
  const initial = (answer.passages as Passage[] | undefined) ?? [];
  const [found, setFound] = React.useState<Answer | null>(null);
  const [text, setText] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const passages = (found?.passages as Passage[] | undefined) ?? initial;
  const permit = typeof answer.permit === 'string' ? answer.permit : null;

  async function search() {
    if (!permit) return;
    setBusy(true);
    try {
      setFound(await post('/api/passages', { permit, text }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <section>
        <h4 className="font-semibold">Sources</h4>
        {sources.length === 0 ? (
          <Empty>No documents cited.</Empty>
        ) : (
          <ul className="divide-y">
            {sources.map((s) => (
              <li key={s.key} className="flex items-center justify-between gap-3 py-2">
                <div className="min-w-0">
                  <Mono>{s.document}</Mono>
                  <div className="truncate text-sm text-muted-foreground">{s.key}</div>
                </div>
                <a
                  href={s.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="inline-flex shrink-0 items-center gap-1 rounded-md border px-2 py-1 text-sm hover:bg-accent"
                >
                  Open PDF <ExternalLink className="h-3.5 w-3.5" />
                </a>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-xs text-muted-foreground">{TUNNEL_NOTE}</p>
      </section>

      <section>
        <h4 className="font-semibold">Passages, pre-filtered to what this answer permitted</h4>
        {permit && (
          <div className="mt-2 flex gap-2">
            <Input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Search the permitted documents (optional)"
              onKeyDown={(e) => e.key === 'Enter' && void search()}
            />
            <Button onClick={() => void search()} disabled={busy}>
              {busy ? 'Searching…' : 'passages()'}
            </Button>
          </div>
        )}
        {found && (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
            <OutcomeBadge outcome={found.outcome} />
            {typeof found.filter === 'string' && <span className="text-muted-foreground">{found.filter}</span>}
            {typeof found.reason === 'string' && <span>{found.reason}</span>}
          </div>
        )}
        {passages.length === 0 ? (
          <Empty>{permit ? 'No passages yet — ask with the permit above.' : 'No permit: this answer returned no rows to cite.'}</Empty>
        ) : (
          <ul className="mt-2 flex flex-col gap-3">
            {passages.map((p) => (
              <li key={p.chunk_id} className="rounded-md border bg-card p-3">
                <div className="mb-1 flex flex-wrap items-center gap-3 text-sm">
                  <Mono>{p.doc_id}</Mono>
                  <span>{p.matter_id}</span>
                  <span className="text-muted-foreground">{p.doc_type}</span>
                  {p.source_url && (
                    <a href={p.source_url} target="_blank" rel="noreferrer noopener" className="ml-auto inline-flex items-center gap-1 underline">
                      PDF <ExternalLink className="h-3 w-3" />
                    </a>
                  )}
                </div>
                <p className="text-sm">{excerpt(p.text)}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function excerpt(text: string): string {
  const body = text.includes('\n\n') ? text.split('\n\n').slice(1).join(' ') : text;
  const flat = body.split(/\s+/).join(' ');
  return flat.length > 420 ? flat.slice(0, 420) + '…' : flat;
}
