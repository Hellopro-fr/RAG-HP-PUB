"use client";

import { useCallback } from 'react';
import { useFlowStore } from '@/lib/stores/flow-store';
import { consolidateEquivalences } from '@/lib/utils/equivalence-merger';
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
      // 2. Récupérer la réponse Q1 (id + libellé) — utilisée par le backend v2 pour le filtrage strict
      const q1AnswerCode = dynamicAnswers['Q1']?.[0] || '';
      const q1Entry = userQuestionAnswers.find((qa) => qa.questionCode === 'Q1');
      const q1AnswerLabel = q1Entry?.answerLabel;
      const q1AnswerName = Array.isArray(q1AnswerLabel)
        ? q1AnswerLabel.join(', ')
        : (q1AnswerLabel || '');

      // 3. Construire texte_prompt (parcours Q/R enrichi)
      const textePrompt = buildTextePromptPrix(userQuestionAnswers, characteristicsMap);

      const requestPayload = {
        id_categorie: categoryId,
        nom_categorie: categoryName,
        equivalences: consolidated,
        texte_prompt: textePrompt,
        id_reponse_q1: q1AnswerCode,
        nom_reponse_q1: q1AnswerName,
      };

      console.log('[usePriceEstimation] Calling prix API with:', requestPayload);

      // 4. Appeler l'API prix
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
        nom_categorie: categoryName,
        texte_prompt: textePrompt,
        id_reponse_q1: q1AnswerCode,
        nom_reponse_q1: q1AnswerName,
        equivalences_count: consolidated.length,
      };

      // 5. Validation : pas de réponse → cas "aucun prix trouvé"
      if (!data.success || !data.reponse) {
        console.warn('[usePriceEstimation] API returned success=false or no reponse');
        trackDbEvent('pricing', 'estimation_empty', {
          request: trackingRequest,
          reason: 'api_returned_no_data',
          matching_message: data.matching?.message,
          duration_utilisateur: durationUtilisateur,
          time_elapsed: data.time_elapsed,
          message: data.message,
        }, categoryId);
        setPriceEstimation({ data: null, error: 'No price data' });
        return;
      }

      // Filet de sécurité : borne_basse === 0 → erreur backend silencieuse
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
          matching_message: data.matching?.message,
          duration_utilisateur: durationUtilisateur,
          time_elapsed: data.time_elapsed,
          message: data.message,
        }, categoryId);
        setPriceEstimation({ data: null, error: 'borne_basse is 0' });
        return;
      }

      // 6. Stocker dans le flow-store
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
    characteristicsMap,
    userQuestionAnswers,
    setPriceEstimation,
    trackDbEvent,
  ]);

  return { fetchPriceEstimation };
}
