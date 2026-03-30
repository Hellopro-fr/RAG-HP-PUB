"use client";

import { useState, useCallback } from 'react';
import { useFlowStore } from '@/lib/stores/flow-store';
import { consolidateEquivalences } from '@/lib/utils/equivalence-merger';
import { normalizeMatchingToSuppliers, enrichSuppliersWithProductInfo } from '@/lib/utils/matching-normalizer';
import type { MatchingResponse, ProductInfoResponse } from '@/types/matching';
import { basePath } from '@/lib/utils';
import { useDbTracking } from '@/hooks/tracking/useDbTracking';
import { buildParcours } from '@/lib/utils/debug-matching';

// ─── Constantes Matching (partagées entre processMatching et refetch) ───
const DEFAULT_GEO_METADATA = {
  pays: "France",
  id_pays: 1,
  cp: "75001",
};

const MATCHING_TOP_K = 30;
const RERANK_TOP_K = 30;
const RERANK_ID_PROMPT = 118;

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
  isRefetching: boolean;
  error: Error | null;
  processMatching: (onProgress?: (progress: number) => void) => Promise<'selection' | 'something-to-add'>;
  refetchMatchingWithUpdatedCriteria: (
    updatedEquivalences: any[],
    removedCritiqueIds?: number[],
    removedSecondaireIds?: number[]
  ) => Promise<boolean>;
}

/**
 * Hook pour traiter le matching après le questionnaire
 * et relancer le matching après modification des critères (refetch)
 */
