'use client';

// Resolver rows as a read-only grid: sortable columns, copy, CSV and XLSX export.
// The rows come straight from the resolver's response, never from the model's text.

import * as React from 'react';
import { ArrowDown, ArrowUp, Check, Copy, Download } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { cn } from '@/lib/utils';
import { buildCsv, buildXlsx, copyTable, downloadBytes } from '@/lib/table-export';

export type TableColumn = { key: string; label?: string };
type Row = Record<string, unknown>;
type SortState = { key: string; dir: 'asc' | 'desc' };

function text(v: unknown): string {
  if (v === null || v === undefined) return '';
  if (Array.isArray(v)) return v.map(text).join(', ');
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

function isNumeric(v: unknown): boolean {
  return typeof v === 'number' || (typeof v === 'string' && v !== '' && !Number.isNaN(Number(v)));
}

function sortRows(data: Row[], sort: SortState | null): Row[] {
  if (!sort) return data;
  const dir = sort.dir === 'asc' ? 1 : -1;
  const cmp = (a: unknown, b: unknown): number => {
    const aN = a === null || a === undefined || a === '';
    const bN = b === null || b === undefined || b === '';
    if (aN && bN) return 0;
    if (aN) return 1; // blanks sort last regardless of direction
    if (bN) return -1;
    if (isNumeric(a) && isNumeric(b)) return (Number(a) - Number(b)) * dir;
    return text(a).localeCompare(text(b), 'en') * dir;
  };
  return [...data].sort((ra, rb) => cmp(ra[sort.key], rb[sort.key]));
}

export function ChatTable({
  columns,
  rows,
  empty = 'No rows.',
  exportName = 'table',
}: {
  columns: TableColumn[];
  rows: Row[];
  empty?: string;
  exportName?: string;
}) {
  const [sort, setSort] = React.useState<SortState | null>(null);
  const [copied, setCopied] = React.useState(false);
  const sorted = React.useMemo(() => sortRows(rows, sort), [rows, sort]);

  const exportMatrix = React.useCallback(() => {
    const headers = columns.map((c) => c.label ?? c.key);
    const body = sorted.map((row) => columns.map((c) => text(row[c.key])));
    return { headers, body };
  }, [columns, sorted]);

  function toggleSort(key: string) {
    setSort((s) => (s && s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'asc' }));
  }

  async function onCopy() {
    const { headers, body } = exportMatrix();
    await copyTable(headers, body);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  if (columns.length === 0 || rows.length === 0) {
    return <p className="mt-1 text-sm text-muted-foreground">{empty}</p>;
  }

  const tool = 'h-auto gap-1 px-1.5 py-0.5 text-xs text-muted-foreground';
  return (
    <div className="mt-2">
      <div className="mb-1 flex items-center justify-end gap-1">
        <Button variant="ghost" size="sm" className={tool} onClick={() => void onCopy()}>
          {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
          {copied ? 'Copied' : 'Copy'}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className={tool}
          onClick={() => {
            const { headers, body } = exportMatrix();
            downloadBytes(`${exportName}.csv`, 'text/csv;charset=utf-8', buildCsv(headers, body));
          }}
        >
          <Download className="h-3 w-3" />
          CSV
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className={tool}
          onClick={() => {
            const { headers, body } = exportMatrix();
            downloadBytes(
              `${exportName}.xlsx`,
              'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
              buildXlsx(headers, body),
            );
          }}
        >
          <Download className="h-3 w-3" />
          XLSX
        </Button>
      </div>
      <div className="overflow-x-auto rounded-md border bg-card" role="figure">
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map((col) => {
                const active = sort?.key === col.key;
                return (
                  <TableHead
                    key={col.key}
                    onClick={() => toggleSort(col.key)}
                    aria-label={`Sort by ${col.label ?? col.key}`}
                    className="cursor-pointer select-none whitespace-nowrap hover:text-foreground"
                  >
                    <span className="inline-flex items-center gap-1">
                      {col.label ?? col.key}
                      {active && (sort?.dir === 'asc' ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
                    </span>
                  </TableHead>
                );
              })}
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((row, ri) => (
              <TableRow key={ri}>
                {columns.map((col) => (
                  <TableCell
                    key={col.key}
                    className={cn(
                      'align-top',
                      text(row[col.key]).length <= 28 && 'whitespace-nowrap',
                      isNumeric(row[col.key]) && 'text-right tabular-nums',
                    )}
                  >
                    {text(row[col.key])}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
