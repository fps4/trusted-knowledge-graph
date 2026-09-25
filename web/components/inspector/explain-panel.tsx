'use client';

import { Empty, RulesTable } from '@/components/inspector/parts';
import type { Answer, Rule } from '@/lib/types';

type Explain = { rules?: Rule[]; blocked?: { direct: number; by_lineage: number }; policy_version?: string };

export function ExplainPanel({ answer }: { answer: Answer }) {
  const explain = answer.explain as Explain | undefined;
  const readings = (answer.readings as { key: string; explain?: Explain }[] | undefined) ?? [];
  const withExplain = readings.filter((r) => r.explain?.rules?.length);
  if (!explain?.rules?.length && withExplain.length === 0) {
    return (
      <Empty>
        Nothing was withheld from this answer
        {answer.outcome && answer.outcome.startsWith('refused') ? ', or the refusal was not about access' : ''}.
      </Empty>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      {explain?.rules?.length ? <Grounds explain={explain} /> : null}
      {withExplain.map((r) => (
        <div key={r.key}>
          <h4 className="font-semibold">Reading “{r.key}”</h4>
          <Grounds explain={r.explain!} />
        </div>
      ))}
    </div>
  );
}

function Grounds({ explain }: { explain: Explain }) {
  return (
    <div>
      {explain.blocked && (
        <div className="mb-2 flex flex-wrap gap-6">
          <Count n={explain.blocked.direct} label="matters blocked directly" />
          <Count n={explain.blocked.by_lineage} label="derived facts blocked by lineage" />
        </div>
      )}
      <RulesTable rules={explain.rules ?? []} />
      {explain.policy_version && (
        <p className="mt-1 text-sm text-muted-foreground">policy {explain.policy_version}</p>
      )}
    </div>
  );
}

function Count({ n, label }: { n: number; label: string }) {
  return (
    <div>
      <div className="text-3xl font-semibold tabular-nums">{n}</div>
      <div className="text-sm text-muted-foreground">{label}</div>
    </div>
  );
}
