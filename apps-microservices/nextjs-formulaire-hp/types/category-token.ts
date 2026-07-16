/**
 * Données URL injectées dans le payload chiffré du token catégorie.
 * Source de vérité unique partagée entre :
 *  - le middleware Edge (déchiffrement AES-256-CBC)
 *  - le client React (parsing du query param urlData)
 */
export interface CategoryTokenUrlData {
  id_question: number;
  id_reponse: number;
  equivalence: unknown[];
  abtest_UX_lead_version?: number;
  abtest2?: string;
  page_template_gtm?: string;
  funnel_context?: string;
  page_location_uri?: string;
}
