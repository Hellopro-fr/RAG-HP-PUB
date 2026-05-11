// Catalogue statique des contenus du panneau "Comment bien répondre / Pourquoi cette question"
// affiché à droite des écrans question (desktop) ou en carte sous les réponses (mobile).
//
// Résolution dans cet ordre (cf. getQuestionExplanation) :
//   1. bulle_aide API (format dynamique) si non-malformé — voir fromBulleAide pour les conditions
//   2. QUESTION_EXPLANATIONS_BY_ID[questionId] — id_question retourné par l'API HelloPro
//   3. QUESTION_EXPLANATIONS_BY_CODE[questionCode] — code séquentiel "Q1", "Q2"...
//   4. apiJustification (chaîne libre renvoyée par l'API, legacy) → panneau générique
//   5. null → panneau masqué, retour mise en page mono-colonne
//
// Données statiques tirées de la maquette Lovable (project a108e9d5-86fe-4550-adcf-91d9c2f1af18).
// L'API HelloPro renvoie désormais un champ structuré `bulle_aide` qui prime sur le catalogue
// statique. Ce dernier reste comme fallback pour les questions non encore migrées côté API.

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

const p = (...segments: ExplanationSegment[]): ExplanationParagraph => ({ segments });
const t = (text: string): ExplanationSegment => ({ text });
const e = (text: string): ExplanationSegment => ({ text, emphasis: true });

export const QUESTION_EXPLANATIONS_BY_CODE: Record<string, QuestionExplanation> = {
  Q1: {
    title: "COMMENT BIEN RÉPONDRE ?",
    paragraphs: [
      p(
        t("Pensez aux véhicules que vous traitez "),
        e("le plus souvent"),
        t(", pas aux cas exceptionnels."),
      ),
      p(
        t("Vous pouvez sélectionner "),
        e("plusieurs catégories"),
        t(" si votre activité est variée — nous adapterons la capacité de levage et la longueur des bras."),
      ),
    ],
    tip: "Astuce : un pont sous-dimensionné s'use prématurément. Mieux vaut prévoir un peu plus large.",
  },
  Q2: {
    title: "POURQUOI CETTE QUESTION ?",
    paragraphs: [
      p(
        t("La hauteur sous plafond détermine si vous pouvez installer un pont "),
        e("sans embase"),
        t(" (arche en haut, sol dégagé) ou s'il faut un pont "),
        e("à embase"),
        t(" (traverse au sol)."),
      ),
      p(
        t("Mesurez la hauteur disponible "),
        e("au point le plus bas"),
        t(" (poutres, gaines, luminaires)."),
      ),
    ],
    tip: "En cas de doute, choisissez « Je ne suis pas sûr » — un technicien pourra valider sur place.",
  },
  Q3: {
    title: "HYDRAULIQUE OU ÉLECTROMÉCANIQUE ?",
    paragraphs: [
      p(
        e("Hydraulique"),
        t(" : montée/descente rapide, peu d'entretien, idéal pour les interventions courtes (pneus, freinage)."),
      ),
      p(
        e("Électromécanique à vis"),
        t(" : précision millimétrique, plus robuste sur le long terme, parfait pour la mécanique de précision."),
      ),
    ],
    tip: "Si vous hésitez, l'hydraulique offre le meilleur rapport coût/performance pour la majorité des ateliers.",
  },
  Q4: {
    title: "À QUOI SERT CETTE QUESTION ?",
    paragraphs: [
      p(
        t("Elle nous permet de cibler la "),
        e("gamme de prix"),
        t(" qui correspond à vos attentes, sans vous demander directement votre budget."),
      ),
      p(
        t("Pensez à la "),
        e("durée de vie attendue"),
        t(" et à l'usage quotidien : un usage intensif justifie un matériel premium."),
      ),
    ],
    tip: "Un pont premium peut durer 15 ans+ contre 7-8 ans pour une entrée de gamme.",
  },
  Q5: {
    title: "COMMENT VÉRIFIER ?",
    paragraphs: [
      p(
        t("Regardez votre "),
        e("tableau électrique"),
        t(" ou une prise existante : 3 phases + neutre = triphasé, 1 phase + neutre = monophasé."),
      ),
      p(
        t("Le "),
        e("triphasé"),
        t(" est le standard pour les ponts professionnels (moteurs plus puissants et durables)."),
      ),
    ],
    tip: "Si vous prévoyez une installation neuve, demandez systématiquement du triphasé 400V.",
  },
  Q6: {
    title: "POURQUOI C'EST CRUCIAL ?",
    paragraphs: [
      p(
        t("La sécurité d'un pont 2 colonnes repose "),
        e("entièrement sur l'ancrage au sol"),
        t(". Une dalle insuffisante peut entraîner un basculement."),
      ),
      p(
        t("Une dalle industrielle standard fait au moins "),
        e("20 cm d'épaisseur"),
        t(" en béton C20/25."),
      ),
    ],
    tip: "Si vous ne savez pas, choisissez « Inconnu » — nous prévoirons une vérification technique.",
  },
  Q7: {
    title: "POURQUOI VOUS DEMANDER ÇA ?",
    paragraphs: [
      p(
        t("Cela nous permet d'"),
        e("adapter notre accompagnement"),
        t(" : devis détaillé immédiat, comparatif multi-fournisseurs ou simple estimation."),
      ),
      p(
        t("Pour un projet en construction, nous joignons les "),
        e("plans de génie civil"),
        t(" nécessaires aux maçons."),
      ),
    ],
    tip: "Tous les projets sont traités, qu'ils soient immédiats ou à long terme.",
  },
};

// Indexation par id_question API. Vide pour l'instant — sera peuplé au fil de l'eau
// si certaines questions divergent entre catégories et nécessitent un mapping précis.
export const QUESTION_EXPLANATIONS_BY_ID: Record<number, QuestionExplanation> = {};

const GENERIC_FALLBACK_TITLE = "POURQUOI CETTE QUESTION ?";

/**
 * Convertit une chaîne contenant des marqueurs `*texte*` en segments alternés
 * (texte normal / texte en gras). Le marqueur retenu est l'astérisque utilisé
 * par l'API HelloPro pour `bulle_aide.explication` et `bulle_aide.astuce`.
 *
 * Exporté pour être réutilisé côté composant lors du rendu de `tip`
 * (le catalogue statique stocke des strings simples, mais l'API peut renvoyer
 * des astérisques que le panneau doit gérer uniformément).
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
 * l'appelant doit tomber sur le fallback suivant. Aucun panneau vide n'est
 * jamais rendu.
 */
function fromBulleAide(bulleAide: BulleAide | null | undefined): QuestionExplanation | null {
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

export function getQuestionExplanation(
  questionId: number | undefined,
  questionCode: string,
  bulleAide?: BulleAide | null,
  apiJustification?: string,
): QuestionExplanation | null {
  const fromApi = fromBulleAide(bulleAide);
  if (fromApi) return fromApi;

  if (typeof questionId === "number" && QUESTION_EXPLANATIONS_BY_ID[questionId]) {
    return QUESTION_EXPLANATIONS_BY_ID[questionId];
  }
  if (QUESTION_EXPLANATIONS_BY_CODE[questionCode]) {
    return QUESTION_EXPLANATIONS_BY_CODE[questionCode];
  }
  const trimmed = apiJustification?.trim();
  if (trimmed) {
    return {
      title: GENERIC_FALLBACK_TITLE,
      paragraphs: [p(t(trimmed))],
    };
  }
  return null;
}
