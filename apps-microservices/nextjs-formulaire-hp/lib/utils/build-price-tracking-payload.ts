import { hasPriceEstimation } from '@/types/prix';
import type { PriceEstimationState } from '@/types/prix';

/**
 * Builds a standardized price estimation payload for DB tracking events.
 * Used across selection, contact, and conversion tracking to ensure consistency.
 */
export function buildPriceTrackingPayload(pe: PriceEstimationState | null | undefined) {
  const hasEstimation = hasPriceEstimation(pe);
  const borneBasse = pe?.data?.fourchette?.borne_basse ?? null;
  const borneHaute = pe?.data?.fourchette?.borne_haute ?? null;
  const nbExemples = pe?.data?.exemples_produits?.length ?? 0;

  // Conditions d'affichage du bandeau prix (miroir de SupplierSelectionModal)
  let bandeauAffiche = false;
  let raisonNonAffiche: string | null = null;

  if (!hasEstimation) {
    raisonNonAffiche = 'pas_estimation';
  } else if (borneBasse === 0) {
    raisonNonAffiche = 'borne_basse_zero';
  } else if (borneBasse === borneHaute) {
    raisonNonAffiche = 'bornes_identiques';
  } else if (nbExemples <= 2) {
    raisonNonAffiche = 'exemples_insuffisants';
  } else {
    bandeauAffiche = true;
  }

  return {
    has_estimation: hasEstimation,
    bandeau_prix_affiche: bandeauAffiche,
    raison_non_affiche: raisonNonAffiche,
    borne_basse: borneBasse,
    borne_haute: borneHaute,
    prix_median: pe?.data?.fourchette?.prix_median ?? null,
    niveau_confiance: pe?.data?.fourchette?.niveau_confiance ?? null,
    nb_exemples: nbExemples,
  };
}
