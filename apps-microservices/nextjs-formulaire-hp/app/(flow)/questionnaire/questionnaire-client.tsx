"use client";

import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import NeedsQuestionnaire from '@/components/flow/NeedsQuestionnaire';
import { useFlowStore, useFlowStoreHydration, FLOW_ORIGINAL_TOKEN_KEY } from '@/lib/stores/flow-store';
import { useFlowNavigation } from '@/hooks/useFlowNavigation';

// Interface pour les données URL (réponse Q1 pré-remplie)
interface UrlData {
  id_question: number;
  id_reponse: number;
  equivalence: any[];
}

interface QuestionnaireClientProps {
  initialCategoryId?: string;
  initialUrlData?: string; // Base64 encoded URL data
  initialToken?: string;   // Token original pour redirection après F5
}

export default function QuestionnaireClient({
  initialCategoryId,
  initialUrlData,
  initialToken
}: QuestionnaireClientProps) {
  const searchParams = useSearchParams();
  const { setCategoryId, setDynamicAnswer, dynamicAnswers } = useFlowStore();
  const { goToProfile } = useFlowNavigation();
  const hasProcessedUrlData = useRef(false);
  const isHydrated = useFlowStoreHydration();

  // État pour contrôler le rendu du questionnaire
  // On attend que les données URL soient traitées avant de rendre
  const [isReady, setIsReady] = useState(false);

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

    // Sauvegarder le token original dans sessionStorage (separe du flow-store)
    // Ce token sera utilise pour la redirection apres F5
    // Priorite : prop du Server Component > searchParams client
    const token = initialToken || searchParams.get('token');
    if (token && typeof window !== 'undefined') {
      sessionStorage.setItem(FLOW_ORIGINAL_TOKEN_KEY, token);
      console.log('[QuestionnaireClient] Token saved for redirect:', token.substring(0, 20) + '...');
    }
  }, [initialCategoryId, initialToken, searchParams, setCategoryId]);

  // Traiter les données URL (réponse Q1 pré-remplie depuis le token)
  // Doit s'exécuter AVANT que le questionnaire ne soit rendu
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

      // Vérifier que les données sont valides
      if (urlData.id_reponse) {
        // Stocker la réponse Q1 et son équivalence dans le flow store
        const answerCode = String(urlData.id_reponse);
        const equivalence = Array.isArray(urlData.equivalence) ? urlData.equivalence : [];

        setDynamicAnswer('Q1', [answerCode], equivalence);
        console.log('[QuestionnaireClient] URL data applied - Q1 pre-filled:', answerCode);
      }
    } catch (error) {
      console.error('[QuestionnaireClient] Error processing URL data:', error);
    }

    hasProcessedUrlData.current = true;
    setIsReady(true);
  }, [isHydrated, initialUrlData, searchParams, dynamicAnswers, setDynamicAnswer]);

  const handleComplete = () => {
    // Navigate to profile step with GET params preserved
    goToProfile();
  };

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
