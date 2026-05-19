// =============================================================================
// Types pour l'API d'estimation de prix
// =============================================================================

/** Critère non matché sur un exemple produit */
export interface CritereNonMatch {
  caracteristique: string;
  valeur_produit: string;
  valeur_requete: string;
}

/** Exemple de produit retourné par l'API prix */
export interface PrixExempleProduit {
  nom: string;
  fournisseur: string;
  date?: string;            // Format ISO "2025-08-31" — optionnel : la v2 ne le renvoie pas
  prix: number;
  tva: string;              // "HT" ou "TTC"
  criteres_non_matches?: CritereNonMatch[];
  pourquoi_pertinent: string;
}

/** Fourchette de prix estimée */
export interface PrixFourchette {
  borne_basse: number;
  borne_haute: number;
  prix_moyen: number;       // Moyenne arithmétique (nouveau v2)
  prix_median: number;
  devise: string;           // "EUR"
  tva: string;              // "HT"
  niveau_confiance: 'fort' | 'moyen' | 'faible';
  nb_references_retenues: number;
  nb_references_ignorees: number;
}

/** Stats de matching renvoyées par l'API v2 (debug/tracking — `results` est strippé côté proxy) */
export interface PrixMatchingInfo {
  erreur: boolean;
  message?: string;
  id_categorie?: string;
  nb_equivalences: number;
  nb_results: number;
  results_count_retenues?: number;
}

/** Contenu de la réponse prix */
export interface PrixReponse {
  phrase_prix: string;
  fourchette: PrixFourchette;
  exemples_produits: PrixExempleProduit[];
  /** Options de réponse calibrées sur la fourchette pour la question budget (calculées côté backend) */
  budget_reponse?: string[];
}

/** Réponse complète de l'API prix */
export interface PrixApiResponse {
  success: boolean;
  reponse: PrixReponse | null;   // null quand le backend ne trouve pas de prix (v2)
  matching?: PrixMatchingInfo;   // stats de matching (v2)
  api_response?: any;      // Debug Gemini — ignoré côté frontend
  time_elapsed?: number;   // secondes (ex: 6.101902)
  message?: string;        // ex: "50 chunks traités en 6.1s"
}

/** État de l'estimation de prix dans le flow-store */
export interface PriceEstimationState {
  data: PrixReponse | null;
  error: string | null;
}

/** Returns true when a valid price estimation with non-zero borne_basse is available. */
export function hasPriceEstimation(pe: PriceEstimationState | null | undefined): boolean {
  return pe?.data != null && pe.data.fourchette.borne_basse !== 0;
}

/**
 * Returns true when the price estimation is rich enough to be displayed on /budget:
 * non-zero borne_basse, distinct bornes (real range), and more than 2 example products.
 * When this returns false, the /budget page is skipped at the navigation step
 * (see questionnaire-client.tsx) — the page is meaningless without a displayable card.
 */
export function hasDisplayablePriceEstimation(pe: PriceEstimationState | null | undefined): boolean {
  const data = pe?.data;
  if (!data) return false;
  if (data.fourchette.borne_basse === 0) return false;
  if (data.fourchette.borne_basse === data.fourchette.borne_haute) return false;
  return (data.exemples_produits?.length ?? 0) > 2;
}
