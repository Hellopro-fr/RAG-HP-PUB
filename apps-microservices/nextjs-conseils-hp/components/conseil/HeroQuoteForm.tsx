'use client';

import { useState } from 'react';
import Image from 'next/image';
import { ShieldCheck, Star, Check, ArrowRight } from 'lucide-react';
import type { AoFormQuestion } from '@/types/conseils';

interface HeroQuoteFormProps {
  question?: AoFormQuestion | null;
  infoRubrique?: { id: number; libelle: string } | null;
}

/**
 * Formulaire devis affiché dans le slot droit du Hero (pages prix et autre).
 * Reçoit la première question AO depuis l'API (formulaire_ao[0]).
 * Voir CLAUDE.md §2.2 — slot Hero.
 */
export function HeroQuoteForm({ question }: HeroQuoteFormProps) {
  const [selected, setSelected] = useState<string | number>('');

  const questionLabel = question?.question ?? 'Quel est votre besoin ?';
  const choix = question?.choix ?? [];

  return (
    <div className="rounded-2xl bg-card p-5 text-card-foreground shadow-2xl ring-1 ring-black/5">
      <div className="mb-1 flex items-center gap-2 text-sm">
        <ShieldCheck className="h-5 w-5 text-success" />
        <span className="font-semibold text-foreground">
          Recevez jusqu&apos;à 3 devis gratuits
        </span>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        En 30 secondes, sans engagement. Comparez les meilleurs constructeurs de France.
      </p>
      <h3 className="mb-3 text-sm font-bold text-foreground">
        {questionLabel} <span className="text-cta">*</span>
      </h3>

      {choix.length > 0 && (
        <div className="grid grid-cols-4 gap-2">
          {choix.map((c) => {
            const isActive = selected === c.id;
            return (
              <button
                key={c.id}
                type="button"
                onClick={() => setSelected(c.id)}
                className={`group flex flex-col items-center gap-2 rounded-lg border bg-background px-2 pb-2 pt-3 text-center transition hover:border-primary hover:shadow-sm ${
                  isActive ? 'border-primary ring-2 ring-primary/30' : 'border-border'
                }`}
              >
                <div className="flex h-14 w-14 items-center justify-center overflow-hidden rounded-full bg-muted ring-1 ring-border">
                  {c.image ? (
                    <Image
                      src={c.image}
                      alt={c.label}
                      width={56}
                      height={56}
                      className="h-full w-full object-cover"
                      unoptimized
                    />
                  ) : (
                    <span className="text-xs text-muted-foreground">···</span>
                  )}
                </div>
                <div className="text-[11px] font-medium leading-tight text-foreground group-hover:text-primary">
                  {c.label}
                </div>
              </button>
            );
          })}
        </div>
      )}

      <button
        type="button"
        className="mt-4 inline-flex h-11 w-full items-center justify-center gap-2 rounded-md bg-cta px-4 text-sm font-bold uppercase tracking-wide text-cta-foreground shadow-lg transition hover:bg-cta-hover"
      >
        Faire une demande groupée (1 min) <ArrowRight className="h-4 w-4" />
      </button>
      <ul className="mt-3 space-y-1 text-xs text-muted-foreground">
        {['100 % gratuit', 'Sans engagement', 'Pros vérifiés près de chez vous'].map((t) => (
          <li key={t} className="flex items-center gap-1.5">
            <Check className="h-3.5 w-3.5 text-success" /> {t}
          </li>
        ))}
      </ul>
      <div className="mt-3 flex items-center justify-center gap-1 border-t border-border pt-2 text-xs">
        <div className="flex" aria-label="4,2 sur 5">
          {[1, 2, 3, 4].map((i) => (
            <Star key={i} className="h-3.5 w-3.5 fill-rating text-rating" />
          ))}
          <Star className="h-3.5 w-3.5 fill-rating/40 text-rating" />
        </div>
        <span className="font-semibold text-foreground">4,2/5</span>
        <span className="text-muted-foreground">&nbsp;· 9 697 avis vérifiés</span>
      </div>
    </div>
  );
}
