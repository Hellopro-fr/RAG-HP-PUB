import { useState } from 'react';
import { useFlowStore } from '@/lib/stores/flow-store';
import { consolidateEquivalences } from '@/lib/utils/equivalence-merger';
import { normalizeMatchingToSuppliers, enrichSuppliersWithProductInfo } from '@/lib/utils/matching-normalizer';
import type { ProfileData } from '@/types';
import type { MatchingResponse, ProductInfoResponse } from '@/types/matching';
import { useDbTracking } from '@/hooks/tracking/useDbTracking';

import { basePath } from '@/lib/utils';

/**
 * Récupère les informations produits depuis l'API
 */
async function fetchProductInfo(
  productIds: string[],
  categoryId: number | null,
  apiBase: string
): Promise<ProductInfoResponse | null> {
  if (productIds.length === 0) return null;

  try {
    const res = await fetch(`${apiBase}/api/produits`, {
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

// Toujours utiliser le proxy Next.js pour éviter les problèmes CORS
const getApiBasePath = () => {
  return basePath || '';
};

const type_typologie = {
  "pro_france": "1",      // Professionnel
  "pro_foreign": "1",     // Professionnel
  "particulier": "2",     // Particulier
  "creation": "1",        // Professionnel
};

export function useProcessMatchingLogic() {
  const [showLoader, setShowLoader] = useState(false);
  const [redirectGoToSomethingToAdd, setRedirectGoToSomethingToAdd] = useState(false);
  const {
    categoryId,
    profileData,
    dynamicEquivalences,
    characteristicsMap,
    matchingResults,
    selectedSupplierIds,
    matchingTestParams,
    setEquivalenceCaracteristique,
    setMatchingResults,
    setOrphanedSelectedSuppliers,
    setCriteriaHaveChanged
  } = useFlowStore();

  const { trackDbEvent } = useDbTracking();

  /**
   * Logique de consolidation des équivalences :
   * 1. Collecter toutes les équivalences avec poids_question
   * 2. Regrouper par id_caracteristique
   * 3. Poids final : critique > secondaire, puis poids_question le plus élevé
   * 4. Fusionner valeurs cibles / bloquantes
   */
  const processEquivalences = () => {
    return consolidateEquivalences(dynamicEquivalences);
  };

  /**
   * Action principale de soumission
   */
  const submitProfile = async (data: ProfileData) => {
    const consolidatedEquivalences = processEquivalences();
    setEquivalenceCaracteristique(consolidatedEquivalences);

    setShowLoader(true);

    // Tracking DB - Profile completion
    trackDbEvent('profile', 'complete', {
      profile_type: data?.type,
      country: data?.country,
      equivalences_count: consolidatedEquivalences.length
    }, categoryId, 1); // step_index = 1 (une seule étape pour le profil)

    try {

      const typologie = data?.type;
      const typologieValue = type_typologie[typologie as keyof typeof type_typologie] || "1";

      // Construire metadonnee_utilisateurs avec id_pays et cp si disponibles
      const metadonnee_utilisateurs: Record<string, string | number> = {
        "pays": data?.country || '',
          "typologie": typologieValue
      };

      // Ajouter id_pays si disponible (vient de l'API geo)
      if (data?.countryID) {
        metadonnee_utilisateurs["id_pays"] = data.countryID;
      }

      // Ajouter cp (code postal) si disponible
      if (data?.postalCode) {
        metadonnee_utilisateurs["cp"] = data.postalCode;
      }

      const formData = new FormData();
      formData.append('id_categorie', categoryId?.toString() || '');
      formData.append('top_k', '12');
      formData.append('champs_sortie', JSON.stringify(["url"]));
      formData.append('metadonnee_utilisateurs', JSON.stringify(metadonnee_utilisateurs));
      formData.append('liste_caracteristique', JSON.stringify(consolidatedEquivalences));

      // Ajouter les paramètres de test du matching (si présents dans l'URL)
      if (matchingTestParams) {
        formData.append('matching_test_params', JSON.stringify(matchingTestParams));
      }

      console.log('Payload MATCHING :', {
        id_categorie: categoryId,
        top_k: 12,
        champs_sortie: ["url"],
        metadonnee_utilisateurs,
        liste_caracteristique: consolidatedEquivalences,
        ...(matchingTestParams && { matching_test_params: matchingTestParams })
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
      // L'API retourne maintenant deux listes séparées : top_produit et liste_produit
      const { recommended, others } = normalizeMatchingToSuppliers(
        apiData.top_produit,
        apiData.liste_produit,
        characteristicsMap,
        consolidatedEquivalences
      );
      

      
      // TODO a dynamiser
      // setRedirectGoToSomethingToAdd(apiData.liste_produit.length < 10);
      
      // Tracking DB - Matching results
      // TODO a dynamiser tracking si pas assez de produits
      if (false) {
        // Insufficient results
        trackDbEvent('matching', 'insufficient_results', {
          results_count: apiData.liste_produit.length,
          threshold: 2,
          product_ids: apiData.liste_produit.map((p: any) => p.id_produit)
        }, categoryId, 1);
      } else {
        // Sufficient results
        trackDbEvent('matching', 'success', {
          results_count: apiData.liste_produit.length,
          threshold: 2,
          product_ids: apiData.liste_produit.map((p: any) => p.id_produit),
          top_product_ids: apiData.top_produit?.map((p: any) => p.id_produit) || []
        }, categoryId, 1);
      }

      // ==========================================================================
      // TODO: SUPPRIMER CE BLOC DE TEST - Début du mode test avec IDs fixes
      // ==========================================================================
      const TEST_MODE = true; // TODO: Mettre à false pour la production

      let finalRecommended = recommended;
      let finalOthers = others;

      if (TEST_MODE) {
        // TODO: Supprimer - Créer des suppliers de test avec les IDs 97 et 98
        const testSuppliers = [
          {
            id: '97',
            productName: 'Produit 97',
            supplierName: 'Fournisseur Test',
            image: '/images/product-placeholder.jpg',
            images: ['/images/product-placeholder.jpg'],
            description: '',
            matchScore: 88,
            matchGaps: [],
            specs: [],
            isRecommended: true,
            rating: 0,
            distance: 0,
            supplier: { name: '', description: '', location: '', responseTime: '' }
          },
          {
            id: '98',
            productName: 'Produit 98',
            supplierName: 'Fournisseur Test',
            image: '/images/product-placeholder.jpg',
            images: ['/images/product-placeholder.jpg'],
            description: '',
            matchScore: 75,
            matchGaps: [],
            specs: [],
            isRecommended: true,
            rating: 0,
            distance: 0,
            supplier: { name: '', description: '', location: '', responseTime: '' }
          },
        ];
        finalRecommended = testSuppliers as typeof recommended;
        finalOthers = [];
      }
      // ==========================================================================
      // TODO: SUPPRIMER CE BLOC DE TEST - Fin du mode test
      // ==========================================================================

      // Stocker les résultats initiaux (avec placeholders)
      setMatchingResults({ recommended, others });

      // Enrichir les recommandés avec les infos produit (prioritaire)
      const recommendedIds = recommended.map((s) => s.id);
      if (recommendedIds.length > 0) {
        const productInfo = await fetchProductInfo(recommendedIds, categoryId, apiBase);
        if (productInfo?.items) {
          const enrichedRecommended = enrichSuppliersWithProductInfo(recommended, productInfo.items);
          setMatchingResults({ recommended: enrichedRecommended, others });

          // Ensuite enrichir les "others" en background
          const othersIds = others.map((s) => s.id);
          if (othersIds.length > 0) {
            fetchProductInfo(othersIds, categoryId, apiBase).then((othersInfo) => {
              if (othersInfo?.items) {
                const enrichedOthers = enrichSuppliersWithProductInfo(others, othersInfo.items);
                setMatchingResults({ recommended: enrichedRecommended, others: enrichedOthers });
              }
            });
          }
        }
      }

    } catch (error) {
      console.error('Matching process error:', error);
      setShowLoader(false);
    }
  };

  /**
   * Relancer le matching avec des caractéristiques modifiées
   * Utilisé quand l'utilisateur affine ses critères dans ModifyCriteriaForm
   *
   * @param updatedEquivalences - TOUS les critères (y compris ceux marqués comme supprimés)
   * @param removedCritiqueIds - IDs des critères critiques supprimés (passés directement pour éviter stale closure)
   * @param removedSecondaireIds - IDs des critères secondaires supprimés (passés directement pour éviter stale closure)
   */
  const refetchMatchingWithUpdatedCriteria = async (
    updatedEquivalences: any[],
    removedCritiqueIds: number[] = [],
    removedSecondaireIds: number[] = []
  ) => {
    // Mettre à jour les équivalences dans le store (TOUS les critères)
    setEquivalenceCaracteristique(updatedEquivalences);

    // Filtrer les critères supprimés pour l'envoi à l'API (fusionner les deux listes)
    const allRemovedIds = [...removedCritiqueIds, ...removedSecondaireIds];
    const removedIdsSet = new Set(allRemovedIds);
    const activeEquivalences = updatedEquivalences.filter(
      (eq: any) => !removedIdsSet.has(eq.id_caracteristique)
    );

    setShowLoader(true);

    try {
      // Récupérer les métadonnées utilisateur du profileData
      const typologie = profileData?.type;
      const typologieValue = type_typologie[typologie as keyof typeof type_typologie] || "1";

      const metadonnee_utilisateurs: Record<string, string | number> =  {
        "pays": profileData?.country || '',
        "typologie": typologieValue
      };

      // Ajouter id_pays si disponible (vient de l'API geo)
      if (profileData?.countryID) {
        metadonnee_utilisateurs["id_pays"] = profileData.countryID;
      }

      // Ajouter cp (code postal) si disponible
      if (profileData?.postalCode) {
        metadonnee_utilisateurs["cp"] = profileData.postalCode;
      }

      const formData = new FormData();
      formData.append('id_categorie', categoryId?.toString() || '');
      formData.append('top_k', '12');
      formData.append('champs_sortie', JSON.stringify(["url"]));
      formData.append('metadonnee_utilisateurs', JSON.stringify(metadonnee_utilisateurs));
      // Envoyer uniquement les critères actifs (non supprimés) à l'API
      formData.append('liste_caracteristique', JSON.stringify(activeEquivalences));

      // Ajouter les paramètres de test du matching (si présents dans l'URL)
      if (matchingTestParams) {
        formData.append('matching_test_params', JSON.stringify(matchingTestParams));
      }

      console.log('Payload MATCHING (client - refetch):', {
        id_categorie: categoryId,
        top_k: 12,
        metadonnee_utilisateurs,
        champs_sortie: ["url"],
        liste_caracteristique: activeEquivalences,
        removed_criteria_ids: allRemovedIds,
        ...(matchingTestParams && { matching_test_params: matchingTestParams })
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

      // Enrichir les recommandés avec les infos produit (prioritaire)
      const recommendedIds = recommended.map((s) => s.id);
      if (recommendedIds.length > 0) {
        const productInfo = await fetchProductInfo(recommendedIds, categoryId, apiBase);
        if (productInfo?.items) {
          const enrichedRecommended = enrichSuppliersWithProductInfo(recommended, productInfo.items);
          setMatchingResults({ recommended: enrichedRecommended, others });

          // Ensuite enrichir les "others" en background
          const othersIds = others.map((s) => s.id);
          if (othersIds.length > 0) {
            fetchProductInfo(othersIds, categoryId, apiBase).then((othersInfo) => {
              if (othersInfo?.items) {
                const enrichedOthers = enrichSuppliersWithProductInfo(others, othersInfo.items);
                setMatchingResults({ recommended: enrichedRecommended, others: enrichedOthers });
              }
            });
          }
        }
      }

      setShowLoader(false);
      return true;
    } catch (error) {
      console.error('Matching refetch error:', error);
      setShowLoader(false);
      return false;
    }
  };

  const resetLoader = () => {
    setShowLoader(false);
  };

  return {
    showLoader,
    submitProfile,
    refetchMatchingWithUpdatedCriteria,
    resetLoader,
    redirectGoToSomethingToAdd
  };
}
