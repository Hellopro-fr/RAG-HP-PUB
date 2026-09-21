'use client';

import { useEffect } from 'react';
import { openAssistantDialog } from '@/lib/hub/assistantDialogEvent';
import { openGuideDialog } from '@/lib/hub/guideDialogEvent';
import { getCookie, CONSENT_RESOLVED_EVENT } from '@/lib/consent/cookies';

/**
 * Ouverture par DEEP-LINK depuis un site externe.
 *
 * Une bannière/bouton hébergé ailleurs pointe vers la page HUB avec `?hub_cta=…` :
 *  - `?hub_cta=projet` → ouvre le QUESTIONNAIRE (`AssistantForm`) directement sur
 *    sa 1re question (l'opener fait `reset()` → step 0 + `forceOpen`) ;
 *  - `?hub_cta=guide`  → ouvre la POP-UP GUIDE (`GuideDownloadDialog`).
 *
 * On réutilise les openers existants → la CONDITION E-MAIL est préservée : le
 * guide saute au téléchargement si le drapeau « lead connu » (par page) est posé,
 * sinon il demande l'e-mail ; le questionnaire affiche toujours l'étape e-mail.
 *
 * ⚠️ ATTENDRE LE CONSENTEMENT. Le bandeau RGPD (`CookieConsent`) s'affiche à la
 * 1re visite comme un overlay MODAL (`z-index:3001`). Ouvrir notre dialog Radix
 * par-dessus le rend inerte : Radix pose `pointer-events:none` sur tout ce qui est
 * hors du dialog, donc les boutons du bandeau cookies ne répondent plus et il ne
 * se ferme jamais. On n'ouvre donc QU'APRÈS résolution du consentement — ce qui
 * est aussi le bon ordre RGPD. Le signal d'attente est l'ÉVÉNEMENT
 * `CONSENT_RESOLVED_EVENT` (émis par `CookieConsent` à la fermeture) et NON le
 * cookie `hp_consent` : ce dernier, écrit en `domain=.hellopro.fr;Secure`, n'est
 * pas relisible hors de ce domaine — le sonder échouait en environnement de test.
 *
 * Ne rend rien. Monté une seule fois par `HubTemplate`.
 */
const PARAM = 'hub_cta';
const CONSENT_COOKIE = 'hp_consent';

export function HubDeepLink() {
  useEffect(() => {
    let action: string | null = null;
    try {
      action = new URLSearchParams(window.location.search).get(PARAM);
    } catch {
      return;
    }
    if (action !== 'projet' && action !== 'guide') return;

    // Nettoie l'URL AVANT d'ouvrir : un rechargement, un retour arrière ou un
    // partage du lien ne doit pas ré-ouvrir le dialog, et l'URL publique reste
    // propre. `replaceState` ne recharge pas la page (pas de perte d'état React).
    try {
      const url = new URL(window.location.href);
      url.searchParams.delete(PARAM);
      window.history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`);
    } catch {
      /* non bloquant : au pire le param reste dans l'URL */
    }

    // Différé d'un tick : garantit que le bandeau de consentement est bien démonté
    // (pointer-events rendus) et que les écouteurs des dialogs (AssistantForm,
    // HubOverlays) sont attachés avant qu'on dispatche l'événement d'ouverture.
    const fire = () => {
      window.setTimeout(() => {
        if (action === 'projet') openAssistantDialog('external_projet');
        else openGuideDialog('external_guide');
      }, 0);
    };

    // Le bandeau RGPD s'affiche exactement quand `hp_consent` est absent (même
    // condition que `CookieConsent`). S'il est présent, aucun bandeau ne s'affiche
    // → on ouvre tout de suite. Sinon, on attend que l'utilisateur tranche :
    // l'ÉVÉNEMENT (et non le cookie) est le signal fiable — le cookie est écrit en
    // `domain=.hellopro.fr;Secure`, illisible hors de ce domaine.
    let consentKnown = false;
    try {
      consentKnown = getCookie(CONSENT_COOKIE) !== '';
    } catch {
      consentKnown = false;
    }

    if (consentKnown) {
      fire();
      return;
    }

    const onResolved = () => fire();
    window.addEventListener(CONSENT_RESOLVED_EVENT, onResolved, { once: true });
    return () => window.removeEventListener(CONSENT_RESOLVED_EVENT, onResolved);
  }, []);

  return null;
}
