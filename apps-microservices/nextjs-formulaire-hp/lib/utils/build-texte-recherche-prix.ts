/**
 * Construit le texte de recherche pour l'API d'estimation de prix.
 * Port TypeScript de la fonction buildTexteRecherchePrix du formulaire-hp PHP (index.php:747-769).
 *
 * Pour chaque caractéristique consolidée :
 * - Textuelle : "Nom caractéristique : val1, val2"
 * - Numérique : "Nom caractéristique : ≥ min & ≤ max unité" ou "Nom : exact unité"
 */

import type { ConsolidatedCharacteristic } from '@/lib/utils/equivalence-merger';
import type { CharacteristicsMap } from '@/types/characteristics';

export function buildTexteRecherchePrix(
  payload: ConsolidatedCharacteristic[],
  characteristicsMap: CharacteristicsMap
): string {
  if (!Array.isArray(payload) || payload.length === 0) return '';

  return payload
    .map((item) => {
      const caracInfo = characteristicsMap[item.id_caracteristique];
      const nom = caracInfo?.nom || `#${item.id_caracteristique}`;

      if (item.type_caracteristique === 'textuelle' && Array.isArray(item.valeurs_cibles)) {
        const vals = (item.valeurs_cibles as number[]).map((valId) => {
          const found = caracInfo?.valeurs?.find((v) => v.id === valId);
          return found ? found.valeur : `#${valId}`;
        });
        return vals.length > 0 ? `${nom} : ${vals.join(', ')}` : null;
      }

      if (
        item.valeurs_cibles &&
        typeof item.valeurs_cibles === 'object' &&
        !Array.isArray(item.valeurs_cibles)
      ) {
        const numVals = item.valeurs_cibles as { exact?: number; min?: number; max?: number };
        const u = item.unite ? ` ${item.unite}` : '';
        const parts: string[] = [];
        if (numVals.exact !== undefined) parts.push(`${numVals.exact}${u}`);
        if (numVals.min !== undefined) parts.push(`\u2265 ${numVals.min}${u}`);
        if (numVals.max !== undefined) parts.push(`\u2264 ${numVals.max}${u}`);
        return parts.length > 0 ? `${nom} : ${parts.join(' & ')}` : null;
      }

      return null;
    })
    .filter(Boolean)
    .join('\n');
}
