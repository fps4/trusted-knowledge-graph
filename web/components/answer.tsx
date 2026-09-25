'use client';

// One resolver answer, rendered the way the CLI renders it: outcome, question,
// route, reason, rows with their citations, and — when something was withheld —
// the rule. Used by guided mode and inside the chat's tool chips.

import { ChatTable } from '@/components/chat/table';
import { OutcomeBadge } from '@/components/outcome';
import { COLUMN_LABELS } from '@/lib/client';
import type { Answer, Rule } from '@/lib/types';

export function AnswerCard({ answer, compact = false }: { answer: Answer; compact?: boolean }) {
  const rows = (answer.rows as Record<string, unknown>[] | undefined) ?? [];
  const columns = ((answer.columns as string[] | undefined) ?? []).map((key) => ({
    key,
    label: COLUMN_LABELS[key] ?? key,
  }));
  const explain = answer.explain as { rules?: Rule[]; blocked?: { direct: number; by_lineage: number } } | undefined;
  const readings = answer.readings as Record<string, unknown>[] | undefined;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <OutcomeBadge outcome={answer.outcome} />
        {answer.template && <span className="font-mono text-sm">{answer.template}</span>}
        {answer.trace && <span className="font-mono text-xs text-muted-foreground">{answer.trace}</span>}
      </div>
      {!compact && typeof answer.question === 'string' && <p className="text-muted-foreground">{answer.question}</p>}
      {typeof answer.reason === 'string' && <p>{answer.reason}</p>}
      {explain?.rules && explain.rules.length > 0 && (
        <p className="text-sm">
          Withheld under{' '}
          {explain.rules.map((r, i) => (
            <span key={r.rule}>
              {i > 0 && '; '}
              <strong>{r.rule}</strong> ({r.kind}) · {r.owner} · set {r.set_on}
            </span>
          ))}
          {explain.blocked && (
            <span className="text-muted-foreground">
              {' '}
              — {explain.blocked.direct} matter(s) directly, {explain.blocked.by_lineage} derived fact(s) by lineage
            </span>
          )}
        </p>
      )}
      {readings && readings.length > 0 && (
        <ChatTable
          columns={[
            { key: 'key', label: 'reading' },
            { key: 'owner' },
            { key: 'definition' },
            { key: 'count' },
          ]}
          rows={readings.map((r) => ({ ...r, count: r.count ?? r.outcome ?? '—' }))}
          exportName="readings"
        />
      )}
      {columns.length > 0 && (rows.length > 0 || !answer.outcome?.startsWith('refused')) && (
        <ChatTable
          columns={columns}
          rows={rows}
          empty="The graph has no facts for this question. That is an answer."
          exportName={String(answer.template ?? 'answer')}
        />
      )}
      {typeof answer.scope === 'string' && <p className="text-sm text-amber-700 dark:text-amber-400">{answer.scope}</p>}
      {typeof answer.note === 'string' && answer.note && !compact && (
        <p className="text-sm text-muted-foreground">{answer.note}</p>
      )}
    </div>
  );
}
