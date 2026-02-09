"use client";

import { useState, useMemo, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useFlowStore } from '@/lib/stores/flow-store';
import { basePath } from '@/lib/utils';
import type { CharacteristicDefinition, CharacteristicsMap } from '@/types/characteristics';

// Toujours utiliser le proxy Next.js pour éviter les problèmes CORS
const getApiBasePath = () => {
  return basePath || '';
};

/**
 * Prefetch les caractéristiques en background (non-bloquant)
 * Appelé dès que l'API Qn répond pour avoir les données prêtes
 */
async function prefetchCharacteristics(
  categoryId: number,
  setCharacteristicsMap: (map: CharacteristicsMap) => void
): Promise<void> {
  try {
    const apiBase = getApiBasePath();
    const formData = new FormData();
    formData.append('id_categorie', categoryId.toString());

    const response = await fetch(`${apiBase}/api/caracteristiques`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) return;

    const data = await response.json();
    const characteristicsArray: CharacteristicDefinition[] = data.response || [];
    const characteristicsMap: CharacteristicsMap = {};

    for (const char of characteristicsArray) {
      // L'API retourne id_caracteristique, pas id
      const charId = Number((char as any).id_caracteristique || char.id);

      if (isNaN(charId)) {
        console.warn('Invalid characteristic ID:', char);
        continue;
      }

      characteristicsMap[charId] = {
        ...char,
        id: charId,
        nom: char.nom,
        unite: char.unite,
        type: char.type,
        valeurs: char.valeurs.map((v: any) => ({
          // L'API retourne id_valeur, pas id
          id: Number(v.id_valeur || v.id),
          valeur: v.valeur,
        })),
      };
    }

    setCharacteristicsMap(characteristicsMap);
  } catch (error) {
    console.error('Prefetch characteristics error:', error);
  }
}


// =============================================================================
// TYPES - Format API
// =============================================================================

// Format brut de l'API
interface ApiQuestion {
  id_question: number;
  intitule: string;
  choix: string;              // "1" = multi, "2" = single
  justification: string | null;
  id_reponse_parent: number | null;
  id_question_parent: number | null;
  reponses: ApiAnswer[];
}

interface ApiAnswer {
  id_reponse: string | number;
  reponse: string;
  equivalence?: any[];    // Format à définir plus tard
}

// Format normalisé pour le frontend
interface NormalizedQuestion {
  id: number;
  code: string;
  title: string;
  type: 'single' | 'multi';
  justification: string | null;
  answers: NormalizedAnswer[];
}

interface NormalizedAnswer {
  id: string;
  code: string;
  mainText: string;
  equivalence?: any[]; // Ajoutez ceci si absent
}

// =============================================================================
// TRANSFORMERS - Convertir format API → format frontend
// =============================================================================

/**
 * Transforme une question de l'API vers le format frontend
 */
function normalizeQuestion(apiQuestion: ApiQuestion, questionIndex: number): NormalizedQuestion {
  return {
    id: apiQuestion.id_question,
    code: `Q${questionIndex + 1}`,
    title: apiQuestion.intitule,
    type: apiQuestion.choix === '1' ? 'multi' : 'single',  // "1" = multi, "2" = single
    justification: apiQuestion.justification,
    answers: apiQuestion.reponses.map((r) => ({      
      id: String(r.id_reponse),
      code: String(r.id_reponse),
      mainText: r.reponse,
      equivalence: r.equivalence,
    })),
  };
}

// =============================================================================
// HOOK
// =============================================================================

