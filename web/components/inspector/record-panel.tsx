'use client';

// explain(trace), read back from the stored decision record: the same grounds as
// the live answer, later, from the chain. docs/decisions/0012, 0013.

import * as React from 'react';

import { OutcomeBadge } from '@/components/outcome';
import { Empty, Field, Mono, Raw, RulesTable } from '@/components/inspector/parts';
import { post } from '@/lib/client';
import type { Answer, Rule } from '@/lib/types';

export function RecordPanel({ answer }: { answer: Answer }) {
  const trace = answer.trace;
  const [data, setData] = React.useState<Answer | null>(null);
  React.useEffect(() => {
    if (!trace) return;
    let live = true;
    setData(null);
    post('/api/explain', { trace }).then((d) => live && setData(d));
    return () => {
      live = false;
    };
  }, [trace]);

  if (!trace) return <Empty>No trace to look up.</Empty>;
  if (!data) return <Empty>Reading the record…</Empty>;
  const rules = (data.rules as Rule[] | undefined) ?? [];
  const blocked = data.blocked as { direct: number; by_lineage: number } | undefined;
  return (
    <div>
      <p className="mb-2 text-muted-foreground">The same grounds, from the stored record.</p>
      <dl>
        <Field label="explain">
          <OutcomeBadge outcome={data.outcome} /> <Mono>{data.trace}</Mono>
        </Field>
        {typeof data.reason === 'string' && <Field label="reason">{data.reason}</Field>}
        {typeof data.of_trace === 'string' && (
          <Field label="of trace">
            <Mono>{data.of_trace}</Mono>
          </Field>
        )}
        {typeof data.asked_at === 'string' && <Field label="asked at">{data.asked_at}</Field>}
        {typeof data.decided === 'string' && (
          <Field label="decided">
            <OutcomeBadge outcome={data.decided} />
          </Field>
        )}
        {typeof data.policy_version === 'string' && (
          <Field label="policy version">
            <Mono>{data.policy_version}</Mono>
          </Field>
        )}
        {blocked && (
          <Field label="blocked">
            {blocked.direct} directly · {blocked.by_lineage} by lineage
          </Field>
        )}
        {typeof data.note === 'string' && <Field label="note">{data.note}</Field>}
        {typeof data.source === 'string' && <Field label="source">{data.source}</Field>}
      </dl>
      {rules.length > 0 && <RulesTable rules={rules} />}
      <Raw value={data} label="Raw record response" />
    </div>
  );
}
