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
   * Recupere le token depuis l'URL actuelle ou sessionStorage.
   * Le token peut etre dans le path (/questionnaire/TOKEN) ou en query param (?token=TOKEN)
   */
  const getToken = useCallback((): string | null => {
    // 1. Chercher dans les query params
    const tokenFromParams = searchParams.get('token');
    if (tokenFromParams) return tokenFromParams;

    // 2. Chercher dans le path (dernier segment qui ressemble a un token base64)
    if (typeof window !== 'undefined') {
      const pathSegments = window.location.pathname.split('/').filter(Boolean);
      // Le token est generalement le dernier segment apres la page (ex: /formulaire/questionnaire/TOKEN)
      const lastSegment = pathSegments[pathSegments.length - 1];
      // Un token base64 contient des caracteres alphanumeriques, +, /, -, _
      if (lastSegment && lastSegment.length > 20 && /^[A-Za-z0-9+/\-_=]+$/.test(lastSegment)) {
        return lastSegment;
      }
    }

    // 3. Fallback: sessionStorage
    if (typeof window !== 'undefined') {
      return sessionStorage.getItem(FLOW_ORIGINAL_TOKEN_KEY);
    }

    return null;
  }, [searchParams]);

  /**
   * Construit une URL avec le token dans le path.
   * Format: /page/TOKEN (ex: /questionnaire/abc123)
   */
  const buildUrl = useCallback((path: string) => {
    const token = getToken();

    // Construire l'URL avec le token dans le path
    if (token) {
      return `${path}/${token}`;
    }

    return path;
  }, [getToken]);

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
