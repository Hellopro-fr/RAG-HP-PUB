'use client';

import { useEffect, useRef } from 'react';
import { ShieldCheck, Star, Check, ArrowRight } from 'lucide-react';
import type { AoFormQuestion } from '@/types/conseils';
import { IframeFormModal } from './IframeFormModal';
import { useAoQuoteForm } from '@/hooks/useAoQuoteForm';
import { AoChoixGrid } from './AoChoixGrid';
import { pushQuoteFormFunnel } from '@/lib/analytics/gtm';

interface HeroQuoteFormProps {
  question?: AoFormQuestion | null;
  infoRubrique?: { id: number; libelle: string } | null;
}

export function HeroQuoteForm({ question, infoRubrique }: HeroQuoteFormProps) {
  const formRef = useRef<HTMLDivElement>(null);
  const stepNumber = question?.stepNumber;

  useEffect(() => {
    const el = formRef.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        observer.disconnect();
        // Funnel "1ere-question" — contexte Hero. Helper partagé (ajoute session_id + product.category5).
        pushQuoteFormFunnel({ funnelContext: 'header pages conseils', stepNumber });
      },
      { threshold: 0.01 },
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [stepNumber]);

  const {
    modalOpen, startStep1, showError,
    questionLabel, isObligatoire,
    idRubrique, category,
    selectedChoixIds, autresNonVides,
    handleChoixClick, handleAutreChange, handleCtaClick, handleModalClose,
  } = useAoQuoteForm(question, infoRubrique);

  return (
    <>
      <div ref={formRef} className="rounded-2xl bg-card p-5 text-card-foreground shadow-2xl ring-1 ring-black/5">
        <div className="mb-1 flex items-center gap-2 text-sm">
          <ShieldCheck className="h-5 w-5 text-success" />
          <span className="font-semibold text-foreground">Recevez jusqu&apos;à 3 devis gratuits</span>
        </div>
        <p className="mb-3 text-xs text-muted-foreground">
          En 30 secondes, sans engagement. Comparez les meilleurs constructeurs de France.
        </p>
        <h3 className="mb-3 text-sm font-bold text-foreground">
          {questionLabel}
          {isObligatoire && <span className="text-cta"> *</span>}
        </h3>

        {showError && (
          <p className="mb-3 flex items-center gap-1.5 text-xs font-medium text-destructive">
            <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-destructive text-[10px] text-white">✕</span>
            Vous devez sélectionner une réponse avant de valider
          </p>
        )}

        <AoChoixGrid
          question={question}
          onChoixClick={handleChoixClick}
          onAutreChange={handleAutreChange}
        />

        <button
          type="button"
          onClick={handleCtaClick}
          className="mt-4 inline-flex h-11 w-full cursor-pointer items-center justify-center gap-2 rounded-md bg-cta px-4 text-sm font-bold uppercase tracking-wide text-cta-foreground shadow-lg transition hover:bg-cta-hover"
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

      <IframeFormModal
        idRubrique={idRubrique}
        category={category}
        selectedChoixIds={selectedChoixIds}
        autres={Object.keys(autresNonVides).length > 0 ? autresNonVides : undefined}
        startFromStep1={startStep1}
        withPrev
        ownsStep1
        open={modalOpen}
        onClose={handleModalClose}
      />
    </>
  );
}
