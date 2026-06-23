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

  /* Sticky bar — ref fraîche à chaque render, listener stable (enregistré une seule fois) */
  const stickyHandlerRef = useRef<() => void>(() => {});
  stickyHandlerRef.current = () => {
    // Le slot Hero est monté 2× (mobile `lg:hidden` + desktop `hidden lg:block`) → 2 instances
    // écoutent l'événement sticky. Seule l'instance réellement visible au breakpoint courant
    // doit ouvrir la modale ; l'autre (ancêtre display:none → offsetParent null) est ignorée,
    // sinon 2 iframes plein écran se chargent en concurrence et échouent (retry max).
    if (formRef.current && formRef.current.offsetParent === null) return;
    // Même comportement que le bouton du formulaire hero
    handleCtaClick();
    // En plus : si aucun choix + obligatoire, scroll vers le formulaire pour que l'erreur soit visible
    if (selectedChoixIds.length === 0 && isObligatoire) {
      document.getElementById('hero-trigger')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  useEffect(() => {
    const handler = () => stickyHandlerRef.current();
    window.addEventListener('hellopro:open-ao-form', handler);
    return () => window.removeEventListener('hellopro:open-ao-form', handler);
  }, []);

  return (
    <>
      <div ref={formRef} className="rounded-2xl bg-card p-5 text-card-foreground shadow-2xl ring-1 ring-black/5">
        <div className="mb-1 flex items-center gap-2 text-base">
          <ShieldCheck className="h-5 w-5 text-success" />
          <span className="font-semibold text-foreground">Recevez jusqu&apos;à 3 devis gratuits</span>
        </div>
        <p className="mb-3 text-base text-muted-foreground">
          En 30 secondes, sans engagement. Comparez les meilleurs fournisseurs.
        </p>
        {/* Invite de formulaire (pas un titre de structure) → <p> pour ne pas casser la hiérarchie des titres. */}
        <p className="mb-3 text-lg font-bold text-foreground">
          {questionLabel}
          {isObligatoire && <span className="text-cta"> *</span>}
        </p>

        {showError && (
          <p className="mb-3 flex items-center gap-1.5 text-base font-medium text-destructive">
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
          className="mt-4 flex w-full cursor-pointer flex-col items-center justify-center gap-0.5 rounded-md bg-cta px-4 py-2.5 text-base font-bold uppercase tracking-wide text-cta-foreground shadow-lg transition hover:bg-cta-hover sm:h-11 sm:flex-row sm:gap-2 sm:py-0"
        >
          <span>Faire une demande groupée</span>
          <span className="flex items-center gap-1.5">(1 min) <ArrowRight className="h-4 w-4" /></span>
        </button>

        <ul className="mt-3 space-y-1 text-sm text-muted-foreground">
          {['100 % gratuit', 'Sans engagement', 'Pros vérifiés près de chez vous'].map((t) => (
            <li key={t} className="flex items-center gap-1.5">
              <Check className="h-3.5 w-3.5 text-success" /> {t}
            </li>
          ))}
        </ul>

        <div className="mt-3 flex items-center justify-center gap-1 border-t border-border pt-2 text-sm">
          <div className="flex" role="img" aria-label="4,2 sur 5">
            {[1, 2, 3, 4].map((i) => (
              <Star key={i} className="h-3.5 w-3.5 fill-rating text-rating" />
            ))}
            <Star className="h-3.5 w-3.5 fill-rating/40 text-rating" />
          </div>
          <span className="font-semibold text-foreground">4,2/5</span>
          <span className="text-muted-foreground">&nbsp;· 222 avis vérifiés</span>
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
