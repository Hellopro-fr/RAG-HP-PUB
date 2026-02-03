import type { CharacteristicsMap } from '@/types/characteristics';

/**
 * Helpers pour accéder aux données des caractéristiques
 * Utilisés dans ModifyCriteriaForm, CriteriaTags, Modal produits, etc.
 */

/**
 * Récupère le label (nom) d'une caractéristique par son ID
 */
export function getCharacteristicLabel(
  map: CharacteristicsMap,
  characteristicId: number
): string {
  return map[characteristicId]?.nom || `Caractéristique #${characteristicId}`;
}

/**
 * Récupère l'unité d'une caractéristique (pour les numériques)
 */
export function getCharacteristicUnit(
  map: CharacteristicsMap,
  characteristicId: number
): string | null {
  return map[characteristicId]?.unite || null;
}

/**
 * Récupère le type d'une caractéristique
 */
export function getCharacteristicType(
  map: CharacteristicsMap,
  characteristicId: number
): 'Textuelle' | 'Numérique' | null {
  return map[characteristicId]?.type || null;
}

/**
 * Récupère le label d'une valeur par son ID
 */
export function getValueLabel(
  map: CharacteristicsMap,
  characteristicId: number,
  valueId: number
): string {
  const characteristic = map[characteristicId];
  if (!characteristic) return `Valeur #${valueId}`;

  const value = characteristic.valeurs.find(v => v.id === valueId);
  return value?.valeur || `Valeur #${valueId}`;
}

/**
 * Récupère les labels de plusieurs valeurs
 */
export function getValueLabels(
  map: CharacteristicsMap,
  characteristicId: number,
  valueIds: number[]
): string[] {
  return valueIds.map(id => getValueLabel(map, characteristicId, id));
}

/**
 * Récupère toutes les options disponibles pour une caractéristique
 * Format adapté pour les select/dropdown
 */
export function getCharacteristicOptions(
  map: CharacteristicsMap,
  characteristicId: number
): { id: number; label: string }[] {
  const characteristic = map[characteristicId];
  if (!characteristic) return [];

  return characteristic.valeurs.map(v => ({
    id: v.id,
    label: v.valeur,
  }));
}

/**
 * Formate une valeur numérique avec son unité
 */
export function formatNumericValue(
  map: CharacteristicsMap,
  characteristicId: number,
  value: number
): string {
  const unit = getCharacteristicUnit(map, characteristicId);
  return unit ? `${value} ${unit}` : `${value}`;
}

/**
 * Formate les valeurs sélectionnées pour affichage
 * Gère les cas textuels et numériques
 */
export function formatSelectedValues(
  map: CharacteristicsMap,
  characteristicId: number,
  valueIds: number[] | { exact?: number; min?: number; max?: number }
): string {
  const characteristic = map[characteristicId];

  // Cas numérique (objet avec min/max/exact)
  if (!Array.isArray(valueIds)) {
    const unit = characteristic?.unite || '';
    if (valueIds.exact !== undefined) {
      return `${valueIds.exact}${unit ? ` ${unit}` : ''}`;
    }
    if (valueIds.min !== undefined && valueIds.max !== undefined) {
      return `${valueIds.min} - ${valueIds.max}${unit ? ` ${unit}` : ''}`;
    }
    if (valueIds.min !== undefined) {
      return `≥ ${valueIds.min}${unit ? ` ${unit}` : ''}`;
    }
    if (valueIds.max !== undefined) {
      return `≤ ${valueIds.max}${unit ? ` ${unit}` : ''}`;
    }
    return '';
  }

  // Cas textuel (tableau d'IDs)
  const labels = getValueLabels(map, characteristicId, valueIds);
  return labels.join(', ');
}
