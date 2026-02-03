/**
 * Types pour l'API caractéristiques
 * Utilisé pour le mapping ID -> labels dans :
 * - ModifyCriteriaForm
 * - CriteriaTags (page résultats)
 * - Modal produits
 * - Cartouches produits (page sélection)
 * - Tableau de comparaison
 */

export interface CharacteristicValue {
  id: number;
  valeur: string;
}

export interface CharacteristicDefinition {
  id: number;
  nom: string;
  unite: string | null;
  type: 'Textuelle' | 'Numérique';
  valeurs: CharacteristicValue[];
}

export interface CharacteristicsApiResponse {
  code: number;
  response: CharacteristicDefinition[];
}

/**
 * Map des caractéristiques indexée par ID pour accès O(1)
 */
export type CharacteristicsMap = Record<number, CharacteristicDefinition>;
