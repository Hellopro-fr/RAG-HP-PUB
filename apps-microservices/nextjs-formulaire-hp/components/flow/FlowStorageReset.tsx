'use client';

import { useEffect, useRef } from 'react';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import { useFlowStore, FLOW_NEEDS_REDIRECT_KEY } from '@/lib/stores/flow-store';
import { resetTrackingState } from '@/lib/analytics';

/**
 * Composant qui gère la redirection après reset du flow.
 *
 * Le reset du storage est géré par createReloadAwareStorage dans flow-store.ts
 * qui s'exécute AVANT l'hydratation de Zustand.
 *
 * Ce composant vérifie le flag FLOW_NEEDS_REDIRECT_KEY défini par flow-store.ts
 * et redirige vers la page du questionnaire si nécessaire.
 *
 * Règles :
 * 1. F5 / Actualiser → Redirection vers / (questionnaire)
 * 2. Modification manuelle de l'URL → Redirection vers / (questionnaire)
 * 3. Première visite → Pas de redirection (on reste sur la page demandée)
 * 4. Navigation SPA (router.push) → Pas de redirection
 */
export default function FlowStorageReset() {
  const reset = useFlowStore((state) => state.reset);
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const hasChecked = useRef(false);

  useEffect(() => {
    // Ne s'exécuter qu'une seule fois par session de composant
    if (hasChecked.current) return;
    hasChecked.current = true;

    if (typeof window === 'undefined') return;

    // Vérifier si flow-store.ts a défini le flag de redirection
    const needsRedirect = sessionStorage.getItem(FLOW_NEEDS_REDIRECT_KEY) === 'true';

    // Nettoyer le flag immédiatement pour éviter des redirections en boucle
    sessionStorage.removeItem(FLOW_NEEDS_REDIRECT_KEY);

    if (!needsRedirect) {
      console.log('[FlowStorageReset] No redirect needed');
      return;
    }

    // Le store a déjà été reset par createReloadAwareStorage
    // On reset aussi le tracking ici
    reset();
    resetTrackingState();

    // Le questionnaire est sur la racine "/" (avec basePath /formulaire → /formulaire/)
    const isQuestionnairePage = pathname === '/' || pathname === '';

    // Construire l'URL de redirection avec les paramètres GET conservés
    const buildRedirectUrl = () => {
      const params = searchParams.toString();
      return params ? `/?${params}` : '/';
    };

    // Rediriger vers questionnaire si pas déjà dessus
    if (!isQuestionnairePage) {
      console.log('[FlowStorageReset] Redirecting to questionnaire from', pathname);
      router.replace(buildRedirectUrl());
    } else {
      console.log('[FlowStorageReset] Already on questionnaire, no redirect needed');
    }
  }, [reset, router, pathname, searchParams]);

  return null;
}
