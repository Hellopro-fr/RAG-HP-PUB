'use client';

import { useSearchParams } from 'next/navigation';
import { useCallback } from 'react';

// Base path configuré dans next.config.js (pour le proxy Apache)
const BASE_PATH = '/formulaire';

/**
 * Hook pour la navigation dans le flow avec conservation des paramètres GET.
 *
 * Les paramètres comme id_categorie ou token sont conservés lors des navigations
 * entre les étapes du funnel (/questionnaire -> /profile -> /selection).
 *
 * NOTE: On utilise window.location.href au lieu de router.push() pour que
 * les navigations passent par le proxy Apache et que l'URL reste sur www.hellopro.fr
 */
export function useFlowNavigation() {
  const searchParams = useSearchParams();

  /**
   * Construit une URL avec les paramètres GET actuels conservés
   */
  const buildUrl = useCallback((path: string) => {
    const params = searchParams.toString();
    return params ? `${path}?${params}` : path;
  }, [searchParams]);

  /**
   * Navigation vers une page du flow en conservant les paramètres GET.
   * Utilise window.location.href pour passer par le proxy Apache.
   */
  const navigateTo = useCallback((path: string) => {
    const url = buildUrl(path);
    // Navigation "hard" pour passer par le proxy Apache
    // Cela garantit que l'URL reste sur le domaine du proxy (www.hellopro.fr)
    window.location.href = `${BASE_PATH}${url}`;
  }, [buildUrl]);

  /**
   * Navigation vers le questionnaire
   */
  const goToQuestionnaire = useCallback(() => {
    navigateTo('/questionnaire');
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
