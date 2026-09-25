'use client';

// Risk & Compliance's workspace: the three questions the record exists to answer,
// and whether its chain is intact. Every one of these reads is itself decided by
// OPA and written to the same chain. docs/decisions/0018.

import * as React from 'react';
import { ShieldAlert, ShieldCheck } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ChatTable } from '@/components/chat/table';
import { OutcomeBadge } from '@/components/outcome';
import { Raw } from '@/components/inspector/parts';
import { post } from '@/lib/client';
import type { Answer } from '@/lib/types';

type Chain = { ok: boolean; records: number; head: string; broken_at: number | null; reason: string | null };

const cols = (keys: string[]) => keys.map((key) => ({ key }));

export function AuditView() {
  const [chain, setChain] = React.useState<Answer | null>(null);
  const [matter, setMatter] = React.useState('M-2022-0117');
  const [person, setPerson] = React.useState('sanne');
  const [since, setSince] = React.useState('');
  const [until, setUntil] = React.useState('');
  const [trace, setTrace] = React.useState('');
  const [result, setResult] = React.useState<{ kind: string; answer: Answer } | null>(null);

  const verify = React.useCallback(() => post('/api/audit/verify').then(setChain), []);
  React.useEffect(() => {
    void verify();
  }, [verify]);

  const run = async (kind: string, body: unknown) => setResult({ kind, answer: await post(`/api/audit/${kind}`, body) });
  const c = chain?.chain as Chain | undefined;

  return (
    <div className="h-full space-y-4 overflow-y-auto p-4">
      <section className="flex flex-wrap items-center gap-4 rounded-lg border bg-card p-4">
        {c ? (
          c.ok ? <ShieldCheck className="h-8 w-8 text-emerald-600" /> : <ShieldAlert className="h-8 w-8 text-red-600" />
        ) : null}
        <div className="min-w-0 flex-1">
          <div className="font-semibold">
            Decision record: {c ? (c.ok ? 'chain intact' : `broken at record ${c.broken_at}`) : chain ? <OutcomeBadge outcome={chain.outcome} /> : 'checking…'}
          </div>
          {c && (
            <div className="text-sm text-muted-foreground">
              {c.records} records · head <span className="break-all font-mono">{c.head}</span>
              {c.reason ? ` · ${c.reason}` : ''}
            </div>
          )}
        </div>
        <Button variant="outline" onClick={() => void verify()}>
          Verify again
        </Button>
      </section>

      <section className="grid gap-3 rounded-lg border bg-card p-4">
        <Form label="Who has ever been shown anything derived from this matter?" onRun={() => run('subject', { matter })}>
          <Input value={matter} onChange={(e) => setMatter(e.target.value)} className="font-mono" aria-label="matter" />
        </Form>
        <Form label="What did this person see, between these times?" onRun={() => run('person', { person, since, until })}>
          <select value={person} onChange={(e) => setPerson(e.target.value)} className="rounded-md border bg-background px-2" aria-label="person">
            {['mara', 'sanne', 'kim', 'risk', 'percy-svc'].map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
          <Input value={since} onChange={(e) => setSince(e.target.value)} placeholder="since (ISO)" aria-label="since" />
          <Input value={until} onChange={(e) => setUntil(e.target.value)} placeholder="until (ISO)" aria-label="until" />
        </Form>
        <Form label="Why was this trace decided as it was?" onRun={() => run('trace', { trace })}>
          <Input value={trace} onChange={(e) => setTrace(e.target.value)} placeholder="t-1a2b3c4d" className="font-mono" aria-label="trace" />
        </Form>
      </section>

      {result && <AuditResult kind={result.kind} answer={result.answer} />}
    </div>
  );
}

function Form({ label, onRun, children }: { label: string; onRun: () => void; children: React.ReactNode }) {
  return (
    <form
      className="grid gap-1"
      onSubmit={(e) => {
        e.preventDefault();
        onRun();
      }}
    >
      <Label className="font-semibold">{label}</Label>
      <div className="flex gap-2">
        {children}
        <Button type="submit">Ask</Button>
      </div>
    </form>
  );
}

function AuditResult({ kind, answer }: { kind: string; answer: Answer }) {
  const shown = (answer.shown as Record<string, unknown>[] | undefined) ?? [];
  const refused = (answer.refused as Record<string, unknown>[] | undefined) ?? [];
  const requests = (answer.requests as Record<string, unknown>[] | undefined) ?? [];
  const record = answer.record as Record<string, unknown> | undefined;
  const rules = (answer.explain as { rules?: { rule: string; owner: string }[] } | undefined)?.rules ?? [];
  return (
    <section className="rounded-lg border bg-card p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <OutcomeBadge outcome={answer.outcome} />
        <span className="font-mono text-xs text-muted-foreground">{answer.trace}</span>
        {typeof answer.reason === 'string' && <span>{answer.reason}</span>}
        {rules.map((r) => (
          <span key={r.rule}>
            rule <strong>{r.rule}</strong> · {r.owner}
          </span>
        ))}
      </div>
      {kind === 'subject' && answer.outcome === 'shown' && (
        <>
          <h4 className="mt-2 font-semibold">Shown ({shown.length})</h4>
          <ChatTable columns={cols(['ts', 'persona', 'trace', 'template', 'how'])} rows={shown} exportName="shown" />
          <h4 className="mt-4 font-semibold">Refused ({refused.length})</h4>
          <ChatTable columns={cols(['ts', 'persona', 'trace', 'template', 'outcome', 'rules', 'blocked'])} rows={refused} exportName="refused" />
          <p className="mt-2 text-sm text-muted-foreground">
            Derived graphs of this matter: {((answer.derived_graphs as string[]) ?? []).join(', ') || 'none'}
          </p>
        </>
      )}
      {kind === 'person' && answer.outcome === 'shown' && (
        <ChatTable
          columns={cols(['ts', 'trace', 'request', 'template', 'outcome', 'shown_matters', 'counted_matters', 'withheld', 'rules'])}
          rows={requests}
          exportName="person"
        />
      )}
      {kind === 'trace' && record && <TraceRecord record={record} />}
      <Raw value={answer} />
    </section>
  );
}

type Ground = { rule: string; kind?: string; owner?: string; set_on?: string; set_by?: string; source?: string };
type Decision = { item: string; allow: boolean; reached?: string; rules?: string[]; via?: string[] };

// One stored decision, read back: who asked what, the rules that decided it (the same
// card the person saw), and every item it allowed or blocked, with how it was reached.
function TraceRecord({ record }: { record: Record<string, unknown> }) {
  const route = record.route as { route?: string; reason?: string } | undefined;
  const grounds = Object.values((record.grounds as Record<string, Ground> | undefined) ?? {});
  const decisions = ((record.decisions as Decision[] | undefined) ?? []).map((d) => ({
    item: d.item,
    decided: d.allow ? 'allowed' : 'blocked',
    reached: d.reached ?? '',
    rules: (d.rules ?? []).join(', '),
    via: (d.via ?? []).join(', '),
  }));
  return (
    <>
      <p className="mt-1 text-sm">
        <strong>{String(record.persona)}</strong> asked <span className="font-mono">{String(record.template ?? record.request)}</span>{' '}
        at {String(record.ts)} → <OutcomeBadge outcome={String(record.outcome)} />
        {route?.reason && <span className="text-muted-foreground"> · {route.route}: {route.reason}</span>}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        record #{String(record.seq)} · policy {String(record.policy_version)} · disclosure {String(record.disclosure)}
      </p>
      {grounds.length > 0 && (
        <>
          <h4 className="mt-3 font-semibold">Grounds</h4>
          <ChatTable columns={cols(['rule', 'kind', 'owner', 'set_on', 'set_by', 'source'])} rows={grounds} exportName="grounds" />
        </>
      )}
      <h4 className="mt-3 font-semibold">Decisions ({decisions.length})</h4>
      <ChatTable columns={cols(['item', 'decided', 'reached', 'rules', 'via'])} rows={decisions} exportName="decisions" />
    </>
  );
}
