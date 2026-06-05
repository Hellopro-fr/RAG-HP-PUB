'use client';

import { useState } from 'react';
import { Check } from 'lucide-react';
import type { AoFormQuestion, AoChoix } from '@/types/conseils';

interface AoChoixGridProps {
  question?: AoFormQuestion | null;
  onChoixClick: (c: AoChoix) => void;
  onAutreChange: (id: string | number, value: string) => void;
}

/**
 * Grille de choix AO partagée entre HeroQuoteForm et QuoteFormBlock.
 * Gère : image / cercle-check / typeInput=1 (champ libre).
 */
export function AoChoixGrid({ question, onChoixClick, onAutreChange }: AoChoixGridProps) {
  const [selected, setSelected] = useState<Set<string | number>>(new Set());
  const [autreValues, setAutreValues] = useState<Record<string | number, string>>({});

  const choix = question?.choix ?? [];
  if (choix.length === 0) return null;

  function handleClick(c: AoChoix) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (Number(question?.typeSelection) === 1) {
        next.clear();
        next.add(c.id);
      } else {
        if (next.has(c.id)) next.delete(c.id);
        else next.add(c.id);
      }
      return next;
    });
    onChoixClick(c);
  }

  function handleAutre(id: string | number, value: string) {
    setAutreValues((prev) => ({ ...prev, [id]: value }));
    onAutreChange(id, value);
  }

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
      {choix.map((c) => {
        const isActive     = selected.has(c.id);
        const hasTypeInput = String(c.typeInput) === '1';
        const hasImage     = Boolean(c.image);
        const autreVal     = autreValues[c.id] ?? '';

        return (
          <button
            key={c.id}
            type="button"
            onClick={() => handleClick(c)}
            className={`group flex flex-col items-center gap-2 rounded-lg border bg-background px-2 pb-2 pt-3 text-center transition hover:border-primary hover:shadow-sm ${
              isActive ? 'border-primary ring-2 ring-primary/30' : 'border-border'
            }`}
          >
            {/* Icône */}
            {!(hasTypeInput && isActive) && (
              hasImage ? (
                <div className="flex h-16 w-16 items-center justify-center overflow-hidden rounded-full bg-muted ring-1 ring-border">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={c.image} alt={c.label} className="h-full w-full object-cover" />
                </div>
              ) : (
                <div className={`flex h-16 w-16 items-center justify-center rounded-full border-2 transition ${
                  isActive ? 'border-cta bg-cta' : 'border-border bg-transparent'
                }`}>
                  <Check className={`h-6 w-6 transition ${isActive ? 'text-cta-foreground' : 'text-border'}`} />
                </div>
              )
            )}

            {/* Label */}
            <div className={`text-[11px] font-medium leading-tight group-hover:text-primary ${
              isActive ? 'text-primary' : 'text-foreground'
            }`}>
              {c.label}
            </div>

            {/* Champ libre typeInput=1 */}
            {hasTypeInput && isActive && (
              <input
                type="text"
                placeholder="Précisez..."
                value={autreVal}
                onClick={(e) => e.stopPropagation()}
                onChange={(e) => handleAutre(c.id, e.target.value)}
                className="mt-1 w-full rounded border border-border px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/30"
              />
            )}
          </button>
        );
      })}
    </div>
  );
}
