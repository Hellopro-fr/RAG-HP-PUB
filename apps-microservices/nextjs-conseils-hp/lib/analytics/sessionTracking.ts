'use client';

/**
 * Tracking « page vue » DB pour les pages conseils servies par Next.js.
 *
 * Deux scénarios de session :
 *
 * 1. Session débutant sur PHP (www.hellopro.fr) → tracking_landing_session_id déjà posé
 *    par le legacy → on le lit et on l'utilise tel quel.
 *
 * 2. Session débutant directement sur Next.js (conseils.hellopro.fr) →
 *    tracking_landing_session_id vide → on crée next_tracking_id (32 hex,
 *    domain=.hellopro.fr). Ce cookie est inconnu de js_general_v1.js → jamais écrasé.
 *    Il est passé à l'iframe (tracking_session_id GET param → champ caché → POST priority 1
 *    dans demande_info_insertion.php) pour lier page_vue et lead.
 *
 * ⚠️ Cross-origin (conseils → www.hellopro.fr) : corps en `text/plain` (CORS-safelisted,
 * pas de préflight) ; le PHP lit via php://input.
 */

const TRACE_SESSION_ENDPOINT =
  process.env.NEXT_PUBLIC_TRACE_SESSION_URL ||
  'https://www.hellopro.fr/hellopro_fr/ajax/ajax_trace_session.php';

/** Nom du cookie dédié aux sessions débutant sur Next.js. */
const NEXT_TRACKING_COOKIE = 'next_tracking_id';

function getCookie(name: string): string {
  if (typeof document === 'undefined') return '';
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
  return match ? decodeURIComponent(match[1]) : '';
}

/** Réplique la sanitisation PHP : `preg_replace('/[^a-zA-Z0-9]/', '', ...)`. */
function sanitizeSessionId(id: string): string {
  return id.replace(/[^a-zA-Z0-9]/g, '');
}

/** Génère 32 caractères hexadécimaux (16 octets). */
function generateSessionId(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Pose next_tracking_id (domain=.hellopro.fr, 1 an, SameSite=Lax).
 * Hors *.hellopro.fr (test local) : cookie host-only.
 */
function setNextTrackingCookie(value: string): void {
  if (typeof document === 'undefined') return;
  const host = window.location.hostname;
  const domainAttr =
    host === 'hellopro.fr' || host.endsWith('.hellopro.fr') ? '; domain=.hellopro.fr' : '';
  const secureAttr = window.location.protocol === 'https:' ? '; Secure' : '';
  const oneYear = 60 * 60 * 24 * 365;
  document.cookie =
    NEXT_TRACKING_COOKIE + '=' +
    encodeURIComponent(value) +
    '; path=/' +
    domainAttr +
    '; max-age=' + oneYear +
    '; SameSite=Lax' +
    secureAttr;
}

/**
 * Résout l'id de session à utiliser pour le tracking :
 *
 * 1. tracking_landing_session_id existe → source PHP autoritaire → on l'utilise.
 * 2. sinon PHPSESSID visible → on (ré)écrit next_tracking_id avec sa valeur → on l'utilise.
 *    PHPSESSID étant quasi toujours présent sur la page Next, next_tracking_id reste aligné
 *    sur la session PHP courante → session unifiée Next ↔ PHP.
 * 3. sinon next_tracking_id existant (cas sans PHPSESSID) → on le réutilise.
 * 4. sinon → on génère un id 32 hex et on le persiste.
 */
export function resolveTrackingSessionId(): string {
  // 1. tracking_landing_session_id → source PHP autoritaire
  const landingId = sanitizeSessionId(getCookie('tracking_landing_session_id'));
  if (landingId) return landingId;

  // 2. PHPSESSID → (ré)écrit next_tracking_id avec sa valeur (prioritaire)
  const phpId = sanitizeSessionId(getCookie('PHPSESSID'));
  if (phpId) {
    setNextTrackingCookie(phpId);
    return phpId;
  }

  // 3. next_tracking_id déjà créé (aucun PHPSESSID) → réutiliser
  const nextId = sanitizeSessionId(getCookie(NEXT_TRACKING_COOKIE));
  if (nextId) return nextId;

  // 4. Aucun cookie → générer et persister
  const generated = generateSessionId();
  setNextTrackingCookie(generated);
  return generated;
}

function formatMysqlDatetime(d: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  );
}

function postTrace(payload: Record<string, unknown>): void {
  const body = JSON.stringify(payload);

  if (typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function') {
    const blob = new Blob([body], { type: 'text/plain;charset=UTF-8' });
    if (navigator.sendBeacon(TRACE_SESSION_ENDPOINT, blob)) return;
  }

  void fetch(TRACE_SESSION_ENDPOINT, {
    method: 'POST',
    body,
    keepalive: true,
    mode: 'no-cors',
    credentials: 'include',
  }).catch(() => {});
}

export function sendPageView(): void {
  if (typeof window === 'undefined') return;

  postTrace({
    action: 'page_view',
    session_id: resolveTrackingSessionId(),
    url: window.location.href,
    referrer: document.referrer || '',
    host: window.location.hostname,
    datetime: formatMysqlDatetime(),
  });
}
