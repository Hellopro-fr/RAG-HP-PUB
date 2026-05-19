import type { UserQuestionAnswer } from '@/lib/stores/flow-store';

// Réponses non-informatives à exclure des résumés (case-insensitive).
// Match si le label COMMENCE par l'une de ces formules
// (ex. "Je ne sais pas / Souhaite être conseillé", "Autre besoin", "Autres options").
const EXCLUDED_CHIP_RE = /^\s*(autres?\b|je ne sais pas\b|souhaite (être|etre) conseill)/i;

/**
 * Aplatit les `answerLabel` des `userQuestionAnswers` en liste de chips affichables,
 * en filtrant les réponses non-informatives (Autre / Je ne sais pas / Souhaite être conseillé).
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
    .filter((label): label is string => Boolean(label) && !EXCLUDED_CHIP_RE.test(label));
}
