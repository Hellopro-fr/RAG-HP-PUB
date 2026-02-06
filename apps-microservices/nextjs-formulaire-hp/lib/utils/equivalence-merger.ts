/**
 * Fusion et consolidation des équivalences de caractéristiques
 *
 * Algorithme :
 * 1. Collecter toutes les équivalences issues des réponses, avec le poids_question
 * 2. Regrouper par id_caracteristique
 * 3. Déterminer le poids final : critique > secondaire, puis poids_question le plus élevé
 * 4. Fusionner les valeurs cibles et bloquantes
 */

// =============================================================================
// TYPES
// =============================================================================

export type PoidsCaracteristique = 'critique' | 'secondaire';
export type TypeCaracteristique = 'textuelle' | 'numerique';

/** Équivalence brute telle que stockée dans dynamicEquivalences (par question) */
export interface RawEquivalence {
  id_caracteristique: number | string;
  type_caracteristique?: TypeCaracteristique;
  poids_caracteristique?: PoidsCaracteristique;
  poids?: PoidsCaracteristique; // L'API peut utiliser 'poids' au lieu de 'poids_caracteristique'
  valeurs_cibles: number[] | string[] | { exact?: number; min?: number; max?: number };
  valeurs_bloquantes: number[] | string[] | { min?: number; max?: number };
  unite?: string; // ex: "kg", "mm" pour les numériques
}

/** Équivalence enrichie avec le poids de la question d'origine */
interface WeightedEquivalence extends RawEquivalence {
  id_caracteristique: number; // Toujours normalisé en number
  type_caracteristique: TypeCaracteristique; // Toujours détecté
  poids_caracteristique: PoidsCaracteristique; // Toujours normalisé
  poids_question: number;
}

/** Caractéristique consolidée après fusion */
export interface ConsolidatedCharacteristic {
  id_caracteristique: number;
  type_caracteristique: TypeCaracteristique;
  poids_question: number;
  poids_caracteristique: PoidsCaracteristique;
  valeurs_cibles: number[] | { exact?: number; min?: number; max?: number };
  valeurs_bloquantes: number[] | { min?: number; max?: number };
  unite?: string;
}

// =============================================================================
// HELPERS
// =============================================================================

/**
 * Détecte si une valeur est un objet numérique (min/max/exact)
 */
function isNumericObject(val: any): val is { exact?: number; min?: number; max?: number } {
  if (val === null || val === undefined) return false;
  if (Array.isArray(val)) return false;
  if (typeof val !== 'object') return false;
  return 'min' in val || 'max' in val || 'exact' in val;
}

/**
 * Détecte le type de caractéristique depuis la structure des données.
 * - Si valeurs_cibles ou valeurs_bloquantes est un objet {min/max/exact} → numerique
 * - Si unite est présent → numerique
 * - Sinon → textuelle
 */
function detectTypeFromData(eq: RawEquivalence): TypeCaracteristique {
  // Si valeurs_cibles est un objet {min/max/exact} → numerique
  if (isNumericObject(eq.valeurs_cibles)) {
    return 'numerique';
  }
  // Si valeurs_bloquantes est un objet {min/max} → numerique
  if (isNumericObject(eq.valeurs_bloquantes)) {
    return 'numerique';
  }
  // Si unite est présent → fort indice pour numerique
  if (eq.unite) {
    return 'numerique';
  }
  // Par défaut, textuelle
  return 'textuelle';
}

// =============================================================================
// FUSION
// =============================================================================

/**
 * Calcule le poids d'une question selon sa position.
 * Q1 (index 0) = N, QN (index N-1) = 1
 */
function getQuestionWeight(questionIndex: number, totalQuestions: number): number {
  return totalQuestions - questionIndex;
}

/**
 * Extrait le code de question "Q1", "Q2"... et retourne l'index 0-based.
 */
function questionCodeToIndex(code: string): number {
  const match = code.match(/^Q(\d+)$/);
  if (!match) return 0;
  return parseInt(match[1], 10) - 1;
}

/**
 * Fusionne les valeurs cibles textuelles (union des IDs)
 * L'API peut retourner des strings ou des numbers, on normalise en numbers
 */
