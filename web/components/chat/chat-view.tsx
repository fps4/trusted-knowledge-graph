'use client';

// Chat with Claude, as this process's person. The route handler runs the model and
// the tools; this view renders the NDJSON stream and keeps the conversation the
// API returned, so the next turn is appended to it unchanged.

import * as React from 'react';
import type Anthropic from '@anthropic-ai/sdk';
import { SendHorizonal } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Message, type Segment, type Turn } from '@/components/chat/message';
import { readNdjson } from '@/lib/client';
import type { Answer } from '@/lib/types';

const EXAMPLES: Record<string, string[]> = {
  mara: [
    'Who led M-2021-0043 and what was the outcome?',
    'Has the firm advised a Dutch fund manager on an AFM investigation since 2021?',
    'How many active clients do we have?',
  ],
  sanne: [
    'Who led M-2022-0117?',
    'Has the firm advised a Dutch fund manager on an AFM investigation since 2021?',
    'What expertise is recorded for Mara?',
  ],
  kim: ['Who has led the most AFM investigations?', 'What does "active client" mean here?'],
  risk: ['Who has ever been shown anything derived from M-2022-0117?', 'Is the decision record intact?'],
};

export function ChatView({
  persona,
  ready,
  onSelect,
  selected,
  onUseGuided,
}: {
  persona: string;
  ready: boolean;
  onSelect: (a: Answer) => void;
  selected: Answer | null;
  onUseGuided: () => void;
}) {
  const [turns, setTurns] = React.useState<Turn[]>([]);
  const [history, setHistory] = React.useState<Anthropic.MessageParam[]>([]);
  const [draft, setDraft] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const bottom = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }), [turns]);

  // Apply a change to the assistant turn being streamed (always the last one).
  const update = (fn: (t: Extract<Turn, { role: 'assistant' }>) => void) =>
    setTurns((all) => {
      const next = [...all];
      const last = next[next.length - 1];
      if (last?.role !== 'assistant') return all;
      const copy = { ...last, segments: [...last.segments] };
      fn(copy);
      next[next.length - 1] = copy;
      return next;
    });

  async function send(text: string) {
    const prompt = text.trim();
    if (!prompt || busy) return;
    setDraft('');
    setBusy(true);
    setTurns((t) => [...t, { role: 'user', text: prompt }, { role: 'assistant', segments: [], pending: true }]);
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, history }),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as { message?: string };
        update((t) => (t.error = body.message ?? `The chat answered ${response.status}.`));
        return;
      }
      for await (const event of readNdjson(response)) {
        if (event.type === 'text') {
          update((t) => {
            const last = t.segments[t.segments.length - 1];
            if (last?.kind === 'text') t.segments[t.segments.length - 1] = { kind: 'text', text: last.text + event.text };
            else t.segments.push({ kind: 'text', text: event.text });
          });
        } else if (event.type === 'tool_start') {
          update((t) => t.segments.push({ kind: 'tool', id: event.id, name: event.name, input: event.input }));
        } else if (event.type === 'tool_done') {
          const result = event.result as Answer;
          update((t) => {
            t.segments = t.segments.map((s): Segment => (s.kind === 'tool' && s.id === event.id ? { ...s, result } : s));
          });
          if (event.name === 'ask' || event.name === 'resolve_term' || event.name.startsWith('audit_')) onSelect(result);
        } else if (event.type === 'done') {
          setHistory(event.messages);
          if (event.note) update((t) => (t.note = event.note));
        } else if (event.type === 'error') {
          update((t) => (t.error = event.message));
        }
      }
    } catch {
      update((t) => (t.error = 'The connection to this screen’s server dropped.'));
    } finally {
      update((t) => (t.pending = false));
      setBusy(false);
    }
  }

  if (!ready) {
    return (
      <div className="m-6 rounded-lg border bg-card p-6">
        <h3 className="text-lg font-semibold">Chat is off on this host</h3>
        <p className="mt-2 text-muted-foreground">
          Chat talks to Claude through the Anthropic API and needs <code>ANTHROPIC_API_KEY</code> in the stack&apos;s{' '}
          <code>.env</code>. Everything else works without it.
        </p>
        <Button className="mt-4" onClick={onUseGuided}>
          Use guided mode
        </Button>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        {turns.length === 0 && (
          <div className="flex flex-col gap-2">
            <p className="text-muted-foreground">Try:</p>
            {(EXAMPLES[persona] ?? EXAMPLES.mara).map((q) => (
              <button key={q} type="button" onClick={() => void send(q)} className="w-fit rounded-lg border bg-card px-3 py-2 text-left hover:bg-accent">
                {q}
              </button>
            ))}
          </div>
        )}
        {turns.map((t, i) => (
          <Message key={i} turn={t} selected={selected} onSelect={onSelect} />
        ))}
        <div ref={bottom} />
      </div>
      <form
        className="flex gap-2 border-t p-3"
        onSubmit={(e) => {
          e.preventDefault();
          void send(draft);
        }}
      >
        <Textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              void send(draft);
            }
          }}
          placeholder="Ask about the firm's matters…"
          rows={2}
          className="min-h-0 resize-none text-base"
          disabled={busy}
        />
        <Button type="submit" size="icon" className="h-auto w-12" disabled={busy || !draft.trim()} aria-label="Send">
          <SendHorizonal className="h-5 w-5" />
        </Button>
      </form>
    </div>
  );
}
