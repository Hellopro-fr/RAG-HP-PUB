/**
 * Construit le texte_prompt pour l'API d'estimation de prix (mode prix_version=3).
 * Port TypeScript de la logique PHP formulaire-hp (index.php:1317-1342).
 *
 * Format de sortie :
 *   Quel type de compresseur recherchez-vous ?
 *   Compresseur à vis (Puissance : ≥ 500 kW)
 *   Quelle utilisation ?
 *   Industrielle
 */

import { detectTypeFromData, isNumericObject } from './equivalence-merger';
import type { UserQuestionAnswer } from '@/lib/stores/flow-store';
import type { CharacteristicsMap } from '@/types/characteristics';

export function buildTextePromptPrix(
  userQuestionAnswers: UserQuestionAnswer[],
  characteristicsMap: CharacteristicsMap
): string {
  if (!userQuestionAnswers || userQuestionAnswers.length === 0) return '';

  return userQuestionAnswers
    .map((qa) => {
      const lines: string[] = [];

      // Ligne question
      lines.push(qa.questionLabel || `Question ${qa.questionId}`);

      // Réponses (peut être string ou string[])
      const answerLabels = Array.isArray(qa.answerLabel)
        ? qa.answerLabel
        : qa.answerLabel
          ? [qa.answerLabel]
          : [String(qa.answerId)];

      const equivalences = qa.equivalences || [];

      for (const answerText of answerLabels) {
        // Extraire les équivalences numériques
        const numParts = equivalences
          .filter((eq: any) => detectTypeFromData(eq) === 'numerique')
          .map((eq: any) => {
            const caracInfo = characteristicsMap[Number(eq.id_caracteristique)];
            const nom = caracInfo?.nom || `#${eq.id_caracteristique}`;
            const u = eq.unite ? ` ${eq.unite}` : '';
            const parts: string[] = [];

            if (isNumericObject(eq.valeurs_cibles)) {
              if (eq.valeurs_cibles.exact !== undefined)
                parts.push(`${eq.valeurs_cibles.exact}${u}`);
              if (eq.valeurs_cibles.min !== undefined)
                parts.push(`\u2265 ${eq.valeurs_cibles.min}${u}`);
              if (eq.valeurs_cibles.max !== undefined)
                parts.push(`\u2264 ${eq.valeurs_cibles.max}${u}`);
            }

            return parts.length > 0 ? `${nom} : ${parts.join(' & ')}` : null;
          })
          .filter(Boolean);

        if (numParts.length > 0) {
          lines.push(`${answerText} (${numParts.join(', ')})`);
        } else {
          lines.push(answerText);
        }
      }

      return lines.join('\n');
    })
    .join('\n');
}
