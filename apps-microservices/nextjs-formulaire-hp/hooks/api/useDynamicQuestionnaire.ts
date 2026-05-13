"use client";

import { useState, useMemo, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useFlowStore } from '@/lib/stores/flow-store';
import { basePath } from '@/lib/utils';
import type { CharacteristicDefinition, CharacteristicsMap } from '@/types/characteristics';
import type { BulleAide } from '@/types';
import { useDbTracking } from '@/hooks/tracking/useDbTracking';

// Toujours utiliser le proxy Next.js pour éviter les problèmes CORS
const getApiBasePath = () => {
  return basePath || '';
};

/**
 * Prefetch les caractéristiques en background (non-bloquant)
 * Appelé dès que l'API Qn répond pour avoir les données prêtes
 */
/**
 * Prefetch les statistiques de catégorie (nb produits, nb fournisseurs)
 * Appelé dès le chargement de Q1 pour avoir les données prêtes
 */
/**
 * Prefetch la vignette de la catégorie (non-bloquant)
 * Appelé dès le chargement de Q1 pour avoir l'image prête
 */
async function prefetchCategoryVignette(
  categoryId: number,
  setCategoryVignette: (url: string | null) => void
): Promise<void> {
  try {
    const apiBase = getApiBasePath();
    const response = await fetch(`${apiBase}/api/vignette-categorie/${categoryId}`, {
      method: 'GET',
    });

    if (!response.ok) return;

    const data = await response.json();
    // API retourne: {"id_categorie":"2007702","vignette":"images/vignette_rubrique/s/...","vignette_large":"...","source_produit":"1"}
    if (data.vignette) {
      setCategoryVignette(`https://www.hellopro.fr/${data.vignette}`);
    }
  } catch (error) {
    console.error('Prefetch category vignette error:', error);
    // En cas d'erreur, on garde null (fallback sur image placeholder)
  }
}

async function prefetchCategoryStats(
  categoryId: number,
  setCategoryStats: (stats: { productsCount: number; suppliersCount: number } | null) => void
): Promise<void> {
  try {
    const apiBase = getApiBasePath();
    const response = await fetch(`${apiBase}/api/info-categorie/${categoryId}`, {
      method: 'GET',
    });

    if (!response.ok) return;

    const data = await response.json();
    // API retourne: {"id_categorie":"2007702","fournisseur":33,"produit":748}
    if (data.produit !== undefined && data.fournisseur !== undefined) {
      const productsCount = Number(data.produit);
      const suppliersCount = Number(data.fournisseur);
      setCategoryStats({ productsCount, suppliersCount });
    }
  } catch (error) {
    console.error('Prefetch category stats error:', error);
    // En cas d'erreur, on garde null (fallback sur valeurs statiques)
  }
}

/**
 * Prefetch les caractéristiques prix en background (non-bloquant)
 * Appelé dès le chargement de Q1 pour avoir les données prêtes pour l'estimation de prix
 */
