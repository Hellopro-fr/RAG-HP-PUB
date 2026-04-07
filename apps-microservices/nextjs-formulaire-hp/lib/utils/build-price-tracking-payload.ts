import { hasPriceEstimation } from '@/types/prix';
import type { PriceEstimationState } from '@/types/prix';

/**
 * Builds a standardized price estimation payload for DB tracking events.
 * Used across selection, contact, and conversion tracking to ensure consistency.
 */
export function buildPriceTrackingPayload(pe: PriceEstimationState | null | undefined) {
  return {
    has_estimation: hasPriceEstimation(pe),
    borne_basse: pe?.data?.fourchette?.borne_basse ?? null,
    borne_haute: pe?.data?.fourchette?.borne_haute ?? null,
    prix_median: pe?.data?.fourchette?.prix_median ?? null,
    niveau_confiance: pe?.data?.fourchette?.niveau_confiance ?? null,
    nb_exemples: pe?.data?.exemples_produits?.length ?? 0,
  };
}
