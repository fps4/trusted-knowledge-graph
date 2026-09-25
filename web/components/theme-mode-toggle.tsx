'use client';

// Light/dark switch. Light is the default: it reads better on a projector.

import * as React from 'react';
import { useTheme } from 'next-themes';
import { Moon, Sun } from 'lucide-react';

import { Button } from '@/components/ui/button';

export function ThemeModeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);

  // `resolvedTheme` is undefined until next-themes hydrates; defer the icon swap
  // until after mount to avoid a hydration mismatch.
  React.useEffect(() => setMounted(true), []);

  const isDark = mounted && resolvedTheme === 'dark';
  const label = isDark ? 'Switch to light' : 'Switch to dark';
  return (
    <Button variant="ghost" size="icon" aria-label={label} title={label} onClick={() => setTheme(isDark ? 'light' : 'dark')}>
      {isDark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
    </Button>
  );
}
