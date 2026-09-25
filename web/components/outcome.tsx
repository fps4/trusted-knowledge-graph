import { cn } from '@/lib/utils';

const TONE: Record<string, string> = {
  answered: 'bg-emerald-600 text-white',
  shown: 'bg-emerald-600 text-white',
  resolved: 'bg-emerald-600 text-white',
  concept: 'bg-emerald-600 text-white',
  'answered-with-withheld': 'bg-amber-500 text-black',
  'refused-ambiguous': 'bg-orange-500 text-black',
  refused: 'bg-red-600 text-white',
  'refused-aggregate': 'bg-red-600 text-white',
  'refused-identity': 'bg-red-600 text-white',
  'refused-permit': 'bg-red-600 text-white',
  'refused-invalid': 'bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200',
};

export function OutcomeBadge({ outcome, className }: { outcome?: string; className?: string }) {
  if (!outcome) return null;
  const tone = TONE[outcome] ?? 'border bg-muted text-muted-foreground';
  return (
    <span className={cn('inline-flex items-center rounded-md px-2 py-0.5 text-sm font-semibold', tone, className)}>
      {outcome}
    </span>
  );
}