export function useProcessMatching(): UseProcessMatchingResult {
  const [isLoading, setIsLoading] = useState(false);
  const [isRefetching, setIsRefetching] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const {
    categoryId,
    dynamicEquivalences,
    characteristicsMap,
    matchingResults,
    selectedSupplierIds,
    setMatchingResults,
    setEquivalenceCaracteristique,
    setOrphanedSelectedSuppliers,
    setCriteriaHaveChanged,
    matchingTestParams,
  } = useFlowStore();

  const { trackDbEvent } = useDbTracking();

  // ─── processMatching : matching initial après le questionnaire ───
  const processMatching = useCallback(async (onProgress?: (progress: number) => void): Promise<'selection' | 'something-to-add'> => {
    setIsLoading(true);
    setError(null);
    // // Ancien: onProgress?.(0); — supprimé car le segment 0→25% est géré par le prix

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
      formData.append('top_k', String(MATCHING_TOP_K));
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
        top_k: RERANK_TOP_K,
        id_prompt: RERANK_ID_PROMPT,
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

      // Matching reçu → 50% (le prix gère 0→25%)
      onProgress?.(50);

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

      // Enrichissement recommandés terminé → 65%
      onProgress?.(65);

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

  // ─── refetchMatchingWithUpdatedCriteria : relancer le matching après modification des critères ───
  // (déplacé depuis useProcessMatchingLogic.ts)
  const refetchMatchingWithUpdatedCriteria = useCallback(async (
    updatedEquivalences: any[],
    removedCritiqueIds: number[] = [],
    removedSecondaireIds: number[] = []
  ): Promise<boolean> => {
    // Mettre à jour les équivalences dans le store (TOUS les critères)
    setEquivalenceCaracteristique(updatedEquivalences);

    // Filtrer les critères supprimés pour l'envoi à l'API (fusionner les deux listes)
    const allRemovedIds = [...removedCritiqueIds, ...removedSecondaireIds];
    const removedIdsSet = new Set(allRemovedIds);
    const activeEquivalences = updatedEquivalences.filter(
      (eq: any) => !removedIdsSet.has(eq.id_caracteristique)
    );

    setIsRefetching(true);

    try {
      // Valeurs par défaut pour les métadonnées géographiques (identique à processMatching)
      // // Ancien code : données dynamiques depuis profileData
      // const metadonnee_utilisateurs: Record<string, string | number> = {};
      // if (profileData?.country) {
      //   metadonnee_utilisateurs["pays"] = profileData.country;
      // }
      // if (profileData?.countryID) {
      //   metadonnee_utilisateurs["id_pays"] = profileData.countryID;
      // }
      // if (profileData?.postalCode) {
      //   metadonnee_utilisateurs["cp"] = profileData.postalCode;
      // }
      const metadonnee_utilisateurs: Record<string, string | number> = { ...DEFAULT_GEO_METADATA };

      const formData = new FormData();
      formData.append('id_categorie', categoryId?.toString() || '');
      // // Ancien top_k : formData.append('top_k', '12');
      formData.append('top_k', String(MATCHING_TOP_K));
      formData.append('champs_sortie', JSON.stringify(["url"]));
      formData.append('metadonnee_utilisateurs', JSON.stringify(metadonnee_utilisateurs));
      // Envoyer uniquement les critères actifs (non supprimés) à l'API
      formData.append('liste_caracteristique', JSON.stringify(activeEquivalences));

      // Données depuis le store pour Rerank
      const { userQuestionAnswers } = useFlowStore.getState();

      // Paramètres de scoring par défaut + paramètres de test (si présents dans l'URL)
      const defaultScoringParams = {
        c_unknown_score: 0,
        z_unmatched: 0,
      };
      const currentMatchingTestParams = useFlowStore.getState().matchingTestParams;
      const scoringParams = { ...defaultScoringParams, ...currentMatchingTestParams };
      formData.append('scoring', JSON.stringify(scoringParams));
      console.log('[MATCHING REFETCH] Scoring params:', scoringParams);

      // Bloc Rerank (mêmes constantes que processMatching)
      // // Ancien rerank : { use_rerank: true, parcours: ..., top_k: 24 }
      const rerankPayload = {
        use_rerank: true,
        parcours: buildParcours(userQuestionAnswers),
        top_k: RERANK_TOP_K,
        id_prompt: RERANK_ID_PROMPT,
      };
      formData.append('rerank', JSON.stringify(rerankPayload));

      console.log('Payload MATCHING (client - refetch):', {
        id_categorie: categoryId,
        top_k: MATCHING_TOP_K,
        metadonnee_utilisateurs,
        champs_sortie: ["url"],
        liste_caracteristique: activeEquivalences,
        removed_criteria_ids: allRemovedIds,
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

      // Normaliser les données de matching vers le format Supplier
      // Utiliser les critères actifs pour construire les specs (exclut les critères supprimés)
      const { recommended, others } = normalizeMatchingToSuppliers(
        apiData.top_produit,
        apiData.liste_produit,
        characteristicsMap,
        activeEquivalences
      );

      // Calculer totalProducts pour le tracking (utilisé plus tard)
      const totalProducts = apiData.liste_produit.length + (apiData.top_produit?.length || 0);

      // Identifier les produits orphelins (sélectionnés mais plus dans les nouveaux résultats)
      const newProductIds = new Set([
        ...recommended.map((s) => s.id),
        ...others.map((s) => s.id)
      ]);

      // Récupérer tous les produits actuels (avant mise à jour)
      const currentProducts = [
        ...(matchingResults?.recommended ?? []),
        ...(matchingResults?.others ?? [])
      ];

      // Filtrer les produits sélectionnés qui ne sont plus dans les nouveaux résultats
      const orphanedProducts = currentProducts.filter(
        (product) => selectedSupplierIds.includes(product.id) && !newProductIds.has(product.id)
      );

      // Stocker les orphelins et marquer les critères comme modifiés
      setOrphanedSelectedSuppliers(orphanedProducts);
      setCriteriaHaveChanged(true);

      // Stocker les résultats initiaux (avec placeholders)
      setMatchingResults({ recommended, others });

      // Enrichir les recommandés avec les infos produit (await - bloquant)
      let enrichedRecommended = recommended;
      const recommendedIds = recommended.map((s) => s.id);
      if (recommendedIds.length > 0) {
        const productInfo = await fetchProductInfo(recommendedIds, categoryId, apiBase);
        if (productInfo?.items) {
          enrichedRecommended = enrichSuppliersWithProductInfo(recommended, productInfo.items);
          setMatchingResults({ recommended: enrichedRecommended, others });
        }
      }

      // Enrichir les "others" avec les infos produit (await - bloquant)
      let enrichedOthers = others;
      const othersIds = others.map((s) => s.id);
      if (othersIds.length > 0) {
        const othersInfo = await fetchProductInfo(othersIds, categoryId, apiBase);
        if (othersInfo?.items) {
          enrichedOthers = enrichSuppliersWithProductInfo(others, othersInfo.items);
          setMatchingResults({ recommended: enrichedRecommended, others: enrichedOthers });
        }
      }

      // Délai pour éviter détection WAF Imperva (succession rapide d'appels)
      await new Promise(resolve => setTimeout(resolve, 500));

      // Tracking DB - Stocker le payload envoyé ET les résultats du refetch
      const refetchTrackingData = {
        request: {
          id_categorie: categoryId,
          metadonnee_utilisateurs,
          liste_caracteristique: activeEquivalences,
          removed_criteria_ids: allRemovedIds,
          scoring: scoringParams,
        },
        response: {
          results_count: totalProducts,
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
        equivalences_count: activeEquivalences.length
      };

      trackDbEvent('matching', 'refetch', refetchTrackingData, categoryId, 1);

      setIsRefetching(false);
      return true;
    } catch (error) {
      console.error('Matching refetch error:', error);
      setIsRefetching(false);
      return false;
    }
  }, [
    categoryId,
    characteristicsMap,
    matchingResults,
    selectedSupplierIds,
    setMatchingResults,
    setEquivalenceCaracteristique,
    setOrphanedSelectedSuppliers,
    setCriteriaHaveChanged,
    trackDbEvent
  ]);

  return {
    isLoading,
    isRefetching,
    error,
    processMatching,
    refetchMatchingWithUpdatedCriteria,
  };
}
