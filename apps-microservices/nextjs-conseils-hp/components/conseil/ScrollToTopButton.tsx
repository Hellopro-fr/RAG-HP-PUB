'use client';

import { ArrowUp } from 'lucide-react';

/** Bouton rond « remonter en haut » (défilement fluide). */
export function ScrollToTopButton() {
  return (
    <button
      type="button"
      aria-label="Remonter en haut de la page"
      onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
      className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-primary-foreground/15 text-primary-foreground transition hover:bg-primary-foreground/25"
    >
      <ArrowUp className="h-5 w-5" />
    </button>
  );
}
