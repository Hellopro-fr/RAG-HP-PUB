'use client';

import { useEffect, useRef } from 'react';
import { Star, Check, ArrowRight } from 'lucide-react';
import type { QuoteFormBlockData } from '@/types/blocks/quote-form';
import type { AoFormQuestion } from '@/types/conseils';
import { IframeFormModal } from '@/components/conseil/IframeFormModal';
import { AoChoixGrid } from '@/components/conseil/AoChoixGrid';
import { useAoQuoteForm } from '@/hooks/useAoQuoteForm';
import { pushQuoteFormFunnel } from '@/lib/analytics/gtm';

interface QuoteFormBlockProps {
  data: QuoteFormBlockData;
  /** Données formulaire AO depuis l'API (même que HeroQuoteForm) */
  formulaire_ao?: AoFormQuestion | null;
  infoRubrique?: { id: number; libelle: string } | null;
}

export function QuoteFormBlock({ data, formulaire_ao, infoRubrique }: QuoteFormBlockProps) {
  const {
    title    = 'Trouvez les fournisseurs,',
    subtitle = "passez à l'action.",
    ctaLabel = 'Faire une demande groupée (1 min)',
  } = data;

  const parenIdx = ctaLabel.indexOf(' (');
  const ctaMain = parenIdx !== -1 ? ctaLabel.slice(0, parenIdx) : ctaLabel;
  const ctaSub  = parenIdx !== -1 ? ctaLabel.slice(parenIdx + 1) : '';

  const {
    modalOpen, startStep1, showError,
    questionLabel, isObligatoire,
    idRubrique, category,
    selectedChoixIds, autresNonVides,
    handleChoixClick, handleAutreChange, handleCtaClick, handleModalClose,
  } = useAoQuoteForm(formulaire_ao, infoRubrique);

  const sectionRef = useRef<HTMLElement>(null);
  const stepNumber = formulaire_ao?.stepNumber;

  /* Funnel "1ere-question" — contexte CTA milieu d'article, déclenché à la 1re vue du bloc. */
  useEffect(() => {
    const el = sectionRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        observer.disconnect();
        pushQuoteFormFunnel({ funnelContext: 'cta devis pages conseils', stepNumber });
      },
      { threshold: 0.01 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [stepNumber]);

  return (
    <>
      <section
        ref={sectionRef}
        className="not-prose my-12 overflow-hidden rounded-2xl border border-primary/20 bg-primary text-primary-foreground shadow-xl"
      >
        <div className="grid gap-0 lg:grid-cols-[1fr_1.1fr]">

          {/* ── Colonne gauche — pitch ── */}
          <div className="flex flex-col justify-center gap-4 p-6 lg:p-8">
            <span className="inline-flex w-fit items-center rounded-full bg-cta px-3 py-1 text-xs font-bold uppercase tracking-wide text-cta-foreground">
              Étape suivante
            </span>
            <h3 className="text-2xl font-extrabold leading-tight lg:text-[1.75rem]">
              {title}
              <br />
              <span className="text-cta">{subtitle}</span>
            </h3>
            <p className="text-base text-primary-foreground/85">
              Décrivez votre projet en 30 secondes et recevez{' '}
              <strong className="text-primary-foreground">jusqu&apos;à 3 devis gratuits</strong> de
              fournisseurs vérifiés près de chez vous.
            </p>
            <ul className="mt-1 space-y-1.5 text-sm text-primary-foreground/90">
              {['Devis personnalisés sous 48h', 'Comparez plusieurs offres en un clic', 'Sans engagement · 100 % gratuit'].map((t) => (
                <li key={t} className="flex items-center gap-2">
                  <Check className="h-4 w-4 text-cta" /> {t}
                </li>
              ))}
            </ul>
            <div className="mt-2 flex items-center gap-2 text-sm text-primary-foreground/80">
              <div className="flex" aria-label="4,2 sur 5">
                {[1, 2, 3, 4].map((i) => (
                  <Star key={i} className="h-4 w-4 fill-rating text-rating" />
                ))}
                <Star className="h-4 w-4 fill-rating/40 text-rating" />
              </div>
              <span className="font-semibold text-primary-foreground">4,2/5</span>
              <span>· 222 avis vérifiés</span>
            </div>
          </div>

          {/* ── Colonne droite — formulaire ── */}
          <div className="bg-card p-5 text-card-foreground lg:p-6">
            <h4 className="mb-3 text-lg font-bold text-foreground">
              {questionLabel}
              {isObligatoire && <span className="text-cta"> *</span>}
            </h4>

            {showError && (
              <p className="mb-3 flex items-center gap-1.5 text-xs font-medium text-destructive">
                <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-destructive text-[10px] text-white">✕</span>
                Vous devez sélectionner une réponse avant de valider
              </p>
            )}

            <AoChoixGrid
              question={formulaire_ao}
              onChoixClick={handleChoixClick}
              onAutreChange={handleAutreChange}
            />

            <button
              type="button"
              onClick={handleCtaClick}
              className="mt-4 flex w-full cursor-pointer flex-col items-center justify-center gap-0.5 rounded-md bg-cta px-4 py-2.5 text-base font-bold uppercase tracking-wide text-cta-foreground shadow-lg transition hover:bg-cta-hover sm:h-12 sm:flex-row sm:gap-2 sm:py-0"
            >
              <span>{ctaMain}</span>
              <span className="flex items-center gap-1.5">
                {ctaSub && `${ctaSub} `}<ArrowRight className="h-4 w-4" />
              </span>
            </button>
          </div>
        </div>
      </section>

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
