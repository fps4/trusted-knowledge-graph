'use client';

import * as React from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

import { ChatTable } from '@/components/chat/table';
import type { Rule } from '@/lib/types';

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[9rem_1fr] gap-3 py-1">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  );
}

export function Mono({ children }: { children: React.ReactNode }) {
  return <span className="font-mono text-[0.9em]">{children}</span>;
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="py-2 text-muted-foreground">{children}</p>;
}

export function RulesTable({ rules }: { rules: Rule[] }) {
  return (
    <ChatTable
      columns={[
        { key: 'rule' },
        { key: 'kind' },
        { key: 'owner' },
        { key: 'set_on', label: 'set on' },
        { key: 'set_by', label: 'set by' },
        { key: 'source', label: 'file' },
      ]}
      rows={rules}
      exportName="rules"
    />
  );
}

export function Raw({ value, label = 'Raw response' }: { value: unknown; label?: string }) {
  const [open, setOpen] = React.useState(false);
  return (
    <div className="mt-4">
      <button
        type="button"
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        onClick={() => setOpen((o) => !o)}
      >
        {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        {label}
      </button>
      {open && (
        <pre className="mt-2 max-h-[28rem] overflow-auto rounded-md border bg-muted/50 p-3 text-xs">
          {JSON.stringify(value, null, 2)}
        </pre>
      )}
    </div>
  );
}

export const TUNNEL_NOTE =
  'PDF links are signed by the resolver with your own document-store credentials, for 127.0.0.1:9100, ' +
  'valid for five minutes. From another machine, tunnel that port too: ssh -L 9100:127.0.0.1:9100 <host>.';
