import type { UserQuestionAnswer } from '@/lib/stores/flow-store';

// Réponses non-informatives à exclure des résumés et payloads (case-insensitive).
// Match si la valeur COMMENCE par l'une de ces formules
// (ex. "Je ne sais pas encore", "Je ne sais pas / Souhaite être conseillé", "Autre besoin", "Autres options").
export const NON_INFORMATIVE_VALUE_RE = /^\s*(autres?\b|je ne sais pas\b|souhaite (être|etre) conseill)/i;

/**
 * Renvoie true si la valeur est non-vide ET pas une formule "non-informative"
 * (Autre / Je ne sais pas / Souhaite être conseillé).
 */
export function isMeaningfulValue(v: string | null | undefined): boolean {
  if (!v) return false;
  return !NON_INFORMATIVE_VALUE_RE.test(v);
}

/**
 * Aplatit les `answerLabel` des `userQuestionAnswers` en liste de chips affichables,
 * en filtrant les réponses non-informatives.
 */
export function extractChipsFromAnswers(answers: UserQuestionAnswer[]): string[] {
  return answers
    .flatMap((a) =>
      Array.isArray(a.answerLabel)
        ? a.answerLabel
        : a.answerLabel
          ? [a.answerLabel]
          : []
    )
    .filter(isMeaningfulValue);
}
