'use client';

import { useEffect, useMemo, useRef } from 'react';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import Image from 'next/image';
import { cn, getAssetPath } from '@/lib/utils';
import { useFlowStore } from '@/lib/stores/flow-store';
import { useFlowNavigation } from '@/hooks/useFlowNavigation';
import { trackBudgetView, trackBudgetComplete, trackBudgetReturn } from '@/lib/analytics';
import { hasDisplayablePriceEstimation } from '@/types/prix';
import BudgetEstimate from '@/components/flow/BudgetEstimate';
import BudgetQuestionScreen from '@/components/flow/BudgetQuestionScreen';
import CategoryHeaderBar from '@/components/flow/CategoryHeaderBar';
import type { BudgetOption } from '@/types/budget';

const hpLogo = getAssetPath('/images/hp-logo.svg');

/**
 * Page /budget — intercalée entre le MatchingLoader et /selection.
 *
 * Affiche :
 *  - la card estimatif prix (`BudgetEstimate`) si l'API a renvoyé une fourchette valide
 *  - la question budget (`BudgetQuestionScreen`) avec 6 options statiques
 *  - footer nav (Précédent / Voir ma sélection)
 *
 * Comportement clé :
 *  - "Voir ma sélection" est désactivé tant qu'aucun budget n'est sélectionné
 *  - "Précédent" appelle `goToQuestionnaire()` — la logique existante de
 *    `NeedsQuestionnaire` (lignes 109-119) appelle `goToLastQuestion()` au
 *    remount → l'utilisateur retrouve sa dernière question répondue
 *  - Si `priceEstimation.data` est null (API échouée), la card prix n'est
 *    simplement pas rendue ; la question budget reste fonctionnelle
 */
const BudgetClient = () => {
  const {
    categoryName,
    categoryVignette,
    priceEstimation,
    userBudgetRange,
    setUserBudgetRange,
  } = useFlowStore();
  const { goToQuestionnaire, goToSelection } = useFlowNavigation();

  const fmtPrice = (n: number) =>
    new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 }).format(n) + ' €';

  const data = priceEstimation?.data;
  const showEstimate = hasDisplayablePriceEstimation(priceEstimation);

  const hasTrackedEstimate = useRef(false);

  useEffect(() => {
    if (!showEstimate || hasTrackedEstimate.current) return;

    const navEntries = performance.getEntriesByType('navigation') as PerformanceNavigationTiming[];
    const navType = navEntries.length > 0 ? navEntries[0].type : 'navigate';
    if (navType === 'back_forward') return;

    hasTrackedEstimate.current = true;
    trackBudgetView();
  }, [showEstimate]);

  const priceItems = data
    ? (data.exemples_produits || []).map((ex) => ({
        price:
          new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 }).format(ex.prix) +
          ` €${ex.tva && ex.tva !== 'inconnu' ? ` ${ex.tva}` : ''}`,
        equipment: `${ex.nom}${ex.fournisseur ? ` — ${ex.fournisseur}` : ''}`,
        date: ex.date || '',
      }))
    : [];

  // Options dynamiques calibrées par l'API prix (champ budget_reponse).
  // id = label pour garantir la persistance déterministe dans userBudgetRange.
  const dynamicOptions: BudgetOption[] = useMemo(
    () => data?.budget_reponse?.map((label) => ({ id: label, label })) ?? [],
    [data?.budget_reponse]
  );

  // Garde-fou : si l'utilisateur atterrit ici sans options (entrée directe URL,
  // bug de timing, F5), on rebascule silencieusement vers /selection.
  // handleComplete dans questionnaire-client filtre déjà ce cas en amont.
  useEffect(() => {
    if (dynamicOptions.length === 0) {
      goToSelection();
    }
  }, [dynamicOptions.length, goToSelection]);

  const hasSelection = userBudgetRange !== null;
  const handleContinue = () => {
    if (!hasSelection) return;
    trackBudgetComplete(userBudgetRange!);
    goToSelection();
  };

  const handleBack = () => {
    trackBudgetReturn(userBudgetRange);
    goToQuestionnaire();
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background">
      {/* Header simplifié — logo seul */}
      <div className="px-4 py-2.5 sm:px-6 border-b border-border">
        <Image src={hpLogo} alt="Hellopro" width={120} height={28} className="h-6 sm:h-7 w-auto" />
      </div>

      {/* Bandeau catégorie sans barre de progression (conforme Lovable budget) */}
      <CategoryHeaderBar
        categoryName={categoryName || ''}
        categoryVignette={categoryVignette}
      />

      <div className="flex-1 overflow-y-auto">
        <div className="px-4 sm:px-6 lg:px-10 pt-5 sm:pt-8 pb-32 sm:pb-6">
          <div className="mx-auto max-w-2xl space-y-5">
            {/* Card estimatif prix — rendue seulement si data valide */}
            {showEstimate && data && (
              <BudgetEstimate
                priceMin={fmtPrice(data.fourchette.borne_basse)}
                priceMax={fmtPrice(data.fourchette.borne_haute)}
                priceMoy={fmtPrice(data.fourchette.prix_moyen)}
                priceCount={priceItems.length}
                priceItems={priceItems.length > 0 ? priceItems : undefined}
                detailDescription={data.phrase_prix}
              />
            )}

            {/* Question budget — options dynamiques venant de /api/prix.budget_reponse */}
            <BudgetQuestionScreen
              options={dynamicOptions}
              selectedId={userBudgetRange}
              onSelect={setUserBudgetRange}
            />

            {/* Footer desktop (sm+) — bouton Précédent + Voir ma sélection + rassurance */}
            <div className="hidden sm:block pt-4 space-y-3">
              <div className="flex items-center justify-between">
                <button
                  type="button"
                  onClick={handleBack}
                  className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-foreground hover:text-foreground/70 transition-colors"
                >
                  <ArrowLeft className="h-4 w-4" />
                  Précédent
                </button>

                <button
                  type="button"
                  onClick={handleContinue}
                  disabled={!hasSelection}
                  className={cn(
                    'flex items-center gap-2 rounded-lg px-6 py-3 text-sm font-semibold transition-all',
                    hasSelection
                      ? 'bg-accent text-accent-foreground hover:bg-accent/90 shadow-lg shadow-accent/25'
                      : 'bg-muted text-muted-foreground cursor-not-allowed'
                  )}
                >
                  Voir ma sélection
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>

              <div className="mt-5 rounded-lg border border-primary/15 bg-primary/5 px-4 py-3 text-center">
                <p className="text-xs text-muted-foreground">
                  Information confidentielle, partagée uniquement avec les fournisseurs sélectionnés.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Footer mobile sticky (Précédent icon + CTA pleine largeur) */}
      <div className="sm:hidden fixed bottom-0 left-0 right-0 bg-background border-t border-border/40 shadow-[0_-2px_8px_rgba(0,0,0,0.05)]">
        <div className="flex items-center gap-3 p-4">
          <button
            type="button"
            onClick={handleBack}
            aria-label="Précédent"
            className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={handleContinue}
            disabled={!hasSelection}
            className={cn(
              'flex-1 flex items-center justify-center gap-2 rounded-lg px-6 py-3.5 text-base font-semibold transition-all',
              hasSelection
                ? 'bg-accent text-accent-foreground shadow-lg shadow-accent/25'
                : 'bg-muted text-muted-foreground cursor-not-allowed'
            )}
          >
            Voir ma sélection
            <ArrowRight className="h-5 w-5" />
          </button>
        </div>
      </div>
    </div>
  );
};

export default BudgetClient;
