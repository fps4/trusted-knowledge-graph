'use client';

// One conversation turn. The assistant's turn is its text and its tool calls, in
// the order they happened; each tool call is a chip that opens to the resolver's
// answer and can be sent to the inspector.

import * as React from 'react';
import { ChevronDown, ChevronRight, PanelRight } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Markdown } from '@/components/markdown';
import { AnswerCard } from '@/components/answer';
import { OutcomeBadge } from '@/components/outcome';
import { cn } from '@/lib/utils';
import type { Answer } from '@/lib/types';

export type Segment =
  | { kind: 'text'; text: string }
  | { kind: 'tool'; id: string; name: string; input: unknown; result?: Answer };

export type Turn =
  | { role: 'user'; text: string }
  | { role: 'assistant'; segments: Segment[]; error?: string; note?: string; pending?: boolean };

function summarise(input: unknown): string {
  if (!input || typeof input !== 'object') return '';
  return Object.entries(input as Record<string, unknown>)
    .filter(([k]) => k !== 'permit')
    .map(([, v]) => (typeof v === 'string' ? v : JSON.stringify(v)))
    .join(' ')
    .slice(0, 90);
}

function ToolChip({
  segment,
  selected,
  onSelect,
}: {
  segment: Extract<Segment, { kind: 'tool' }>;
  selected: boolean;
  onSelect: (a: Answer) => void;
}) {
  const result = segment.result;
  const rows = Array.isArray(result?.rows) ? (result!.rows as unknown[]).length : 0;
  const [open, setOpen] = React.useState(rows > 0);
  React.useEffect(() => {
    if (rows > 0) setOpen(true);
  }, [rows]);
  const renderable = segment.name === 'ask' || segment.name === 'resolve_term';
  return (
    <div className={cn('my-2 rounded-lg border bg-muted/40', selected && 'ring-2 ring-foreground/40')}>
      <div className="flex flex-wrap items-center gap-2 px-2 py-1.5">
        <button type="button" className="flex min-w-0 items-center gap-1.5 text-left" onClick={() => setOpen((o) => !o)}>
          {open ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
          <span className="font-mono text-sm font-semibold">{segment.name}</span>
          <span className="truncate font-mono text-sm text-muted-foreground">{summarise(segment.input)}</span>
        </button>
        {result ? <OutcomeBadge outcome={result.outcome} className="text-xs" /> : <span className="text-sm text-muted-foreground">running…</span>}
        {result && (
          <Button variant="ghost" size="sm" className="ml-auto h-7 gap-1 px-2" onClick={() => onSelect(result)}>
            <PanelRight className="h-4 w-4" /> Inspect
          </Button>
        )}
      </div>
      {open && result && (
        <div className="border-t px-3 py-2">
          {renderable ? (
            <AnswerCard answer={result} compact />
          ) : (
            <pre className="max-h-72 overflow-auto text-xs">{JSON.stringify(result, null, 2)}</pre>
          )}
        </div>
      )}
    </div>
  );
}

export function Message({
  turn,
  selected,
  onSelect,
}: {
  turn: Turn;
  selected: Answer | null;
  onSelect: (a: Answer) => void;
}) {
  if (turn.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-primary px-4 py-2 text-primary-foreground">{turn.text}</div>
      </div>
    );
  }
  return (
    <div className="rounded-2xl border bg-card px-4 py-3 text-card-foreground">
      {turn.segments.map((s, i) =>
        s.kind === 'text' ? (
          <Markdown key={i}>{s.text}</Markdown>
        ) : (
          <ToolChip key={s.id} segment={s} selected={!!s.result && s.result === selected} onSelect={onSelect} />
        ),
      )}
      {turn.pending && turn.segments.length === 0 && <p className="text-muted-foreground">Thinking…</p>}
      {turn.note && <p className="mt-2 text-sm text-amber-700 dark:text-amber-400">{turn.note}</p>}
      {turn.error && (
        <p className="mt-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-destructive">{turn.error}</p>
      )}
    </div>
  );
}