function mergeTextualTargets(equivalences: WeightedEquivalence[]): number[] {
  const allTargets = new Set<number>();
  for (const eq of equivalences) {
    if (Array.isArray(eq.valeurs_cibles)) {
      eq.valeurs_cibles.forEach((v) => allTargets.add(Number(v)));
    }
  }
  return Array.from(allTargets);
}

/**
 * Fusionne les valeurs bloquantes textuelles (union des IDs, en excluant les cibles)
 * L'API peut retourner des strings ou des numbers, on normalise en numbers
 */
function mergeTextualBlocking(equivalences: WeightedEquivalence[], mergedTargets: number[]): number[] {
  const allBlocking = new Set<number>();
  for (const eq of equivalences) {
    if (Array.isArray(eq.valeurs_bloquantes)) {
      eq.valeurs_bloquantes.forEach((v) => allBlocking.add(Number(v)));
    }
  }
  // Retirer les valeurs qui sont aussi des cibles (cible prioritaire)
  return Array.from(allBlocking).filter((v) => !mergedTargets.includes(v));
}

/**
 * Fusionne les valeurs cibles numériques.
 * Si plusieurs intervalles, on prend l'union (min des min, max des max).
 * Si exact + intervalle, l'exact est converti en intervalle.
 */
function mergeNumericTargets(
  equivalences: WeightedEquivalence[]
): { exact?: number; min?: number; max?: number } {
  const intervals: { min: number; max: number }[] = [];

  for (const eq of equivalences) {
    const val = eq.valeurs_cibles;
    if (isNumericObject(val)) {
      if (val.exact !== undefined) {
        intervals.push({ min: val.exact, max: val.exact });
      } else if (val.min !== undefined || val.max !== undefined) {
        intervals.push({
          min: val.min ?? -Infinity,
          max: val.max ?? Infinity,
        });
      }
    }
  }

  if (intervals.length === 0) return {};
  if (intervals.length === 1) {
    const iv = intervals[0];
    if (iv.min === iv.max) return { exact: iv.min };
    return {
      min: iv.min === -Infinity ? undefined : iv.min,
      max: iv.max === Infinity ? undefined : iv.max,
    };
  }

  // Union : min des min, max des max
  const globalMin = Math.min(...intervals.map((i) => i.min));
  const globalMax = Math.max(...intervals.map((i) => i.max));

  return {
    min: globalMin === -Infinity ? undefined : globalMin,
    max: globalMax === Infinity ? undefined : globalMax,
  };
}

/**
 * Fusionne les valeurs bloquantes numériques.
 * Même logique que pour les cibles : union des intervalles.
 */
function mergeNumericBlocking(
  equivalences: WeightedEquivalence[]
): { min?: number; max?: number } {
  const intervals: { min: number; max: number }[] = [];

  for (const eq of equivalences) {
    const val = eq.valeurs_bloquantes;
    if (isNumericObject(val)) {
      if (val.min !== undefined || val.max !== undefined) {
        intervals.push({
          min: val.min ?? -Infinity,
          max: val.max ?? Infinity,
        });
      }
    }
  }

  if (intervals.length === 0) return {};
  if (intervals.length === 1) {
    const iv = intervals[0];
    return {
      min: iv.min === -Infinity ? undefined : iv.min,
      max: iv.max === Infinity ? undefined : iv.max,
    };
  }

  // Union : min des min, max des max
  const globalMin = Math.min(...intervals.map((i) => i.min));
  const globalMax = Math.max(...intervals.map((i) => i.max));

  return {
    min: globalMin === -Infinity ? undefined : globalMin,
    max: globalMax === Infinity ? undefined : globalMax,
  };
}

/**
 * Consolide toutes les équivalences issues du questionnaire dynamique.
 *
 * @param dynamicEquivalences - Record<questionCode, RawEquivalence[]> du store
 * @returns Liste consolidée de caractéristiques avec poids final
 */
