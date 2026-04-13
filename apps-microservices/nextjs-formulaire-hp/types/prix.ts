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
  date: string;             // Format ISO "2025-08-31"
  prix: number;
  tva: string;              // "HT" ou "TTC"
  criteres_non_matches?: CritereNonMatch[];
  pourquoi_pertinent: string;
}

/** Fourchette de prix estimée */
export interface PrixFourchette {
  borne_basse: number;
  borne_haute: number;
  prix_median: number;
  devise: string;           // "EUR"
  tva: string;              // "HT"
  niveau_confiance: 'fort' | 'moyen' | 'faible';
  nb_references_retenues: number;
  nb_references_ignorees: number;
}

/** Contenu de la réponse prix */
export interface PrixReponse {
  phrase_prix: string;
  fourchette: PrixFourchette;
  exemples_produits: PrixExempleProduit[];
}

/** Réponse complète de l'API prix */
export interface PrixApiResponse {
  success: boolean;
  reponse: PrixReponse;
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
