'use client';

import { OutcomeBadge } from '@/components/outcome';
import { ChatTable } from '@/components/chat/table';
import { Field, Mono, Raw } from '@/components/inspector/parts';
import type { Answer } from '@/lib/types';

type Term = { term: string; reading?: string | null; owner: string };

export function TracePanel({ answer }: { answer: Answer }) {
  const route = answer.route as { route: string; reason: string } | undefined;
  const terms = (answer.terms as Term[] | undefined) ?? [];
  const slots = answer.slots as Record<string, string> | undefined;
  const means = answer.means as Record<string, string> | undefined;
  return (
    <div>
      <dl>
        <Field label="outcome">
          <OutcomeBadge outcome={answer.outcome} />
        </Field>
        {answer.trace && (
          <Field label="trace">
            <Mono>{answer.trace}</Mono>
          </Field>
        )}
        {route && (
          <Field label="route">
            <strong>{route.route}</strong> — {route.reason}
          </Field>
        )}
        {answer.template || typeof answer.question_id === 'string' ? (
          <Field label="template">
            <Mono>{String(answer.question_id ?? answer.template)}</Mono>
            {answer.question_id && answer.template ? (
              <span className="text-muted-foreground"> → {answer.template}</span>
            ) : null}
            {typeof answer.question === 'string' && <div className="text-muted-foreground">{answer.question}</div>}
          </Field>
        ) : null}
        {slots && Object.keys(slots).length > 0 && (
          <Field label="slots">
            {Object.entries(slots).map(([k, v]) => (
              <div key={k}>
                <Mono>
                  {k} = {v}
                </Mono>
              </div>
            ))}
          </Field>
        )}
        {typeof answer.policy_version === 'string' && (
          <Field label="policy version">
            <Mono>{answer.policy_version}</Mono>
          </Field>
        )}
        {typeof answer.permit_expires === 'string' && (
          <Field label="permit">for passages(), until {answer.permit_expires}</Field>
        )}
        {typeof answer.term === 'string' && (
          <Field label="term">
            <strong>{String(answer.label)}</strong> <Mono>({answer.term})</Mono> — {String(answer.definition)}
            <div className="text-muted-foreground">owner: {String(answer.owner)}</div>
          </Field>
        )}
        {typeof answer.on_ambiguous === 'string' && <Field label="on ambiguous">{answer.on_ambiguous}</Field>}
        {means && Object.keys(means).length > 0 && (
          <Field label="means">
            {Object.entries(means).map(([k, v]) => (
              <div key={k}>
                <Mono>
                  {k} = {v}
                </Mono>
              </div>
            ))}
          </Field>
        )}
      </dl>
      {terms.length > 0 && (
        <div className="mt-3">
          <h4 className="text-sm font-semibold">Glossary terms this answer rests on</h4>
          <ChatTable
            columns={[{ key: 'term' }, { key: 'reading' }, { key: 'owner' }]}
            rows={terms}
            exportName="terms"
          />
        </div>
      )}
      <Raw value={answer} />
    </div>
  );
}