export function consolidateEquivalences(
  dynamicEquivalences: Record<string, RawEquivalence[]>
): ConsolidatedCharacteristic[] {
  const questionCodes = Object.keys(dynamicEquivalences);
  const totalQuestions = questionCodes.length;

  if (totalQuestions === 0) return [];

  // Étape 1 : Collecter toutes les équivalences avec poids_question
  const allWeighted: WeightedEquivalence[] = [];

  for (const code of questionCodes) {
    const questionIndex = questionCodeToIndex(code);
    const poidsQuestion = getQuestionWeight(questionIndex, totalQuestions);
    const equivalences = dynamicEquivalences[code] || [];

    for (const eq of equivalences) {
      // Normaliser poids_caracteristique en minuscule
      // L'API peut retourner 'poids' ou 'poids_caracteristique', et 'Critique'/'Secondaire'
      const rawPoids = (eq as any).poids || eq.poids_caracteristique;
      const normalizedPoids = (rawPoids?.toLowerCase() || 'secondaire') as PoidsCaracteristique;

      // Détecter le type depuis la structure des données (pas de champ type dans l'API)
      // Si valeurs_cibles est {min/max/exact} ou si unite est présent → numerique
      const detectedType = detectTypeFromData(eq);

      allWeighted.push({
        ...eq,
        id_caracteristique: Number(eq.id_caracteristique),
        poids_caracteristique: normalizedPoids,
        type_caracteristique: detectedType,
        poids_question: poidsQuestion,
      });
    }
  }

  // Étape 2 : Regrouper par id_caracteristique
  const grouped: Record<number, WeightedEquivalence[]> = {};

  for (const eq of allWeighted) {
    const id = eq.id_caracteristique;
    if (!grouped[id]) {
      grouped[id] = [];
    }
    grouped[id].push(eq);
  }

  // Étape 3 & 4 : Pour chaque caractéristique, déterminer poids final et fusionner valeurs
  const result: ConsolidatedCharacteristic[] = [];

  for (const [idStr, equivalences] of Object.entries(grouped)) {
    const id = Number(idStr);
    const critiques = equivalences.filter((eq) => eq.poids_caracteristique === 'critique');
    const secondaires = equivalences.filter((eq) => eq.poids_caracteristique === 'secondaire');

    // Déterminer le niveau de priorité et le poids_question
    let poidsCaracteristique: PoidsCaracteristique;
    let poidsQuestion: number;

    if (critiques.length > 0) {
      // Cas 1 : au moins une occurrence critique → critique gagne
      poidsCaracteristique = 'critique';
      poidsQuestion = Math.max(...critiques.map((eq) => eq.poids_question));
    } else {
      // Cas 2 : que des secondaires
      poidsCaracteristique = 'secondaire';
      poidsQuestion = Math.max(...secondaires.map((eq) => eq.poids_question));
    }

    // Récupérer le type et l'unité depuis la première occurrence
    const first = equivalences[0];
    const type = first.type_caracteristique || 'textuelle'; // Toujours défini car détecté en amont
    const unite = first.unite;

    // Fusionner les valeurs (toutes les occurrences, pas seulement la gagnante)
    let valeursCibles: number[] | { exact?: number; min?: number; max?: number };
    let valeursBloquantes: number[] | { min?: number; max?: number };

    if (type === 'textuelle') {
      const mergedTargets = mergeTextualTargets(equivalences);
      valeursCibles = mergedTargets;
      valeursBloquantes = mergeTextualBlocking(equivalences, mergedTargets);
    } else {
      // numérique
      valeursCibles = mergeNumericTargets(equivalences);
      valeursBloquantes = mergeNumericBlocking(equivalences);
    }

    const consolidated: ConsolidatedCharacteristic = {
      id_caracteristique: id,
      type_caracteristique: type,
      poids_question: poidsQuestion,
      poids_caracteristique: poidsCaracteristique,
      valeurs_cibles: valeursCibles,
      valeurs_bloquantes: valeursBloquantes,
    };

    if (unite) {
      consolidated.unite = unite;
    }

    result.push(consolidated);
  }

  // Trier par priorité : critique d'abord, puis par poids_question décroissant
  result.sort((a, b) => {
    const priorityA = a.poids_caracteristique === 'critique' ? 1 : 0;
    const priorityB = b.poids_caracteristique === 'critique' ? 1 : 0;
    if (priorityB !== priorityA) return priorityB - priorityA;
    return b.poids_question - a.poids_question;
  });

  return result;
}
