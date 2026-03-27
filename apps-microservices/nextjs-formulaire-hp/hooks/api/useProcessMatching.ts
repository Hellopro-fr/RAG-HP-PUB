"use client";

import { useState, useCallback } from 'react';
import { useFlowStore } from '@/lib/stores/flow-store';
import { consolidateEquivalences } from '@/lib/utils/equivalence-merger';
import { normalizeMatchingToSuppliers, enrichSuppliersWithProductInfo } from '@/lib/utils/matching-normalizer';
import type { MatchingResponse, ProductInfoResponse } from '@/types/matching';
import { basePath } from '@/lib/utils';
import { useDbTracking } from '@/hooks/tracking/useDbTracking';
import { buildParcours } from '@/lib/utils/debug-matching';

// Valeurs par défaut pour les métadonnées géographiques
const DEFAULT_GEO_METADATA = {
  pays: "France",
  id_pays: 1,
  cp: "75001",
};

const getApiBasePath = () => {
  return basePath || '';
};

// Helper function to fetch product info
async function fetchProductInfo(
  productIds: string[],
  categoryId: number | null,
  apiBase: string
): Promise<ProductInfoResponse | null> {
  if (productIds.length === 0) return null;

  try {
    const res = await fetch(`${apiBase}/api/pdt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id_categorie: categoryId?.toString() || '',
        id_produits: productIds,
      }),
    });

    if (!res.ok) {
      console.error('Failed to fetch product info:', res.status);
      return null;
    }

    return await res.json();
  } catch (error) {
    console.error('Error fetching product info:', error);
    return null;
  }
}

interface UseProcessMatchingResult {
  isLoading: boolean;
  error: Error | null;
  processMatching: (onProgress?: (progress: number) => void) => Promise<'selection' | 'something-to-add'>;
}

/**
 * Hook pour traiter le matching après le questionnaire
 * Extrait la logique de geo-zone-client.tsx pour permettre
 * d'appeler le matching directement depuis le questionnaire
 */
export function useProcessMatching(): UseProcessMatchingResult {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const {
    categoryId,
    dynamicEquivalences,
    characteristicsMap,
    setMatchingResults,
    setEquivalenceCaracteristique,
    matchingTestParams,
  } = useFlowStore();

  const { trackDbEvent } = useDbTracking();

  const processMatching = useCallback(async (onProgress?: (progress: number) => void): Promise<'selection' | 'something-to-add'> => {
    setIsLoading(true);
    setError(null);
    onProgress?.(0);

    try {
      // Consolider les équivalences du questionnaire
      const consolidatedEquivalences = consolidateEquivalences(dynamicEquivalences);

      // Données depuis le store pour Rerank
      const { userQuestionAnswers } = useFlowStore.getState();

      // Sauvegarder les équivalences consolidées dans le store pour ModifyCriteriaForm
      setEquivalenceCaracteristique(consolidatedEquivalences);

      // Utiliser les valeurs par défaut pour les métadonnées géographiques
      const metadonnee_utilisateurs: Record<string, string | number> = { ...DEFAULT_GEO_METADATA };

      const formData = new FormData();
      formData.append('id_categorie', categoryId?.toString() || '');
      formData.append('top_k', '30');
      formData.append('champs_sortie', JSON.stringify(["url"]));
      formData.append('metadonnee_utilisateurs', JSON.stringify(metadonnee_utilisateurs));
      formData.append('liste_caracteristique', JSON.stringify(consolidatedEquivalences));

      // Paramètres de scoring (par défaut ou depuis URL de test)
      const scoringParams = {
        c_unknown_score: matchingTestParams?.c_unknown_score ?? 0,
        z_unmatched: matchingTestParams?.z_unmatched ?? 0,
        ...(matchingTestParams?.e_unmatched !== undefined && { e_unmatched: matchingTestParams.e_unmatched }),
        ...(matchingTestParams?.g_unknown_score !== undefined && { g_unknown_score: matchingTestParams.g_unknown_score }),
        ...(matchingTestParams?.v_blocked !== undefined && { v_blocked: matchingTestParams.v_blocked }),
        ...(matchingTestParams?.v_different !== undefined && { v_different: matchingTestParams.v_different }),
        ...(matchingTestParams?.t_unmatched !== undefined && { t_unmatched: matchingTestParams.t_unmatched }),
      };
      formData.append('scoring', JSON.stringify(scoringParams));

      // Bloc Rerank
      const rerankPayload = {
        use_rerank: true,
        parcours: buildParcours(userQuestionAnswers),
        top_k: 30,
        id_prompt: 118,
      };
      formData.append('rerank', JSON.stringify(rerankPayload));

      console.log('[useProcessMatching] Calling matching API with payload:', {
        id_categorie: categoryId,
        metadonnee_utilisateurs,
        liste_caracteristique: consolidatedEquivalences,
        liste_caracteristique_length: consolidatedEquivalences.length,
        scoring: scoringParams,
        rerank: rerankPayload
      });

      const apiBase = getApiBasePath();
      const apiUrl = `${apiBase}/api/matching`;

      const res = await fetch(apiUrl, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) throw new Error('Failed to fetch matching');

      const apiData: MatchingResponse = await res.json();

      // Normaliser les données de matching
      const { recommended, others } = normalizeMatchingToSuppliers(
        apiData.top_produit,
        apiData.liste_produit,
        characteristicsMap,
        consolidatedEquivalences
      );

      // Seuil minimum de produits pour afficher la sélection
      // Condition : au moins 2 produits dans top_produit avec score >= 0.3 (30%)
      const MIN_TOP_PRODUCTS = 2;
      const MIN_SCORE_THRESHOLD = 0.3;
      const topProductsWithGoodScore = (apiData.top_produit || []).filter(
        (p: any) => Number(p.score) >= MIN_SCORE_THRESHOLD
      );
      const totalProducts = apiData.liste_produit.length + (apiData.top_produit?.length || 0);
      const hasInsufficientResults = topProductsWithGoodScore.length < MIN_TOP_PRODUCTS;

      // Matching reçu → 25%
      onProgress?.(25);

      // Stocker les résultats initiaux
      setMatchingResults({ recommended, others });

      // Enrichir avec les infos produit
      const apiBase2 = getApiBasePath();

      // Enrichir les recommandés
      let enrichedRecommended = recommended;
      const recommendedIds = recommended.map((s) => s.id);
      if (recommendedIds.length > 0) {
        const productInfo = await fetchProductInfo(recommendedIds, categoryId, apiBase2);
        if (productInfo?.items) {
          enrichedRecommended = enrichSuppliersWithProductInfo(recommended, productInfo.items);
          setMatchingResults({ recommended: enrichedRecommended, others });
        }
      }

      // Enrichissement recommandés terminé → 50%
      onProgress?.(50);

      // Enrichir les autres
      let enrichedOthers = others;
      const othersIds = others.map((s) => s.id);
      if (othersIds.length > 0) {
        const othersInfo = await fetchProductInfo(othersIds, categoryId, apiBase2);
        if (othersInfo?.items) {
          enrichedOthers = enrichSuppliersWithProductInfo(others, othersInfo.items);
          setMatchingResults({ recommended: enrichedRecommended, others: enrichedOthers });
        }
      }

      // Enrichissement autres terminé → 75%
      onProgress?.(75);

      console.log('[useProcessMatching] Matching completed:', {
        recommendedCount: enrichedRecommended.length,
        othersCount: enrichedOthers.length
      });

      // Tracking DB - Matching results
      const matchingTrackingData = {
        request: {
          id_categorie: categoryId,
          metadonnee_utilisateurs,
          liste_caracteristique: consolidatedEquivalences,
          scoring: scoringParams,
        },
        response: {
          results_count: totalProducts,
          top_products_with_good_score: topProductsWithGoodScore.length,
          min_top_products: MIN_TOP_PRODUCTS,
          min_score_threshold: MIN_SCORE_THRESHOLD,
          redirect_to: hasInsufficientResults ? 'something-to-add' : 'selection',
          top_products: apiData.top_produit?.map((p: any) => ({
            id: p.id_produit,
            score: Number(Number(p.score).toFixed(2)),
            id_fournisseur: p.id_fournisseur
          })) || [],
          liste_products: apiData.liste_produit.map((p: any) => ({
            id: p.id_produit,
            score: Number(Number(p.score).toFixed(2)),
            id_fournisseur: p.id_fournisseur
          })),
        },
        equivalences_count: consolidatedEquivalences.length,
        has_insufficient_results: hasInsufficientResults,
        will_redirect_to_something_to_add: hasInsufficientResults,
      };

      trackDbEvent(
        'matching',
        hasInsufficientResults ? 'insufficient_results' : 'success',
        matchingTrackingData,
        categoryId,
        2
      );

      // Délai pour éviter détection WAF
      await new Promise(resolve => setTimeout(resolve, 500));

      setIsLoading(false);
      return hasInsufficientResults ? 'something-to-add' : 'selection';

    } catch (err) {
      console.error('[useProcessMatching] Matching error:', err);
      setError(err instanceof Error ? err : new Error('Unknown error'));
      setIsLoading(false);
      return 'something-to-add';
    }
  }, [
    categoryId,
    dynamicEquivalences,
    characteristicsMap,
    setMatchingResults,
    setEquivalenceCaracteristique,
    matchingTestParams,
    trackDbEvent
  ]);

  return {
    isLoading,
    error,
    processMatching,
  };
}
