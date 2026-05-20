'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback } from 'react';
import { FLOW_ORIGINAL_TOKEN_KEY } from '@/lib/stores/flow-store';

/**
 * Hook pour la navigation dans le flow avec conservation des paramètres GET.
 *
 * Les paramètres comme id_categorie ou token sont conservés lors des navigations
 * entre les étapes du funnel (/questionnaire -> /profile -> /selection).
 */
export function useFlowNavigation() {
  const router = useRouter();
  const searchParams = useSearchParams();

  /**
   * Construit une URL avec les paramètres GET actuels conservés
   */
  const buildUrl = useCallback((path: string) => {
    const params = searchParams.toString();
    return params ? `${path}?${params}` : path;
  }, [searchParams]);

  /**
   * Navigation vers une page du flow en conservant les paramètres GET
   */
  const navigateTo = useCallback((path: string) => {
    router.push(buildUrl(path));
  }, [router, buildUrl]);

  /**
   * Navigation vers le questionnaire.
   *
   * Le token de catégorie est transporté dans le PATH (`/questionnaire/<TOKEN>`),
   * pas en query string — donc `navigateTo('/questionnaire')` produirait une 404
   * (route dynamique [token] manquante). On relit le token sauvegardé dans
   * sessionStorage (posé par questionnaire-client.tsx au premier rendu) pour
   * reconstruire l'URL complète. Fallback sans token uniquement si aucun token
   * n'a été enregistré (parcours direct hors funnel — rare).
   */
  const goToQuestionnaire = useCallback(() => {
    const originalToken = typeof window !== 'undefined'
      ? sessionStorage.getItem(FLOW_ORIGINAL_TOKEN_KEY)
      : null;
    navigateTo(originalToken ? `/questionnaire/${originalToken}` : '/questionnaire');
  }, [navigateTo]);

  /**
   * Navigation vers la zone géographique
   */
  const goToGeoZone = useCallback(() => {
    navigateTo('/geo-zone');
  }, [navigateTo]);

  /**
   * Navigation vers le profil
   */
  const goToProfile = useCallback(() => {
    navigateTo('/profile');
  }, [navigateTo]);

  /**
   * Navigation vers la sélection
   */
  const goToSelection = useCallback(() => {
    navigateTo('/selection');
  }, [navigateTo]);

  /**
   * Navigation vers la page budget (intercalée entre /questionnaire et /selection)
   */
  const goToBudget = useCallback(() => {
    navigateTo('/budget');
  }, [navigateTo]);

  /**
   * Navigation vers le choix
   */
  const goToChoice = useCallback(() => {
    navigateTo('/choice');
  }, [navigateTo]);

  /**
   * Navigation vers "quelque chose à ajouter"
   */
  const goToSomethingToAdd = useCallback(() => {
    navigateTo('/something-to-add');
  }, [navigateTo]);

  /**
   * Navigation vers le contact simple
   */
  const goToContactSimple = useCallback(() => {
    navigateTo('/contact-simple');
  }, [navigateTo]);

  /**
   * Navigation vers la confirmation
   */
  const goToConfirmation = useCallback(() => {
    navigateTo('/confirmation');
  }, [navigateTo]);

  return {
    navigateTo,
    goToQuestionnaire,
    goToGeoZone,
    goToProfile,
    goToSelection,
    goToBudget,
    goToChoice,
    goToSomethingToAdd,
    goToContactSimple,
    goToConfirmation,
    buildUrl,
    searchParams,
  };
}
