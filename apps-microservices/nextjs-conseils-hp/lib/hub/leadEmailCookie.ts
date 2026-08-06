'use client';

/**
 * Drapeau « ce navigateur a déjà soumis un lead » — cookie 30 jours.
 *
 * ⚠️ La valeur stockée est UNIQUEMENT `1`, JAMAIS l'e-mail. Un cookie est renvoyé
 * au serveur à chaque requête du sous-domaine ; y mettre l'e-mail l'exposerait
 * inutilement (RGPD + poids). L'e-mail n'est transmis QUE dans le corps de la
 * soumission `POST /api/demande`, jamais persisté côté navigateur.
 *
 * Effet « visiteur reconnu » (cookie présent) :
 *  - `GuideDownloadDialog` : va directement à l'écran de téléchargement ;
 *  - `LeadPopup` : ne s'affiche pas au scroll (on ne redérange pas) ;
 *  - `AssistantForm` : PAS de raccourci (l'étape e-mail reste toujours affichée).
 */
const COOKIE_NAME = 'hub_lead';
const MAX_AGE_SECONDS = 30 * 24 * 60 * 60; // 30 jours

/** true si ce navigateur a déjà soumis un lead (cookie drapeau présent). */
export function isLeadKnown(): boolean {
  if (typeof document === 'undefined') return false;
  return new RegExp(`(?:^|; )${COOKIE_NAME}=1(?:;|$)`).test(document.cookie);
}

/** Marque ce navigateur comme ayant déjà soumis un lead (valeur `1`, 30 jours). */
export function markLeadKnown(): void {
  if (typeof document === 'undefined') return;
  document.cookie = `${COOKIE_NAME}=1; path=/; max-age=${MAX_AGE_SECONDS}; samesite=lax`;
}
