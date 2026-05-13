// Source unique du panneau "Comment bien répondre / Pourquoi cette question" :
// le champ `bulle_aide` retourné par l'API HelloPro (libelle / explication / astuce).
//
// Si `bulle_aide` est absent ou malformé, `getQuestionExplanation` retourne `null`
// et le panneau est simplement masqué côté `QuestionScreen` (layout mono-colonne).
// Aucun fallback statique n'est rendu — voir discussion d'intégration : un contenu
// hardcodé risquerait d'être incohérent avec la question réellement servie par l'API.

import type { BulleAide } from "@/types";

export interface ExplanationSegment {
  text: string;
  emphasis?: boolean;
}

export interface ExplanationParagraph {
  segments: ExplanationSegment[];
}

export interface QuestionExplanation {
  title: string;
  paragraphs: ExplanationParagraph[];
  tip?: string;
}

/**
 * Convertit une chaîne contenant des marqueurs `*texte*` en segments alternés
 * (texte normal / texte en gras). Le marqueur retenu est l'astérisque utilisé
 * par l'API HelloPro pour `bulle_aide.explication` et `bulle_aide.astuce`.
 *
 * Exporté pour être réutilisé côté composant lors du rendu de `tip`.
 */
export function parseEmphasisSegments(text: string): ExplanationSegment[] {
  const segments: ExplanationSegment[] = [];
  const regex = /\*([^*]+)\*/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ text: text.slice(lastIndex, match.index) });
    }
    segments.push({ text: match[1], emphasis: true });
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) {
    segments.push({ text: text.slice(lastIndex) });
  }
  return segments.length > 0 ? segments : [{ text }];
}

/**
 * Construit une `QuestionExplanation` depuis le champ `bulle_aide` de l'API.
 * Retourne `null` si la donnée est absente, malformée ou vide — auquel cas
 * le panneau n'est pas rendu.
 */
export function getQuestionExplanation(
  bulleAide?: BulleAide | null,
): QuestionExplanation | null {
  if (!bulleAide) return null;
  const title = typeof bulleAide.libelle === "string" ? bulleAide.libelle.trim() : "";
  if (!title) return null;

  const rawExplications = Array.isArray(bulleAide.explication) ? bulleAide.explication : [];
  const paragraphs: ExplanationParagraph[] = rawExplications
    .filter((entry): entry is string => typeof entry === "string" && entry.trim().length > 0)
    .map((entry) => ({ segments: parseEmphasisSegments(entry.trim()) }));

  if (paragraphs.length === 0) return null;

  const rawAstuce = typeof bulleAide.astuce === "string" ? bulleAide.astuce.trim() : "";

  return {
    title,
    paragraphs,
    tip: rawAstuce || undefined,
  };
}