async function prefetchCaracteristiquesPrix(
  categoryId: number,
  setCaracteristiquesPrix: (data: any[]) => void
): Promise<void> {
  try {
    const apiBase = getApiBasePath();
    const formData = new FormData();
    formData.append('id_categorie', categoryId.toString());

    const response = await fetch(`${apiBase}/api/caracteristiques-prix`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) return;

    const data = await response.json();
    // L'API retourne un objet avec un champ response contenant les réponses Q1 avec leurs caracteristiques_prix
    const reponses = data.response || data;
    if (Array.isArray(reponses)) {
      setCaracteristiquesPrix(reponses);
    }
  } catch (error) {
    console.error('Prefetch caracteristiques prix error:', error);
  }
}

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
  bulle_aide?: BulleAide | null;
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
  bulleAide: BulleAide | null;
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
    bulleAide: apiQuestion.bulle_aide ?? null,
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
    addUserQuestionAnswer,
    updateUserQuestionAnswer,
    userQuestionAnswers,
    setCategoryName,
    setCategoryStats,
    setCategoryVignette,
    setCaracteristiquesPrix,
    truncateAnswersAfterIndex,
  } = useFlowStore();

  const { trackDbEvent } = useDbTracking();

  // Prefetch vignette dès que rubriqueId est disponible (en parallèle de Q1, pas après)
  useEffect(() => {
    if (rubriqueId) {
      prefetchCategoryVignette(Number(rubriqueId), setCategoryVignette);
    }
  }, [rubriqueId, setCategoryVignette]);

  // Restaurer l'index à partir des réponses déjà enregistrées dans le store.
  // Si l'utilisateur revient (ex: retour depuis /profile), on affiche la question suivante.
  // Si Q1 est pré-remplie via l'URL, on démarre directement à Q2.
  const [currentIndex, setCurrentIndex] = useState(() => {
    const answeredCount = Object.keys(dynamicAnswers).length;
    // answeredCount = nombre de questions déjà répondues
    // On veut afficher la question suivante (index = answeredCount)
    return answeredCount;
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
      const nom_categorie = apiData.nom_categorie || null;
      apiData = apiData.response;

      if (nom_categorie) {
        setCategoryName(nom_categorie);
      }

      // Prefetch category stats (non-bloquant)
      if (rubriqueId) {
        prefetchCategoryStats(Number(rubriqueId), setCategoryStats);
        prefetchCaracteristiquesPrix(Number(rubriqueId), setCaracteristiquesPrix);
      }

      const apiDataAPI : ApiQuestion = apiData;

      const dataReturn = {
        entryQuestion: normalizeQuestion(apiDataAPI, 0),
      };

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
      const nom_categorie = apiData.nom_categorie || null;
      apiData = apiData.response;

      if (nom_categorie) {
        setCategoryName(nom_categorie);
      }
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

  // Mettre à jour Q1 pré-remplie avec les vrais labels une fois les données chargées
  useEffect(() => {
    if (!entryData?.entryQuestion) return;

    // Vérifier si Q1 est pré-remplie (existe dans dynamicAnswers)
    const q1Answers = dynamicAnswers['Q1'];
    if (!q1Answers || q1Answers.length === 0) return;

    // Vérifier si Q1 existe déjà dans userQuestionAnswers avec un label placeholder
    const existingQ1 = userQuestionAnswers.find(qa => qa.questionCode === 'Q1');
    if (!existingQ1 || !existingQ1.questionLabel?.includes('pre-remplie')) return;

    // Récupérer les vrais labels des réponses sélectionnées
    const selectedAnswers = entryData.entryQuestion.answers.filter(
      a => q1Answers.includes(a.code)
    );
    const answerLabels = selectedAnswers.map(a => a.mainText);

    // Mettre à jour avec les vraies informations
    updateUserQuestionAnswer('Q1', {
      questionId: entryData.entryQuestion.id,
      questionLabel: entryData.entryQuestion.title,
      answerLabel: answerLabels,
    });

    console.log('[useDynamicQuestionnaire] Q1 pre-filled updated with real labels:', {
      questionLabel: entryData.entryQuestion.title,
      answerLabels
    });
  }, [entryData, dynamicAnswers, userQuestionAnswers, updateUserQuestionAnswer]);

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

    // Purger les réponses des questions postérieures (cas retour-arrière + changement)
    truncateAnswersAfterIndex(currentIndex);

    setDynamicAnswer(questionCode, answerCodes, selectedEquivalences);

    // Stocker question/réponse pour debug et tracking
    const answerLabels = matchedAnswers.map(a => a.mainText);
    addUserQuestionAnswer({
      questionId: currentQuestion.id,
      questionCode: questionCode,
      questionLabel: currentQuestion.title,
      answerId: answerCodes,
      answerLabel: answerLabels,
      equivalences: selectedEquivalences,
      timestamp: Date.now(),
    });

    // Tracking DB
    trackDbEvent('questionnaire', 'question_answer', {
      question_id: currentQuestion.id,
      question_code: questionCode,
      answer_ids: answerCodes,
      equivalences: selectedEquivalences
    }, categoryId, currentIndex + 1); // step_index = numéro de la question (1-based)

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

  // Aller à la dernière question (pour retour navigateur)
  const goToLastQuestion = () => {
    if (!pathData) {
      // Si pathData pas encore chargé, on reste sur Q1 (sera recalculé après chargement)
      setCurrentIndex(0);
      return;
    }
    // La dernière question du parcours est à l'index pathData.questions.length
    // (Q1 est index 0, Q2 est index 1, etc.)
    const lastIndex = pathData.questions.length;
    setCurrentIndex(lastIndex);
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
    goToLastQuestion,

    // Flags
    canGoBack: currentIndex > 0,
    isComplete,
    isEntryQuestion: currentIndex === 0,
  };
}
