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
  api_response?: any; // Debug Gemini — ignoré côté frontend
}

/** État de l'estimation de prix dans le flow-store */
export interface PriceEstimationState {
  data: PrixReponse | null;
  error: string | null;
}
