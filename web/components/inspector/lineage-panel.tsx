'use client';

// Where each cited graph came from: fact graph → document (type, date) → matter;
// told facts → the partner who told them; spine graphs → the system of record and
// its mapping. Each lookup is itself decided, and recorded, as this person.

import * as React from 'react';
import { ArrowDown } from 'lucide-react';

import { OutcomeBadge } from '@/components/outcome';
import { Empty, Mono } from '@/components/inspector/parts';
import { post } from '@/lib/client';
import type { Answer } from '@/lib/types';

type Edge = {
  from: string;
  to: string;
  kind: string;
  attributed_to: string | null;
  document?: { type: string; date: string; matter: string | null };
};
type Lineage = Answer & { graph?: string; kind?: string; source?: string; facts?: number; matters?: string[]; chain?: Edge[] };

const LIMIT = 8;

export function LineagePanel({ answer }: { answer: Answer }) {
  const citations = ((answer.citations as string[] | undefined) ?? []).slice(0, LIMIT);
  const extra = ((answer.citations as string[] | undefined) ?? []).length - citations.length;
  if (citations.length === 0) return <Empty>This answer cites no graphs.</Empty>;
  return (
    <div className="flex flex-col gap-4">
      {citations.map((g) => (
        <GraphLineage key={g} graph={g} />
      ))}
      {extra > 0 && <p className="text-sm text-muted-foreground">… and {extra} more cited graphs.</p>}
    </div>
  );
}

function GraphLineage({ graph }: { graph: string }) {
  const [data, setData] = React.useState<Lineage | null>(null);
  React.useEffect(() => {
    let live = true;
    post<Lineage>('/api/lineage', { graph }).then((d) => live && setData(d));
    return () => {
      live = false;
    };
  }, [graph]);

  return (
    <section className="rounded-lg border bg-card p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Mono>{graph}</Mono>
        {data && <OutcomeBadge outcome={data.outcome} />}
        {data?.trace && <span className="font-mono text-xs text-muted-foreground">{data.trace}</span>}
      </div>
      {!data && <p className="text-sm text-muted-foreground">Asking the resolver…</p>}
      {data && data.outcome !== 'shown' && (
        <p className="mt-2 text-sm">{String(data.reason ?? 'Not shown.')}</p>
      )}
      {data?.outcome === 'shown' && data.kind === 'system of record' && (
        <Flow nodes={[{ title: graph, detail: 'graph built from a system of record' }, { title: 'system of record', detail: data.source ?? '' }]} />
      )}
      {data?.outcome === 'shown' && data.kind === 'derived' && <Derived data={data} />}
    </section>
  );
}

function Derived({ data }: { data: Lineage }) {
  const chain = data.chain ?? [];
  const graph = data.graph ?? '';
  // Walk the edges from the graph downwards, so the flow reads top to bottom.
  const nodes: { title: string; detail: string }[] = [];
  const seen = new Set<string>();
  let frontier = [graph];
  const by = chain.find((e) => e.from === graph && e.attributed_to)?.attributed_to;
  nodes.push({ title: graph, detail: `${data.facts ?? 0} fact(s)` + attribution(by) });
  seen.add(graph);
  while (frontier.length) {
    const next: string[] = [];
    for (const from of frontier) {
      for (const e of chain.filter((c) => c.from === from && !seen.has(c.to))) {
        seen.add(e.to);
        next.push(e.to);
        const nextBy = chain.find((c) => c.from === e.to && c.attributed_to)?.attributed_to;
        nodes.push({ title: e.to, detail: describe(e) + attribution(nextBy) });
      }
    }
    frontier = next;
  }
  return (
    <>
      <Flow nodes={nodes} />
      {data.matters && data.matters.length > 0 && (
        <p className="mt-2 text-sm text-muted-foreground">Reaches matter(s): {data.matters.join(', ')}</p>
      )}
    </>
  );
}

// A person told it (an asserted fact) or a model read it from a document.
function attribution(by: string | null | undefined): string {
  if (!by) return '';
  return by.startsWith('id:person/') ? ` · told by ${by}` : ` · extracted by ${by}`;
}

function describe(e: Edge): string {
  if (e.document) return `document · ${e.document.type} · ${e.document.date}${e.document.matter ? ` · ${e.document.matter}` : ''}`;
  return e.kind;
}

function Flow({ nodes }: { nodes: { title: string; detail: string }[] }) {
  return (
    <ol className="mt-3 flex flex-col items-start">
      {nodes.map((n, i) => (
        <li key={n.title + i} className="flex flex-col items-start">
          {i > 0 && <ArrowDown className="my-1 ml-4 h-4 w-4 text-muted-foreground" aria-label="derived from" />}
          <div className="rounded-md border bg-background px-3 py-1.5">
            <Mono>{n.title}</Mono>
            {n.detail && <div className="text-sm text-muted-foreground">{n.detail}</div>}
          </div>
        </li>
      ))}
    </ol>
  );
}
