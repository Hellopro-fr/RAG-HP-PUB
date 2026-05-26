'use client';

import { useState } from 'react';
import { ShieldCheck, Star, Check, HelpCircle, MoreHorizontal, ArrowRight } from 'lucide-react';
import type { QuoteFormBlockData } from '@/types/blocks/quote-form';

interface QuoteFormBlockProps {
  data: QuoteFormBlockData;
}

const CHOICES: { label: string; emoji: string }[] = [
  { label: 'Elevage bovin', emoji: '🐄' },
  { label: 'Elevage porcin', emoji: '🐖' },
  { label: 'Elevage ovin', emoji: '🐑' },
  { label: 'Elevage caprin', emoji: '🐐' },
  { label: 'Elevage cunicole', emoji: '🐇' },
  { label: 'Autre', emoji: '⋯' },
  { label: 'Je ne sais pas encore', emoji: '?' },
];

export function QuoteFormBlock({ data }: QuoteFormBlockProps) {
  const {
    title = 'Maintenant que vous connaissez les prix,',
    subtitle = 'passez à l\'action.',
    ctaLabel = 'Faire une demande groupée (1 min)',
  } = data;

  const [selected, setSelected] = useState('');

  return (
    <section className="not-prose my-12 overflow-hidden rounded-2xl border border-primary/20 bg-primary text-primary-foreground shadow-xl">
      <div className="grid gap-0 lg:grid-cols-[1fr_1.1fr]">
        {/* Colonne gauche — pitch */}
        <div className="flex flex-col justify-center gap-4 p-6 lg:p-8">
          <span className="inline-flex w-fit items-center rounded-full bg-cta px-3 py-1 text-xs font-bold uppercase tracking-wide text-cta-foreground">
            Étape suivante
          </span>
          <h3 className="text-2xl font-extrabold leading-tight lg:text-[1.75rem]">
            {title}
            <br />
            <span className="text-cta">{subtitle}</span>
          </h3>
          <p className="text-sm text-primary-foreground/85 lg:text-base">
            Décrivez votre projet en 30 secondes et recevez{' '}
            <strong className="text-primary-foreground">jusqu&apos;à 3 devis gratuits</strong> de
            constructeurs vérifiés près de chez vous.
          </p>
          <ul className="mt-1 space-y-1.5 text-sm text-primary-foreground/90">
            {['Devis personnalisés sous 48h', 'Comparez plusieurs offres en un clic', 'Sans engagement · 100 % gratuit'].map((t) => (
              <li key={t} className="flex items-center gap-2">
                <Check className="h-4 w-4 text-cta" /> {t}
              </li>
            ))}
          </ul>
          <div className="mt-2 flex items-center gap-2 text-xs text-primary-foreground/80">
            <div className="flex" aria-label="4,2 sur 5">
              {[1, 2, 3, 4].map((i) => (
                <Star key={i} className="h-4 w-4 fill-rating text-rating" />
              ))}
              <Star className="h-4 w-4 fill-rating/40 text-rating" />
            </div>
            <span className="font-semibold text-primary-foreground">4,2/5</span>
            <span>· 9 697 avis vérifiés</span>
          </div>
        </div>

        {/* Colonne droite — formulaire */}
        <div className="bg-card p-5 text-card-foreground lg:p-6">
          <div className="mb-1 flex items-center gap-2 text-sm">
            <ShieldCheck className="h-5 w-5 text-success" />
            <span className="font-semibold text-foreground">
              Recevez jusqu&apos;à 3 devis gratuits
            </span>
          </div>
          <p className="mb-3 text-xs text-muted-foreground">
            En 30 secondes, sans engagement. Comparez les meilleurs constructeurs de France.
          </p>
          <h4 className="mb-3 text-sm font-bold text-foreground">
            Quel type d&apos;élevage souhaitez-vous réaliser dans le bâtiment ?{' '}
            <span className="text-cta">*</span>
          </h4>
          <div className="grid grid-cols-4 gap-2">
            {CHOICES.map((c) => {
              const isActive = selected === c.label;
              return (
                <button
                  key={c.label}
                  type="button"
                  onClick={() => setSelected(c.label)}
                  className={`group flex flex-col items-center gap-2 rounded-lg border bg-background px-2 pb-2 pt-3 text-center transition hover:border-primary hover:shadow-sm ${
                    isActive ? 'border-primary ring-2 ring-primary/30' : 'border-border'
                  }`}
                >
                  <div className="flex h-14 w-14 items-center justify-center overflow-hidden rounded-full bg-muted text-2xl ring-1 ring-border">
                    {c.emoji}
                  </div>
                  <div className="text-[11px] font-medium leading-tight text-foreground group-hover:text-primary">
                    {c.label}
                  </div>
                </button>
              );
            })}
          </div>
          <button
            type="button"
            className="mt-4 inline-flex h-12 w-full items-center justify-center gap-2 rounded-md bg-cta px-4 text-sm font-bold uppercase tracking-wide text-cta-foreground shadow-lg transition hover:bg-cta-hover"
          >
            {ctaLabel} <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </section>
  );
}
