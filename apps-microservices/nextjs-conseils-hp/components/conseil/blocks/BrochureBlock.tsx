'use client';

import { useState } from 'react';
import { Download, FileText, Check } from 'lucide-react';
import type { BrochureBlockData } from '@/types/blocks/brochure';

interface BrochureBlockProps {
  data: BrochureBlockData;
}

export function BrochureBlock({ data }: BrochureBlockProps) {
  const {
    title,
    description,
    bullets,
    ctaLabel = 'Recevoir le guide gratuit',
  } = data;

  const [email, setEmail] = useState('');
  const [accepted, setAccepted] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email || !accepted) return;
    // TODO Phase 8 : appel API soumission brochure
    setSubmitted(true);
  }

  return (
    <section
      id="guide"
      className="not-prose my-12 scroll-mt-32 overflow-hidden rounded-2xl border border-border bg-card shadow-sm"
    >
      <div className="grid gap-0 md:grid-cols-[1fr_1.2fr]">
        {/* Colonne gauche — pitch */}
        <div className="flex flex-col justify-center bg-primary p-8 text-primary-foreground">
          <span className="mb-3 inline-flex w-fit items-center rounded-full bg-cta px-3 py-1 text-xs font-bold uppercase tracking-wide text-cta-foreground">
            Guide gratuit
          </span>
          <FileText className="mb-3 h-10 w-10 text-cta" />
          <h3 className="text-2xl font-extrabold leading-tight">{title}</h3>
          {description && (
            <p className="mt-2 text-sm text-primary-foreground/85">{description}</p>
          )}
          <ul className="mt-4 space-y-1.5 text-sm">
            {bullets.map((t) => (
              <li key={t} className="flex items-start gap-2">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-cta" /> {t}
              </li>
            ))}
          </ul>
        </div>

        {/* Colonne droite — formulaire */}
        {submitted ? (
          <div className="flex flex-col items-center justify-center gap-4 p-8 text-center">
            <Check className="h-12 w-12 text-success" />
            <p className="text-lg font-bold text-foreground">Guide envoyé !</p>
            <p className="text-sm text-muted-foreground">
              Vérifiez votre boîte mail.
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col justify-center gap-4 p-8">
            <div>
              <label className="mb-2 block text-sm font-semibold text-foreground">
                Recevez le guide par e-mail
              </label>
              <input
                type="email"
                required
                placeholder="votre.email@exemple.fr"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="h-12 w-full rounded-md border border-input bg-background px-3 text-sm focus:border-primary focus:outline-none"
              />
            </div>
            <label className="flex items-start gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={accepted}
                onChange={(e) => setAccepted(e.target.checked)}
                className="mt-0.5 h-4 w-4 accent-primary"
              />
              J&apos;accepte de recevoir le guide et les communications HelloPro. Voir notre
              Politique de confidentialité.
            </label>
            <button
              type="submit"
              className="inline-flex h-12 items-center justify-center gap-2 rounded-md bg-cta text-sm font-bold uppercase tracking-wide text-cta-foreground hover:bg-cta-hover disabled:opacity-50"
              disabled={!email || !accepted}
            >
              <Download className="h-4 w-4" /> {ctaLabel}
            </button>
            <p className="text-xs text-muted-foreground">
              Envoi immédiat par e-mail · 100 % gratuit · sans engagement
            </p>
          </form>
        )}
      </div>
    </section>
  );
}