export function useDynamicQuestionnaire(rubriqueId: string) {
  const {
    dynamicAnswers,
    setDynamicAnswer,
    resetDynamicAnswers,
    categoryId,
    characteristicsMap,
    setCharacteristicsMap,
  } = useFlowStore();

  // Restaurer l'index à partir des réponses déjà enregistrées dans le store.
  // Si l'utilisateur revient (ex: retour depuis /profile), on affiche la dernière
  // question répondue au lieu de repartir à Q1.
  const [currentIndex, setCurrentIndex] = useState(() => {
    const answeredCount = Object.keys(dynamicAnswers).length;
    return answeredCount > 0 ? answeredCount - 1 : 0;
  });

  // Appel A : Charger Q1
  const {
    data: entryData,
    isLoading: isLoadingEntry,
    error: entryError
  } = useQuery({
    queryKey: ['questionnaire', 'q1', rubriqueId],
    queryFn: async () => {

      const formData = new FormData();
      formData.append('rubriqueId', rubriqueId);

      const apiBase = getApiBasePath();
      const apiUrl = `${apiBase}/api/questionnaire/q1`;
      
      const res = await fetch(apiUrl, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) throw new Error('Failed to fetch Q1');

      let apiData = await res.json();
      apiData = apiData.response;

      console.log("apiData RAW", apiData);
      
      const apiDataAPI : ApiQuestion = apiData;

      console.log("apiData", apiDataAPI);

      const dataReturn = {
        entryQuestion: normalizeQuestion(apiDataAPI, 0),
      };

      console.log("dataReturn waaaaaa", dataReturn);

      // Transformer vers le format frontend
      return dataReturn;
    },
    enabled: !!rubriqueId,
  });

  // Réponse Q1 de l'utilisateur (utilise le code de la réponse = id)
  const q1AnswerCode = dynamicAnswers?.['Q1']?.[0];

  // Appel B : Charger le parcours (seulement après réponse Q1)
  const {
    data: pathData,
    isLoading: isLoadingPath,
    error: pathError
  } = useQuery({
    queryKey: ['questionnaire', 'qn', rubriqueId, q1AnswerCode],
    queryFn: async () => {
      const formData = new FormData();
      formData.append('rubriqueId', rubriqueId);
      formData.append('q1Answer', q1AnswerCode);

      const apiBase = getApiBasePath();
      const apiUrl = `${apiBase}/api/questionnaire/qn`;
      
      const res = await fetch(apiUrl, {
        method: 'POST',
        body: formData,
      });
      
      if (!res.ok) throw new Error('Failed to fetch path questions');
      let apiData = await res.json();
      apiData = apiData.response;
      // L'API retourne un tableau imbriqué [[...questions]], on aplatit
      const apiDataAPI: ApiQuestion[] = Array.isArray(apiData?.[0]) ? apiData.flat() : apiData;

      // Transformer chaque question du parcours (Q2 à Qn)
      // L'index commence à 1 car Q1 est déjà passée
      const questions = apiDataAPI.map((q, index) => normalizeQuestion(q, index + 1));

      return {
        questions,
        totalQuestions: apiDataAPI.length,
      };
    },
    enabled: !!q1AnswerCode && !!rubriqueId,
  });

  // Prefetch des caractéristiques dès que pathData est reçu (en background)
  const hasCharacteristics = Object.keys(characteristicsMap).length > 0;
  useEffect(() => {
    if (pathData && categoryId && !hasCharacteristics) {
      // Lancer en background sans bloquer
      prefetchCharacteristics(categoryId, setCharacteristicsMap);
    }
  }, [pathData, categoryId, hasCharacteristics, setCharacteristicsMap]);

  // Question courante
  const currentQuestion = useMemo(() => {
    if (currentIndex === 0) {
      return entryData?.entryQuestion || null;
    }
    if (!pathData?.questions) return null;
    return pathData.questions[currentIndex - 1] || null;
  }, [entryData, pathData, currentIndex]);

  // Progression
  const progress = useMemo(() => {
    if (!pathData || currentIndex === 0) {
      return { current: 1, total: 1, percent: 0 };
    }
    const total = 1 + (pathData.totalQuestions || pathData.questions?.length || 0);
    const current = currentIndex + 1;
    return { current, total, percent: Math.round((current / total) * 100) };
  }, [pathData, currentIndex]);

  // Soumettre réponse
  const submitAnswer = (answerCodes: string[]) => {
    if (!currentQuestion) return;
    const questionCode = currentQuestion.code || `Q${currentIndex + 1}`;

    // Trouver les réponses sélectionnées
    const matchedAnswers = currentQuestion.answers
      .filter((a) => answerCodes.includes(a.code));

    // Extraire les équivalences de manière robuste
    const selectedEquivalences = matchedAnswers
      .flatMap((a) => Array.isArray(a.equivalence) ? a.equivalence : []);

    setDynamicAnswer(questionCode, answerCodes, selectedEquivalences);

    setCurrentIndex((prev) => prev + 1);
  };

  // Retour arrière
  const goBack = () => {
    if (currentIndex > 0) {
      setCurrentIndex(prev => prev - 1);
    }
  };

  // Fin du questionnaire
  const isComplete = useMemo(() => {
    if (!pathData || currentIndex === 0) return false;
    const totalInPath = pathData.totalQuestions || pathData.questions?.length || 0;
    return currentIndex > totalInPath;
  }, [pathData, currentIndex]);

  // Reset
  const reset = () => {
    resetDynamicAnswers();
    setCurrentIndex(0);
  };

  return {
    // État
    currentQuestion,
    currentIndex,
    isLoading: isLoadingEntry || (!!q1AnswerCode && isLoadingPath),
    error: entryError || pathError,

    // Progression
    progress,

    // Parcours (à implémenter si l'API retourne ces infos)
    // pathId: null,
    // pathName: null,

    // Actions
    submitAnswer,
    goBack,
    reset,

    // Flags
    canGoBack: currentIndex > 0,
    isComplete,
    isEntryQuestion: currentIndex === 0,
  };
}
