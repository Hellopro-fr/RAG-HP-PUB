/**
 * Slots A/B test GTM partagés HelloPro (dimensions custom GA4 abtest1..abtest5).
 * Tout slot présent dans le bloc `data` du token chiffré est propagé dans chaque
 * event GTM devis_funnel_formulaire du funnel (omis si absent).
 */
export const ABTEST_SLOTS = ['abtest1', 'abtest2', 'abtest3', 'abtest4', 'abtest5'] as const;
export type AbtestSlot = (typeof ABTEST_SLOTS)[number];

/**
 * Données URL injectées dans le payload chiffré du token catégorie.
 * Source de vérité unique partagée entre :
 *  - le middleware Edge (déchiffrement AES-256-CBC)
 *  - le client React (parsing du query param urlData)
 */
export interface CategoryTokenUrlData extends Partial<Record<AbtestSlot, string>> {
  id_question: number;
  id_reponse: number;
  equivalence: unknown[];
  abtest_UX_lead_version?: number;
  page_template_gtm?: string;
  funnel_context?: string;
  page_location_uri?: string;
}
