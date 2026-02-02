'use client';

import { useEffect, useRef } from 'react';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import { useFlowStore } from '@/lib/stores/flow-store';
import { resetTrackingState } from '@/lib/analytics';

/**
 * Composant qui gère le reset du flow lors d'un rechargement de page (F5).
 *
 * Comportement :
 * - F5 sur /questionnaire : reset et reste sur /questionnaire (avec paramètres GET)
 * - F5 sur /profile, /selection, etc. : reset et redirige vers /questionnaire (avec paramètres GET)
 * - Navigation SPA (router.push) : pas de reset
 *
 * Les paramètres GET (id_categorie, token, etc.) sont conservés lors de la redirection.
 * Cela garantit que l'utilisateur recommence toujours le funnel depuis le début
 * après un rechargement, avec des données de tracking cohérentes.
 */
export default function FlowStorageReset() {
  const reset = useFlowStore((state) => state.reset);
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const hasChecked = useRef(false);

  useEffect(() => {
    // Ne s'exécuter qu'une seule fois par montage du composant
    if (hasChecked.current) return;
    hasChecked.current = true;

    if (typeof window === 'undefined') return;

    // Détecter le type de navigation
    let navigationType: string | undefined;

    // Méthode moderne: PerformanceNavigationTiming
    const navEntries = performance.getEntriesByType('navigation') as PerformanceNavigationTiming[];
    if (navEntries.length > 0) {
      navigationType = navEntries[0].type;
    }

    const hasInitialized = sessionStorage.getItem('flow-initialized') === 'true';
    const isQuestionnairePage = pathname === '/questionnaire' || pathname?.startsWith('/formulaire');

    // Construire l'URL de redirection avec les paramètres GET conservés
    const buildRedirectUrl = () => {
      const params = searchParams.toString();
      return params ? `/questionnaire?${params}` : '/questionnaire';
    };

    if (!hasInitialized) {
      // Première visite : reset complet
      sessionStorage.removeItem('flow-storage');
      reset();
      resetTrackingState();
      sessionStorage.setItem('flow-initialized', 'true');

      // Si pas sur questionnaire, rediriger avec les paramètres GET
      if (!isQuestionnairePage) {
        router.replace(buildRedirectUrl());
      }
    } else if (navigationType === 'reload') {
      // F5/Reload : reset complet et rediriger vers questionnaire
      sessionStorage.removeItem('flow-storage');
      reset();
      resetTrackingState();

      // Rediriger vers questionnaire si on n'y est pas déjà (avec paramètres GET)
      if (!isQuestionnairePage) {
        router.replace(buildRedirectUrl());
      }
    }
  }, [reset, router, pathname, searchParams]);

  return null;
}
