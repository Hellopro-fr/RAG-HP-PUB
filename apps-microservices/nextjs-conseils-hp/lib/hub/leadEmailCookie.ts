'use client';

/**
 * Mémorisation de l'e-mail du visiteur dans un cookie 30 jours, pour ne pas le
 * re-demander : un visiteur reconnu qui relance un téléchargement (ou termine le
 * questionnaire) passe directement à l'écran de remerciement.
 *
 * ⚠️ RGPD / perf : ce cookie (qui contient l'e-mail) est renvoyé au serveur à
 * CHAQUE requête sous `conseils.hellopro.fr`. Pour éviter cette transmission, on
 * pourrait utiliser `localStorage` (client-only) — choix « cookie » fait à la demande.
 */
const COOKIE_NAME = 'hub_lead_email';
const MAX_AGE_SECONDS = 30 * 24 * 60 * 60; // 30 jours
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** E-mail mémorisé, ou chaîne vide si absent / invalide. */
export function getRememberedEmail(): string {
  if (typeof document === 'undefined') return '';
  const match = document.cookie.match(new RegExp(`(?:^|; )${COOKIE_NAME}=([^;]*)`));
  const email = match ? decodeURIComponent(match[1]) : '';
  return EMAIL_RE.test(email) ? email : '';
}

/** Mémorise un e-mail valide (no-op si vide / invalide). */
export function rememberEmail(email: string): void {
  if (typeof document === 'undefined' || !EMAIL_RE.test(email)) return;
  document.cookie = `${COOKIE_NAME}=${encodeURIComponent(email)}; path=/; max-age=${MAX_AGE_SECONDS}; samesite=lax`;
}
