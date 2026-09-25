'use client';

import * as React from 'react';
import { Lock } from 'lucide-react';

import { ThemeModeToggle } from '@/components/theme-mode-toggle';
import { get } from '@/lib/client';
import { NAMES } from '@/lib/personas';
import type { Answer } from '@/lib/types';

export function Header({ persona, model }: { persona: string; model: string | null }) {
  const [who, setWho] = React.useState<Answer | null>(null);
  React.useEffect(() => {
    get('/api/whoami').then(setWho);
  }, []);
  const verified = who && typeof who.principal === 'string';
  return (
    <header className="border-b bg-card">
      <div className="bg-amber-100 px-4 py-1 text-center text-sm font-medium text-amber-950 dark:bg-amber-950 dark:text-amber-100">
        Lab Firm LLP — synthetic. No real firm, client, matter or person. Identity is asserted, not federated.
      </div>
      <div className="flex flex-wrap items-center gap-x-6 gap-y-1 px-4 py-2">
        <div className="text-lg font-semibold">Lab Firm LLP</div>
        <div className="flex items-center gap-2">
          <Lock className="h-4 w-4 text-muted-foreground" aria-hidden />
          <span className="text-muted-foreground">you are</span>
          <span className="text-lg font-semibold">{NAMES[persona] ?? (persona || 'nobody')}</span>
          <span className="rounded border px-1.5 text-xs text-muted-foreground">fixed for this window</span>
        </div>
        <div className="min-w-0 text-sm text-muted-foreground">
          {verified ? (
            <>
              {String(who!.principal)} · {String(who!.about ?? '')}
            </>
          ) : who ? (
            <span className="text-destructive">resolver: {String(who.reason ?? who.outcome)}</span>
          ) : (
            'checking identity…'
          )}
        </div>
        <div className="ml-auto flex items-center gap-3 text-sm text-muted-foreground">
          <span>{model ? `chat: ${model}` : 'chat off — guided only'}</span>
          <ThemeModeToggle />
        </div>
      </div>
    </header>
  );
}
