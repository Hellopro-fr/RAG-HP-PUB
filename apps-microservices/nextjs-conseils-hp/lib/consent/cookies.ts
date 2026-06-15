'use client';

/**
 * Helpers de gestion du consentement RGPD HelloPro — RÉPLIQUE EXACTE du legacy.
 *
 * ⚠️ Les noms de cookies, le domaine (.hellopro.fr), les formats de valeur et les
 * durées doivent rester STRICTEMENT identiques au legacy, sinon le consentement
 * n'est plus partagé entre www.hellopro.fr / conseils.hellopro.fr (cf. ticket GTM).
 *
 * Cookies :
 *   - hp_consent        : choix global  "1"=refus, "2"=perso/essentiel, "3"=tout accepté
 *   - hp_consent_perso  : détail si "2"  "<statistics>,<personalization>" (0/1)
 *   - user_consent_hp   : état Consent Mode v2 (chaîne "clé:valeur|…")
 *
 * Référence legacy : js_general_v1 (stocker_consentement, gest_cookie_rgpd) +
 * tag_google_tag_manager_footer / cookie_consentement.php.
 */

const COOKIE_DOMAIN = '.hellopro.fr';

export type ConsentValue = 'granted' | 'denied';

export interface ConsentStateV2 {
  ad_storage: ConsentValue;
  analytics_storage: ConsentValue;
  ad_user_data: ConsentValue;
  ad_personalization: ConsentValue;
}

/* ───────────────────────── Lecture ───────────────────────── */

export function getCookie(name: string): string {
  if (typeof document === 'undefined') return '';
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
  return match ? decodeURIComponent(match[1]) : '';
}

/* ───────────────────────── Écriture ───────────────────────── */

/**
 * Équivalent de `gest_cookie_rgpd` legacy : cookie domaine .hellopro.fr, SameSite=Strict.
 * @param days durée en jours
 */
export function setRgpdCookie(name: string, value: string, days: number): void {
  if (typeof document === 'undefined') return;
  let expires = '';
  if (days) {
    const date = new Date();
    date.setTime(date.getTime() + days * 24 * 60 * 60 * 1000);
    expires = '; expires=' + date.toUTCString();
  }
  document.cookie =
    name + '=' + value + expires + ';path=/;domain=' + COOKIE_DOMAIN + ';Secure;SameSite=Strict';
}

/**
 * Équivalent de `stocker_consentement` legacy : écrit `user_consent_hp` (Consent Mode v2).
 * max-age = 1 an, sauf si analytics refusé → 30 jours + flag `analytics_denied_set:1`.
 */
export function storeConsentV2(c: ConsentStateV2): void {
  if (typeof document === 'undefined') return;
  let maxAge = '31536000'; // 1 an
  let consentValue =
    'ad_storage:' + c.ad_storage +
    '|analytics_storage:' + c.analytics_storage +
    '|ad_user_data:' + c.ad_user_data +
    '|ad_personalization:' + c.ad_personalization;
  if (c.analytics_storage === 'denied') {
    maxAge = '2592000'; // 30 jours
    consentValue += '|analytics_denied_set:1';
  }
  document.cookie =
    'user_consent_hp=' + encodeURIComponent(consentValue) +
    '; path=/; domain=' + COOKIE_DOMAIN + '; max-age=' + maxAge + '; Secure; SameSite=Lax';
}

/* ───────────────────────── Consent Mode (dataLayer) ───────────────────────── */

/**
 * Pousse une commande gtag dans le dataLayer (équivalent de `gtag('consent','update',{…})`).
 * GTM/gtag.js interprète une commande poussée comme tableau de la même façon que l'objet
 * `arguments` du snippet officiel (array-like : mêmes index + length).
 */
export function gtagConsent(...args: unknown[]): void {
  const w = window as Window & { dataLayer?: unknown[] };
  w.dataLayer = w.dataLayer || [];
  w.dataLayer.push(args);
}

export function pushConsentUpdate(c: ConsentStateV2): void {
  gtagConsent('consent', 'update', c);
}

/* ───────────────────────── Audit serveur (pixel legacy) ───────────────────────── */

/**
 * Déclenche le pixel d'audit RGPD vers cookie_consentement.php (legacy, servi sous
 * conseils.hellopro.fr via le reverse proxy) : journalise en base `cookie_rgpd`
 * et pose les cookies serveur hp_consent / hp_consent_perso.
 *
 * @param consentement  "1" | "2" | "3"
 * @param personnalisation  "<stats>,<perso>" ou ""
 */
export function fireConsentAuditPixel(consentement: string, personnalisation = ''): void {
  if (typeof window === 'undefined') return;
  let requestUri = window.location.pathname + window.location.search;
  requestUri = requestUri.replace(/\.html$/, '');
  const url =
    'https://' + window.location.hostname +
    '/hellopro_fr/ajax/cookie_consentement.php' +
    '?consentement=' + encodeURIComponent(consentement) +
    '&personnalisation=' + encodeURIComponent(personnalisation) +
    '&page=' + encodeURIComponent(requestUri);
  const img = new Image();
  img.src = url;
}
