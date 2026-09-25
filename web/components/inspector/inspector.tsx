'use client';

import * as React from 'react';

import { cn } from '@/lib/utils';
import { isAsk } from '@/lib/client';
import type { Answer } from '@/lib/types';
import { TracePanel } from '@/components/inspector/trace-panel';
import { ExplainPanel } from '@/components/inspector/explain-panel';
import { SourcesPanel } from '@/components/inspector/sources-panel';
import { LineagePanel } from '@/components/inspector/lineage-panel';
import { RecordPanel } from '@/components/inspector/record-panel';

const TABS = ['Trace', 'Explain', 'Sources', 'Lineage', 'Record'] as const;
type Tab = (typeof TABS)[number];

export function Inspector({ answer }: { answer: Answer | null }) {
  const [tab, setTab] = React.useState<Tab>('Trace');
  const ask = isAsk(answer);
  return (
    <aside className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-1 border-b px-4 pt-3">
        <span className="mr-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">Inspector</span>
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={cn(
              '-mb-px border-b-2 px-3 py-2 text-[0.95rem]',
              tab === t ? 'border-foreground font-semibold' : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {t}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {!answer ? (
          <p className="text-muted-foreground">
            Ask something. The answer&apos;s route, rules, sources, lineage and record appear here.
          </p>
        ) : tab === 'Trace' ? (
          <TracePanel answer={answer} />
        ) : tab === 'Explain' ? (
          <ExplainPanel answer={answer} />
        ) : tab === 'Sources' ? (
          <SourcesPanel key={answer.trace} answer={answer} />
        ) : tab === 'Lineage' ? (
          <LineagePanel key={answer.trace} answer={answer} />
        ) : ask ? (
          <RecordPanel answer={answer} />
        ) : (
          <p className="text-muted-foreground">explain() reads the record of a question; select an ask() result.</p>
        )}
      </div>
    </aside>
  );
}
