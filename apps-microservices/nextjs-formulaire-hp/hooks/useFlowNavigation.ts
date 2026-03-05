'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback } from 'react';
import { FLOW_ORIGINAL_TOKEN_KEY } from '@/lib/stores/flow-store';

/**
 * Hook pour la navigation dans le flow avec conservation des paramètres GET.
 *
 * Les paramètres comme id_categorie ou token sont conservés lors des navigations
 * entre les étapes du funnel (/questionnaire -> /profile -> /selection).
 *
 * Fallback: Si le token n'est pas dans l'URL actuelle, on le recupere depuis sessionStorage.
 */
export function useFlowNavigation() {
  const router = useRouter();
  const searchParams = useSearchParams();

  /**
   * Construit une URL avec les paramètres GET actuels conservés.
   * Si le token n'est pas present dans l'URL, on le recupere depuis sessionStorage.
   */
  const buildUrl = useCallback((path: string) => {
    const params = new URLSearchParams(searchParams.toString());

    // Fallback: Si pas de token dans l'URL, recuperer depuis sessionStorage
    if (!params.has('token') && typeof window !== 'undefined') {
      const savedToken = sessionStorage.getItem(FLOW_ORIGINAL_TOKEN_KEY);
      if (savedToken) {
        params.set('token', savedToken);
      }
    }

    const paramsString = params.toString();
    return paramsString ? `${path}?${paramsString}` : path;
  }, [searchParams]);

  /**
   * Navigation vers une page du flow en conservant les paramètres GET
   */
  const navigateTo = useCallback((path: string) => {
    router.push(buildUrl(path));
  }, [router, buildUrl]);

  /**
   * Navigation vers le questionnaire
   */
  const goToQuestionnaire = useCallback(() => {
    navigateTo('/questionnaire');
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
    goToChoice,
    goToSomethingToAdd,
    goToContactSimple,
    goToConfirmation,
    buildUrl,
    searchParams,
  };
}
