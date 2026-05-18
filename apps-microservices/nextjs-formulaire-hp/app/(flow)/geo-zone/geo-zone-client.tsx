"use client";

import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import GeoZoneStep from '@/components/flow/GeoZoneStep';
import MatchingLoader from '@/components/flow/MatchingLoader';
import MatchingLoaderV2 from '@/components/flow/MatchingLoaderV2';
import { parseSelectionVersion } from '@/types/selectionVersion';
import { useFlowStore } from '@/lib/stores/flow-store';
import { useFlowNavigation } from '@/hooks/useFlowNavigation';
import { consolidateEquivalences } from '@/lib/utils/equivalence-merger';
import { normalizeMatchingToSuppliers, enrichSuppliersWithProductInfo } from '@/lib/utils/matching-normalizer';
import type { GeoData } from '@/lib/stores/flow-store';
import type { MatchingResponse, ProductInfoResponse } from '@/types/matching';
import { basePath } from '@/lib/utils';
import { trackGeoZoneView, trackGeoZoneComplete } from '@/lib/analytics';
import { useDbTracking } from '@/hooks/tracking/useDbTracking';


interface Country {
  id: number;
  libelle: string;
}

interface GeoZoneClientProps {
  priorityCountries: Country[];
  otherCountries: Country[];
}

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

const getApiBasePath = () => {
  return basePath || '';
};

export default function GeoZoneClient({
  priorityCountries = [],
  otherCountries = []
}: GeoZoneClientProps) {
  const searchParams = useSearchParams();
  const { setGeoData, categoryId, dynamicEquivalences, characteristicsMap, setMatchingResults, setEquivalenceCaracteristique } = useFlowStore();
  const [showLoader, setShowLoader] = useState(false);
  const [RedirectGoToSomethingToAdd, setRedirectGoToSomethingToAdd] = useState(false);
  const { goToSelection, goToSomethingToAdd } = useFlowNavigation();
  const { trackDbEvent } = useDbTracking();
  const hasTrackedView = useRef(false);

  // Track page view au montage (sauf si retour navigateur)
  useEffect(() => {
    if (!hasTrackedView.current) {
      hasTrackedView.current = true;

      // Ne pas tracker si c'est un retour navigateur (evite le pushState GTM)
      const navEntries = performance.getEntriesByType('navigation') as PerformanceNavigationTiming[];
      const navType = navEntries.length > 0 ? navEntries[0].type : 'navigate';
      const isBackForward = navType === 'back_forward';

      if (!isBackForward) {
        trackGeoZoneView();

        // Track DB - page view
        const equivalencesCount = Object.keys(dynamicEquivalences).length;
        trackDbEvent('profile', 'geo_zone_view', {
          has_dynamic_equivalences: equivalencesCount > 0,
          equivalences_count: equivalencesCount,
        }, categoryId, 1);
      }
    }
  }, [trackDbEvent, categoryId, dynamicEquivalences]);

  const handleComplete = async (data: GeoData) => {
    // Track la complétion de l'étape geo-zone
    trackGeoZoneComplete();

    // Track DB - geo-zone complete
    trackDbEvent('profile', 'geo_zone_complete', {
      country: data.country,
      country_id: data.countryId,
      has_postal_code: !!data.postalCode,
      has_city: !!data.city,
    }, categoryId, 1);

    // Sauvegarder les données dans le store
    setGeoData(data);

    // Afficher le loader
    setShowLoader(true);

    // TODO: Définir le format exact des données pour l'API matching
    // Pour l'instant, on utilise les données disponibles: geoData + equivalences du questionnaire
    console.log('[GeoZone] Preparing matching with:', {
      geoData: data,
      categoryId,
      equivalencesCount: dynamicEquivalences.length
    });

    try {
      // Consolider les équivalences du questionnaire
      const consolidatedEquivalences = consolidateEquivalences(dynamicEquivalences);

      // Sauvegarder les équivalences consolidées dans le store pour ModifyCriteriaForm
      setEquivalenceCaracteristique(consolidatedEquivalences);

      // Préparer les métadonnées utilisateur avec les données géo
      // N'ajouter que les champs renseignés
      const metadonnee_utilisateurs: Record<string, string | number> = {};

      if (data.country) {
        metadonnee_utilisateurs["pays"] = data.country;
      }

      if (data.countryId) {
        metadonnee_utilisateurs["id_pays"] = data.countryId;
      }

      if (data.postalCode) {
        metadonnee_utilisateurs["cp"] = data.postalCode;
      }

      const formData = new FormData();
      formData.append('id_categorie', categoryId?.toString() || '');
      formData.append('top_k', '12');
      formData.append('champs_sortie', JSON.stringify(["url"]));
      formData.append('metadonnee_utilisateurs', JSON.stringify(metadonnee_utilisateurs));
      formData.append('liste_caracteristique', JSON.stringify(consolidatedEquivalences));

      // Paramètres de scoring par défaut
      const scoringParams = {
        c_unknown_score: 0,
        z_unmatched: 0,
      };
      formData.append('scoring', JSON.stringify(scoringParams));

      console.log('[GeoZone] Calling matching API with payload:', {
        id_categorie: categoryId,
        metadonnee_utilisateurs,
        liste_caracteristique: consolidatedEquivalences,
        liste_caracteristique_length: consolidatedEquivalences.length,
        scoring: scoringParams
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
      const MIN_TOP_PRODUCTS         = 2;
      const MIN_SCORE_THRESHOLD      = 0.3;
      const topProductsWithGoodScore = (apiData.top_produit || []).filter(
        (p: any) => Number(p.score) >= MIN_SCORE_THRESHOLD
      );
      const totalProducts = apiData.liste_produit.length + (apiData.top_produit?.length || 0);
      const hasInsufficientResults = topProductsWithGoodScore.length < MIN_TOP_PRODUCTS;
      setRedirectGoToSomethingToAdd(hasInsufficientResults);

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

      console.log('[GeoZone] Matching completed:', {
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

    } catch (error) {
      // En cas d'erreur, On bascule vers la demande sur catégorie
      setRedirectGoToSomethingToAdd(true);
      console.error('[GeoZone] Matching error:', error);
    }
  };

  const handleLoaderComplete = () => {
    // Navigation après le loader
    if(RedirectGoToSomethingToAdd){
      goToSomethingToAdd();
    }else{
      goToSelection();
    }
  };

  const handleBack = () => {
    // Utiliser history.back() pour declencher une vraie navigation "retour"
    // Cela permet au questionnaire de detecter le retour et afficher la derniere question
    window.history.back();
  };

  // Afficher le loader pendant le matching — variante par version
  if (showLoader) {
    const version = parseSelectionVersion(searchParams.get('version'));
    return version === 'originale'
      ? <MatchingLoader onComplete={handleLoaderComplete} duration={5000} />
      : <MatchingLoaderV2 onComplete={handleLoaderComplete} duration={5000} />;
  }

  return (
    <GeoZoneStep
      onComplete={handleComplete}
      onBack={handleBack}
      priorityCountries={priorityCountries}
      otherCountries={otherCountries}
    />
  );
}
