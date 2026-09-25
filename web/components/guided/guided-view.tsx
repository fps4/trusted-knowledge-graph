'use client';

// Guided mode: no model, no key, no network beyond this host. Pick a competency
// question, fill its slots (defaults shown), look words up in the glossary, ask.
// The same resolver, the same answer, the same inspector.

import * as React from 'react';
import { X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { AnswerCard } from '@/components/answer';
import { OutcomeBadge } from '@/components/outcome';
import { get, post } from '@/lib/client';
import { cn } from '@/lib/utils';
import type { Answer } from '@/lib/types';

type Slot = { name: string; kind: string; default: string | null; about: string };
type Template = { id: string; question: string; kind: string; slots: Slot[]; note?: string };
type Reading = { key: string; label?: string; owner: string; definition: string; count?: number | null; outcome?: string };

export function GuidedView({ onSelect, selected }: { onSelect: (a: Answer) => void; selected: Answer | null }) {
  const [templates, setTemplates] = React.useState<Template[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [chosen, setChosen] = React.useState<string>('');
  const [slots, setSlots] = React.useState<Record<string, string>>({});
  const [terms, setTerms] = React.useState<string[]>([]);
  const [word, setWord] = React.useState('');
  const [lookup, setLookup] = React.useState<Answer | null>(null);
  const [answers, setAnswers] = React.useState<Answer[]>([]);
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    get<Template[] | Answer>('/api/templates').then((t) => {
      if (Array.isArray(t)) setTemplates(t);
      else setError(String(t.reason ?? t.outcome ?? 'The resolver did not list its questions.'));
    });
  }, []);

  const template = templates?.find((t) => t.id === chosen);

  function choose(id: string) {
    setChosen(id);
    const t = templates?.find((x) => x.id === id);
    setSlots(Object.fromEntries((t?.slots ?? []).map((s) => [s.name, s.default ?? ''])));
  }

  async function resolve() {
    if (!word.trim()) return;
    const result = await post('/api/resolve_term', { text: word.trim() });
    setLookup(result);
    onSelect(result);
  }

  function adoptTerm(result: Answer) {
    const id = result.term as string | undefined;
    if (id && !terms.includes(id)) setTerms([...terms, id]);
    const means = (result.means as Record<string, string> | undefined) ?? {};
    setSlots((s) => ({ ...s, ...Object.fromEntries(Object.entries(means).filter(([k]) => k in s)) }));
  }

  async function ask() {
    if (!template) return;
    setBusy(true);
    try {
      const result = await post('/api/ask', { template_id: template.id, slots, terms });
      setAnswers((a) => [result, ...a]);
      onSelect(result);
    } finally {
      setBusy(false);
    }
  }

  if (error) return <p className="m-6 rounded-md border border-destructive/40 bg-destructive/10 p-4 text-destructive">{error}</p>;
  if (!templates) return <p className="m-6 text-muted-foreground">Loading the competency questions…</p>;

  const readings = (lookup?.readings as Reading[] | undefined) ?? [];
  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4">
        <section>
          <Label htmlFor="cq" className="text-base font-semibold">Competency question</Label>
          <select
            id="cq"
            value={chosen}
            onChange={(e) => choose(e.target.value)}
            className="mt-1 w-full rounded-md border bg-card px-3 py-2 text-base"
          >
            <option value="">Choose a question…</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.id} — {t.question}
              </option>
            ))}
          </select>
          {template?.note && <p className="mt-1 text-sm text-muted-foreground">{template.note}</p>}
        </section>

        {template && template.slots.length > 0 && (
          <section className="grid gap-2 sm:grid-cols-2">
            {template.slots.map((s) => (
              <div key={s.name}>
                <Label htmlFor={`slot-${s.name}`}>
                  {s.name} <span className="text-muted-foreground">({s.kind})</span>
                </Label>
                <Input
                  id={`slot-${s.name}`}
                  value={slots[s.name] ?? ''}
                  placeholder={s.default ?? ''}
                  onChange={(e) => setSlots({ ...slots, [s.name]: e.target.value })}
                  className="mt-1 font-mono text-base"
                />
                <p className="mt-0.5 text-xs text-muted-foreground">{s.about}</p>
              </div>
            ))}
          </section>
        )}

        <section className="rounded-lg border bg-card p-3">
          <Label htmlFor="term" className="font-semibold">Glossary — what a word means here, and who says so</Label>
          <div className="mt-1 flex gap-2">
            <Input
              id="term"
              value={word}
              onChange={(e) => setWord(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && void resolve()}
              placeholder="active client · AIFM · AFM investigation"
            />
            <Button variant="secondary" onClick={() => void resolve()}>
              resolve_term
            </Button>
          </div>
          {lookup && (
            <div className="mt-2 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <OutcomeBadge outcome={lookup.outcome} />
                {typeof lookup.label === 'string' && <strong>{lookup.label}</strong>}
                {typeof lookup.owner === 'string' && <span className="text-muted-foreground">owner: {lookup.owner}</span>}
                {typeof lookup.term === 'string' && readings.length === 0 && (
                  <Button size="sm" variant="outline" onClick={() => adoptTerm(lookup)}>
                    Use in slots
                  </Button>
                )}
              </div>
              {typeof lookup.definition === 'string' && <p className="mt-1">{lookup.definition}</p>}
              {typeof lookup.note === 'string' && <p className="mt-1 text-muted-foreground">{lookup.note}</p>}
              {readings.length > 0 && (
                <ul className="mt-2 divide-y rounded-md border">
                  {readings.map((r) => (
                    <li key={r.key} className="flex items-center gap-3 px-2 py-1.5">
                      <span className="font-mono">{r.key}</span>
                      <span className="text-muted-foreground">{r.owner}</span>
                      <span className="ml-auto tabular-nums">{r.count ?? r.outcome ?? '—'}</span>
                      {template?.slots.some((s) => s.name === 'reading') && (
                        <Button size="sm" variant="outline" onClick={() => setSlots({ ...slots, reading: r.key })}>
                          Choose
                        </Button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {terms.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
              <span className="text-muted-foreground">terms relied on:</span>
              {terms.map((t) => (
                <span key={t} className="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 font-mono">
                  {t}
                  <button type="button" aria-label={`Remove ${t}`} onClick={() => setTerms(terms.filter((x) => x !== t))}>
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
          )}
        </section>

        <div>
          <Button size="lg" disabled={!template || busy} onClick={() => void ask()}>
            {busy ? 'Asking…' : 'Ask'}
          </Button>
        </div>

        {answers.map((a) => (
          <button
            key={String(a.trace)}
            type="button"
            onClick={() => onSelect(a)}
            className={cn('min-w-0 rounded-xl border bg-card p-4 text-left', a === selected && 'ring-2 ring-foreground/40')}
          >
            <AnswerCard answer={a} />
          </button>
        ))}
      </div>
    </div>
  );
}
