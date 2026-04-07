"use client";

import { useCallback } from 'react';
import { useFlowStore } from '@/lib/stores/flow-store';
import { consolidateEquivalences } from '@/lib/utils/equivalence-merger';
import { buildTexteRecherchePrix } from '@/lib/utils/build-texte-recherche-prix';
import { buildTextePromptPrix } from '@/lib/utils/build-texte-prompt-prix';
import { basePath } from '@/lib/utils';
import { useDbTracking } from '@/hooks/tracking/useDbTracking';
import type { PrixApiResponse } from '@/types/prix';

const getApiBasePath = () => {
  return basePath || '';
};

/**
 * Hook pour l'estimation de prix après le questionnaire.
 * Encapsule : consolidation équivalences → filtrage caracs prix → build texte → appel API → validation → store.
 */
export function usePriceEstimation() {
  const {
    categoryId,
    categoryName,
    dynamicEquivalences,
    dynamicAnswers,
    caracteristiquesPrix,
    characteristicsMap,
    userQuestionAnswers,
    setPriceEstimation,
  } = useFlowStore();

  const { trackDbEvent } = useDbTracking();

  const fetchPriceEstimation = useCallback(async () => {
    // 1. Consolider les équivalences du questionnaire
    const consolidated = consolidateEquivalences(dynamicEquivalences);
    if (consolidated.length === 0) {
      console.log('[usePriceEstimation] No equivalences to process');
      setPriceEstimation(null);
      return;
    }

    try {
      // 2. Trouver les caracteristiques_prix de la réponse Q1 sélectionnée
      const q1AnswerCode = dynamicAnswers['Q1']?.[0];
      const reponseQ1 = (caracteristiquesPrix || []).find(
        (r: any) => String(r.id_reponse) === String(q1AnswerCode)
      );
      const caracsPrix = reponseQ1?.caracteristiques_prix || [];
      const caracsPrixIds = caracsPrix.map((c: any) => Number(c.id_caracteristique));

      // 3. Filtrer les équivalences consolidées aux IDs prix (si disponibles)
      let payloadForPrix = consolidated;
      if (caracsPrixIds.length > 0) {
        const filtered = consolidated.filter(
          (item) => caracsPrixIds.includes(item.id_caracteristique)
        );
        if (filtered.length > 0) payloadForPrix = filtered;
      }

      // 4. Construire texte_recherche
      const texteRecherche = buildTexteRecherchePrix(payloadForPrix, characteristicsMap);
      if (!texteRecherche) {
        console.log('[usePriceEstimation] Empty texte_recherche, skipping');
        setPriceEstimation(null);
        return;
      }

      // 4b. Construire texte_prompt (parcours Q/R enrichi, mode prix_version=3)
      const textePrompt = buildTextePromptPrix(userQuestionAnswers, characteristicsMap);

      const requestPayload = {
        id_categorie: categoryId,
        texte_recherche: texteRecherche,
        texte_prompt: textePrompt,
        /*type_source: 'other',*/
        nom_categorie: categoryName,
      };

      console.log('[usePriceEstimation] Calling prix API with:', requestPayload);

      // 5. Appeler l'API prix
      const apiBase = getApiBasePath();
      const startTime = performance.now();
      const res = await fetch(`${apiBase}/api/prix`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestPayload),
      });
      const durationUtilisateur = Math.round(performance.now() - startTime);

      if (!res.ok) throw new Error(`Prix API error: ${res.status}`);

      const data: PrixApiResponse = await res.json();

      // Données de tracking communes (requête + temps)
      const trackingRequest = {
        id_categorie: categoryId,
        texte_recherche: texteRecherche,
        texte_prompt: textePrompt,
        /*type_source: 'other',*/
        nom_categorie: categoryName,
        equivalences_count: consolidated.length,
        prix_caracs_count: caracsPrixIds.length,
      };

      // 6. Validation : borne_basse === 0 → erreur backend silencieuse
      if (!data.success || !data.reponse) {
        console.warn('[usePriceEstimation] API returned success=false or no reponse');
        trackDbEvent('pricing', 'estimation_empty', {
          request: trackingRequest,
          reason: 'api_returned_no_data',
          duration_utilisateur: durationUtilisateur,
          time_elapsed: data.time_elapsed,
          message: data.message,
        }, categoryId);
        setPriceEstimation({ data: null, error: 'No price data' });
        return;
      }

      if (data.reponse.fourchette.borne_basse === 0) {
        console.warn('[usePriceEstimation] borne_basse === 0, treating as empty');
        trackDbEvent('pricing', 'estimation_empty', {
          request: trackingRequest,
          reason: 'borne_basse_zero',
          response: {
            fourchette: data.reponse.fourchette,
            exemples_produits: data.reponse.exemples_produits?.map(p => ({
              nom: p.nom,
              fournisseur: p.fournisseur,
              prix: p.prix,
              date: p.date,
              tva: p.tva,
            })) || [],
            phrase_prix: data.reponse.phrase_prix,
            model_version: data.api_response?.model_version,
          },
          duration_utilisateur: durationUtilisateur,
          time_elapsed: data.time_elapsed,
          message: data.message,
        }, categoryId);
        setPriceEstimation({ data: null, error: 'borne_basse is 0' });
        return;
      }

      // 7. Stocker dans le flow-store
      console.log('[usePriceEstimation] Prix estimation received:', {
        borne_basse: data.reponse.fourchette.borne_basse,
        borne_haute: data.reponse.fourchette.borne_haute,
        confiance: data.reponse.fourchette.niveau_confiance,
        exemples: data.reponse.exemples_produits.length,
      });

      // Tracking DB — estimation réussie
      trackDbEvent('pricing', 'estimation_success', {
        request: trackingRequest,
        response: {
          fourchette: data.reponse.fourchette,
          exemples_produits: data.reponse.exemples_produits.map(p => ({
            nom: p.nom,
            fournisseur: p.fournisseur,
            prix: p.prix,
            date: p.date,
            tva: p.tva,
          })),
          phrase_prix: data.reponse.phrase_prix,
          model_version: data.api_response?.model_version,
          usage_metadata: data.api_response?.usage_metadata ? {
            prompt_token_count: data.api_response.usage_metadata.prompt_token_count,
            candidates_token_count: data.api_response.usage_metadata.candidates_token_count,
            total_token_count: data.api_response.usage_metadata.total_token_count,
          } : undefined,
        },
        duration_utilisateur: durationUtilisateur,
        time_elapsed: data.time_elapsed,
        message: data.message,
      }, categoryId);

      setPriceEstimation({ data: data.reponse, error: null });

    } catch (err) {
      console.error('[usePriceEstimation] Error:', err);
      trackDbEvent('pricing', 'estimation_error', {
        request: {
          id_categorie: categoryId,
          nom_categorie: categoryName,
        },
        duration_utilisateur: null,
        error: err instanceof Error ? err.message : 'Unknown error',
      }, categoryId);
      setPriceEstimation({
        data: null,
        error: err instanceof Error ? err.message : 'Unknown error',
      });
    }
  }, [
    categoryId,
    categoryName,
    dynamicEquivalences,
    dynamicAnswers,
    caracteristiquesPrix,
    characteristicsMap,
    userQuestionAnswers,
    setPriceEstimation,
    trackDbEvent,
  ]);

  return { fetchPriceEstimation };
}
