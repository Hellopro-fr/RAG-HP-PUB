"use client";

import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import NeedsQuestionnaire from '@/components/flow/NeedsQuestionnaire';
import MatchingLoaderV2 from '@/components/flow/MatchingLoaderV2';
import { useFlowStore, useFlowStoreHydration, FLOW_ORIGINAL_TOKEN_KEY, type MatchingTestParams } from '@/lib/stores/flow-store';
import { useFlowNavigation } from '@/hooks/useFlowNavigation';
import { useDbTracking } from '@/hooks/tracking/useDbTracking';
import { useProcessMatching } from '@/hooks/api/useProcessMatching';
import { usePriceEstimation } from '@/hooks/api/usePriceEstimation';

// Interface pour les données URL (réponse Q1 pré-remplie)
interface UrlData {
  id_question: number;
  id_reponse: number;
  equivalence: any[];
  abtest_UX_lead_version?: number;
}

interface QuestionnaireClientProps {
  initialCategoryId?: string;
  initialUrlData?: string; // Base64 encoded URL data
  initialToken?: string;   // Token original pour redirection après F5
  initialDdc?: string;   // Token original pour redirection après F5
}

export default function QuestionnaireClient({
  initialCategoryId,
  initialUrlData,
  initialToken,
  initialDdc
}: QuestionnaireClientProps) {
  const searchParams = useSearchParams();
  const { setCategoryId, setDynamicAnswer, dynamicAnswers, addUserQuestionAnswer, setDdc, setMatchingTestParams, setAbtestUxLeadVersion } = useFlowStore();
  const { goToSelection, goToSomethingToAdd } = useFlowNavigation();
  const { processMatching } = useProcessMatching();
  const { fetchPriceEstimation } = usePriceEstimation();
  const hasProcessedUrlData = useRef(false);
  const isHydrated = useFlowStoreHydration();

  // État pour contrôler le rendu du questionnaire
  // On attend que les données URL soient traitées avant de rendre
  const [isReady, setIsReady] = useState(false);

  // État pour le loader de matching et la destination après
  const [showLoader, setShowLoader] = useState(false);
  const [loaderProgress, setLoaderProgress] = useState(0);
  const [redirectDestination, setRedirectDestination] = useState<'selection' | 'something-to-add' | 'budget' | null>(null);

  // Récupérer et stocker le categoryId + sauvegarder le token original
  // Priorité : props du Server Component > searchParams client
  useEffect(() => {
    let categoryId = initialCategoryId;

    // Fallback: searchParams côté client (pour navigation interne)
    if (!categoryId) {
      categoryId = searchParams.get('categoryId') || searchParams.get('id_categorie') || undefined;
    }

    if (categoryId) {
      const id = parseInt(categoryId, 10);
      if (!isNaN(id) && id > 0) {
        setCategoryId(id);
      }
    }

    if (initialDdc) {
      setDdc(initialDdc);
      //console.log('[QuestionnaireClient] DDC set from initial props:', initialDdc);
    }

    if(initialDdc){
      setDdc(initialDdc);
      //console.log('[QuestionnaireClient] DDC set from initial props:', initialDdc);
    }
    // Sauvegarder le token original dans sessionStorage (separe du flow-store)
    // Ce token sera utilise pour la redirection apres F5
    // Priorite : prop du Server Component > searchParams client
    const token = initialToken || searchParams.get('token');
    if (token && typeof window !== 'undefined') {
      sessionStorage.setItem(FLOW_ORIGINAL_TOKEN_KEY, token);
      //console.log('[QuestionnaireClient] Token saved for redirect:', token.substring(0, 20) + '...');
    }
  }, [initialCategoryId, initialToken, searchParams, setCategoryId, initialDdc]);

  // Lire les paramètres de test du matching depuis l'URL (pour tests uniquement)
  useEffect(() => {
    const testParamKeys: (keyof MatchingTestParams)[] = [
      'z_unmatched',
      'e_unmatched',
      'g_unknown_score',
      'c_unknown_score',
      'v_blocked',
      'v_different',
      't_unmatched',
    ];

    console.log('[QuestionnaireClient] Reading scoring params from URL...');
    console.log('[QuestionnaireClient] Current URL searchParams:', Object.fromEntries(searchParams.entries()));

    const params: MatchingTestParams = {};
    let hasAnyParam = false;

    for (const key of testParamKeys) {
      const value = searchParams.get(key);
      if (value !== null) {
        const numValue = parseFloat(value);
        if (!isNaN(numValue)) {
          params[key] = numValue;
          hasAnyParam = true;
          console.log(`[QuestionnaireClient] Found param ${key}=${numValue}`);
        }
      }
    }

    // Stocker seulement si au moins un paramètre est présent
    if (hasAnyParam) {
      setMatchingTestParams(params);
      console.log('[QuestionnaireClient] Stored matching test params:', params);
    } else {
      console.log('[QuestionnaireClient] No scoring params found in URL');
    }

  }, [searchParams, setMatchingTestParams]);

  // Traiter les données URL (réponse Q1 pré-remplie depuis le token)
  // Doit s'exécuter AVANT que le questionnaire ne soit rendu
  const { trackDbEvent } = useDbTracking();

  useEffect(() => {
    // Attendre l'hydratation du store
    if (!isHydrated) return;

    // Éviter les doubles traitements
    if (hasProcessedUrlData.current) {
      setIsReady(true);
      return;
    }

    // Récupérer urlData depuis props ou searchParams
    let urlDataBase64 = initialUrlData;
    if (!urlDataBase64) {
      urlDataBase64 = searchParams.get('urlData') || undefined;
    }

    // Si pas de données URL, marquer comme prêt et continuer
    if (!urlDataBase64) {
      hasProcessedUrlData.current = true;
      setIsReady(true);
      return;
    }

    // Si Q1 déjà répondu, ne pas écraser
    if (dynamicAnswers['Q1']?.length > 0) {
      hasProcessedUrlData.current = true;
      setIsReady(true);
      return;
    }

    try {
      // Décoder Base64 URL-safe
      let base64 = urlDataBase64.replace(/-/g, '+').replace(/_/g, '/');
      const padding = base64.length % 4;
      if (padding) {
        base64 += '='.repeat(4 - padding);
      }

      const urlDataJson = atob(base64);
      const urlData: UrlData = JSON.parse(urlDataJson);

      // Stocker la version AB-test issue du token (disponible globalement via le store)
      if (typeof urlData.abtest_UX_lead_version === 'number') {
        setAbtestUxLeadVersion(urlData.abtest_UX_lead_version);
      }

      // Vérifier que les données sont valides
      if (urlData.id_reponse) {
        // Stocker la réponse Q1 et son équivalence dans le flow store
        const answerCode = String(urlData.id_reponse);
        const equivalence = Array.isArray(urlData.equivalence) ? urlData.equivalence : [];

        setDynamicAnswer('Q1', [answerCode], equivalence);

        // Enregistrer aussi dans userQuestionAnswers pour debug
        addUserQuestionAnswer({
          questionId: urlData.id_question,
          questionCode: 'Q1',
          questionLabel: 'Q1 (pre-remplie via URL)',
          answerId: [answerCode],
          answerLabel: [`Reponse ID: ${answerCode}`],
          equivalences: equivalence,
          timestamp: Date.now(),
        });

        // Tracking DB pour la question pré-remplie
        // Cela permet de garder une trace du début du parcours même si Q1 est invisible
        const categoryIdNum = parseInt(initialCategoryId || '0', 10);
        trackDbEvent('questionnaire', 'question_answer', {
          question_id: urlData.id_question,
          question_code: 'Q1',
          answer_ids: [answerCode],
          equivalences: equivalence,
          is_prefilled: true // Flag pour indiquer que c'est une injection via URL
        }, categoryIdNum, 1); // step_index = 1

        console.log('[QuestionnaireClient] URL data applied - Q1 pre-filled:', answerCode);
      }
    } catch (error) {
      console.error('[QuestionnaireClient] Error processing URL data:', error);
    }

    hasProcessedUrlData.current = true;
    setIsReady(true);
  }, [isHydrated, initialUrlData, searchParams, dynamicAnswers, setDynamicAnswer, trackDbEvent, initialCategoryId, addUserQuestionAnswer, setAbtestUxLeadVersion]);

  const handleComplete = async () => {
    // Afficher le loader et lancer matching + prix en parallèle
    setShowLoader(true);

    // Wrapper monotone : le progress ne recule jamais (protection contre les réponses tardives)
    const safeProgress = (value: number) => setLoaderProgress(prev => Math.max(prev, value));

    // Lancer prix et matching en parallèle
    // Le prix répond plus vite → met à jour le progress à 25%
    // Le matching prend le relais (50→65→75) via safeProgress
    const prixPromise = fetchPriceEstimation()
      .then(() => { safeProgress(25); })
      .catch((err) => {
        console.error('[Prix] Error (non-blocking):', err);
        safeProgress(25); // Même en erreur, on avance
      });

    const matchingPromise = processMatching(safeProgress); // progress interne : 50→65→75

    const [, destination] = await Promise.all([prixPromise, matchingPromise]);

    setLoaderProgress(100);
    // Attendre que la barre anime jusqu'à 100% avant de naviguer
    await new Promise(resolve => setTimeout(resolve, 1500));
    // Intercaler la page /budget avant /selection. Le flow alternatif
    // 'something-to-add' reste tel quel (pas de budget si flow dégradé).
    const finalDestination = destination === 'something-to-add' ? destination : 'budget';
    setRedirectDestination(finalDestination);
  };

  // Navigation dès que les données sont prêtes (matching + prix terminés)
  useEffect(() => {
    if (redirectDestination) {
      if (redirectDestination === 'something-to-add') {
        goToSomethingToAdd();
      } else if (redirectDestination === 'budget') {
        goToBudget();
      } else {
        goToSelection();
      }
    }
  }, [redirectDestination, goToSelection, goToSomethingToAdd, goToBudget]);

  // Afficher le loader pendant le matching
  if (showLoader) {
    return <MatchingLoaderV2 externalProgress={loaderProgress} />;
  }

  // Attendre que les données URL soient traitées avant de rendre le questionnaire
  // Cela garantit que le hook useDynamicQuestionnaire s'initialise avec les bonnes données
  if (!isReady) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-background">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  return (
    <NeedsQuestionnaire
      onComplete={handleComplete}
      rubriqueId={initialCategoryId}
    />
  );
}
