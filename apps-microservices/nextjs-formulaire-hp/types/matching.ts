// ========================================
// MATCHING API TYPES
// ========================================

/**
 * Caractéristique d'un produit dans la réponse matching
 */
export interface MatchingCharacteristic {
  /** Statut du matching: 1=match, 2=écart, 3=bloquant, 4=non_renseigné */
  statut_matching: 1 | 2 | 3 | 4;
  /** ID de la caractéristique */
  id_caracteristique: number;
  /** Type: 1=numérique, 2=textuelle */
  type_caracteristique: 1 | 2;
  /** Valeur numérique exacte (si type 1) */
  valeur?: number | string | null;
  /** Valeur numérique min (si type 1, pour les plages) */
  valeur_min?: number | string | null;
  /** Valeur numérique max (si type 1, pour les plages) */
  valeur_max?: number | string | null;
  /** Unité (si type 1) */
  unite?: string | null;
  /** IDs des valeurs (si type 2) */
  id_valeur: number[];
  /** Poids de la caractéristique dans le score */
  poids: number;
  /** Barème pour debug (ne pas afficher dans UI) */
  bareme: number;
  /** Poids question (même valeur qu'envoyée à l'API) */
  poids_question: number;
}

/**
 * Données renvoyées par le Rerank (LLM)
 */
export interface LlmResponse {
  rang: number;
  id_produit: string;
  nom: string;
  score: number;
  completude: number;
  base_calcul: string;
  decision: string;
  fournisseur_client: boolean;
  justification: string;
}

/**
 * Produit retourné par l'API matching
 */
export interface MatchingProduct {
  /** Position dans le classement */
  rang: number;
  /** Identifiant du produit */
  id_produit: string;
  /** Score de matching (0 à 1) */
  score: number;
  /** Détails du matching par caractéristique */
  caracteristique: MatchingCharacteristic[];
  /** Coefficient géographique (debug uniquement) */
  coeff_geo: number;
  /** Coefficient type fournisseur (debug uniquement) */
  coeff_type_frns: number;
  /** Coefficient caractéristique (debug uniquement) */
  coeff_caracteristique?: number;
  /** Coefficient état score (debug uniquement) */
  coeff_etat_score?: number;
  /** Response du LLM pour le rerank (debug uniquement) */
  llm_response?: LlmResponse;
}

/**
 * Réponse complète de l'API matching
 */
export interface MatchingResponse {
  /** Produits recommandés (top) */
  top_produit: MatchingProduct[];
  /** Autres produits */
  liste_produit: MatchingProduct[];
  /** Temps de traitement en secondes */
  temps_de_traitement: number;
}

/**
 * Statuts de matching avec leur signification
 * Note: Dans l'UI, les statuts 2 et 3 sont traités comme des écarts
 */
export const MATCHING_STATUS = {
  MATCH: 1,        // Matche
  GAP: 2,          // Écart
  BLOCKING: 3,     // Bloquant (traité comme écart dans l'UI)
  NOT_PROVIDED: 4, // Non renseigné
} as const;

export type MatchingStatus = typeof MATCHING_STATUS[keyof typeof MATCHING_STATUS];

// =============================================================================
// PRODUCT INFO API TYPES (get_info_produit)
// =============================================================================

/**
 * Informations produit retournées par l'API get_info_produit
 */
export interface ProductInfoData {
  id_produit: string;
  titre_produit: string;
  description_produit: string;
  prix_produit: string;
  url_produit: string;
  image_produit: string | string[];  // Peut être un tableau de chemins ou une string avec séparateurs
  livraison_produit: string;
  stock_produit: string;
  categorie_produit: string;
  date_scrapping: string;
}

/**
 * Informations catégorie du produit
 */
export interface ProductCategoryInfo {
  id_categorie: string;
  nom_categorie: string | null;
}

/**
 * Informations vendeur du produit
 */
export interface ProductVendorInfo {
  id: string;
  nom: string;
  adresse: string;
  logo?: string;
  localisation?: {
    lat: number;
    lng: number;
    addr_md5: string;
  };
  annee_creation?: string;
  temps_reponse?: string;
  short_description?: string;
  affichage_complet?: boolean;
  fiche?: string;
  annee_hellopro?: number;
  desc_cutted?: number;
  neuf_occasion_location?: string;
  garantie?: string;
  etat_societe?: string;
  id_type_societe_contrat?: string;
  domaine: string;
}

/**
 * Item produit complet avec produit, catégorie et vendeur
 */
export interface ProductInfoItem {
  produit: ProductInfoData;
  categorie: ProductCategoryInfo;
  vendeur: ProductVendorInfo;
}

/**
 * Réponse de l'API get_info_produit
 */
export interface ProductInfoResponse {
  items: Record<string, ProductInfoItem>;
}
