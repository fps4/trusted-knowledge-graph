'use client';

import * as React from 'react';

import { Header } from '@/components/header';
import { ChatView } from '@/components/chat/chat-view';
import { GuidedView } from '@/components/guided/guided-view';
import { AuditView } from '@/components/audit/audit-view';
import { Inspector } from '@/components/inspector/inspector';
import { cn } from '@/lib/utils';
import type { Answer } from '@/lib/types';

type Mode = 'Chat' | 'Guided' | 'Audit';

export function Workspace({ persona, model }: { persona: string; model: string | null }) {
  // Risk's screen opens on the record; everyone else's on the conversation.
  const modes: Mode[] = persona === 'risk' ? ['Audit', 'Chat', 'Guided'] : ['Chat', 'Guided'];
  const [mode, setMode] = React.useState<Mode>(persona === 'risk' ? 'Audit' : model ? 'Chat' : 'Guided');
  const [selected, setSelected] = React.useState<Answer | null>(null);

  return (
    <div className="flex h-screen flex-col">
      <Header persona={persona} model={model} />
      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] xl:grid-cols-[minmax(0,11fr)_minmax(0,9fr)]">
        <main className="flex min-h-0 flex-col border-r">
          <nav className="flex gap-1 border-b px-4 pt-3">
            {modes.map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={cn(
                  '-mb-px border-b-2 px-3 py-2 font-medium',
                  mode === m ? 'border-foreground' : 'border-transparent text-muted-foreground hover:text-foreground',
                )}
              >
                {m}
              </button>
            ))}
          </nav>
          <div className="min-h-0 flex-1">
            {/* Hidden, not unmounted: switching modes keeps the conversation. */}
            <div className={cn('h-full', mode !== 'Chat' && 'hidden')}>
              <ChatView persona={persona} ready={!!model} selected={selected} onSelect={setSelected} onUseGuided={() => setMode('Guided')} />
            </div>
            <div className={cn('h-full', mode !== 'Guided' && 'hidden')}>
              <GuidedView selected={selected} onSelect={setSelected} />
            </div>
            {persona === 'risk' && (
              <div className={cn('h-full', mode !== 'Audit' && 'hidden')}>
                <AuditView />
              </div>
            )}
          </div>
        </main>
        <div className="min-h-0 bg-background">
          <Inspector answer={selected} />
        </div>
      </div>
    </div>
  );
}
