'use client';

/**
 * Tracking « page vue » DB pour les pages conseils servies par Next.js.
 *
 * Contexte : le suivi de session/landing est porté par le legacy PHP, hébergé sur
 * www.hellopro.fr (PAS sous conseils.hellopro.fr — le host Next ne sert aucun PHP).
 * Côté Next, on émet une « page vue » à chaque page conseil affichée, vers l'endpoint PHP
 * `ajax_trace_session.php` (upsert tracking_session + insert tracking_page_vue). Le marquage
 * en conversion est fait côté lead par demande_info_insertion.php (lit le même session_id),
 * donc rien à faire ici pour le lead.
 *
 * Pourquoi côté client : les pages conseils sont mises en cache (ISR), l'id de session
 * vit dans les cookies du navigateur (.hellopro.fr) et n'est pas disponible au rendu serveur.
 *
 * ⚠️ Cross-origin (conseils|preview → www.hellopro.fr) : le corps part en `text/plain`
 * (type CORS-safelisted → pas de préflight, que sendBeacon ne sait pas faire ; le PHP lit
 * le corps brut via php://input). `credentials:'include'` joint PHPSESSID (.hellopro.fr,
 * same-site en prod).
 */

/**
 * URL absolue de l'endpoint PHP. Le PHP vit sur www.hellopro.fr (déployé FTP, NE PAS
 * modifier). Surchargeable par build via NEXT_PUBLIC_TRACE_SESSION_URL (ex. staging).
 */
const TRACE_SESSION_ENDPOINT =
  process.env.NEXT_PUBLIC_TRACE_SESSION_URL ||
  'https://www.hellopro.fr/hellopro_fr/ajax/ajax_trace_session.php';

function getCookie(name: string): string {
  if (typeof document === 'undefined') return '';
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
  return match ? decodeURIComponent(match[1]) : '';
}

/**
 * Identifiant de session lisible côté client, dans l'ordre imposé par le legacy :
 *   tracking_landing_session_id  →  sinon  PHPSESSID.
 *
 * ⚠️ `PHPSESSID` est généralement `HttpOnly` → illisible via `document.cookie` : cette
 * fonction renverra alors `''`. Ce n'est PAS bloquant : la requête de page vue partant
 * en same-origin, le navigateur joint automatiquement `PHPSESSID` (même HttpOnly), et le
 * PHP `ajax_trace_session.php` résout l'id « POST puis cookies ». On ne renseigne donc le
 * champ POST `session_id` que lorsqu'un id est lisible côté client.
 */
export function getTrackingSessionId(): string {
  return getCookie('tracking_landing_session_id') || getCookie('PHPSESSID');
}

/**
 * Génère 32 caractères hexadécimaux (16 octets via crypto.getRandomValues).
 * Format imposé : uniquement [0-9a-f], pas de tirets ni d'underscores.
 * Le backend strip tout [^a-zA-Z0-9] (demande_info_insertion.php) — un tiret ou
 * underscore raccourcirait silencieusement l'id et casserait la corrélation page_view/lead.
 */
function generateSessionId(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

/** Réplique exacte de la sanitisation côté lead : ne garde que [a-zA-Z0-9]. */
function sanitizeSessionId(id: string): string {
  return id.replace(/[^a-zA-Z0-9]/g, '');
}

/**
 * Persiste `tracking_landing_session_id` afin que le `page_view` (parent conseils.hellopro.fr)
 * ET le lead (iframe www.hellopro.fr → demande_info_insertion.php) partagent le même id.
 *
 * `domain=.hellopro.fr` → le cookie est joint aux requêtes de l'iframe (same-site) et relu par
 * `$_COOKIE['tracking_landing_session_id']` (prioritaire sur PHPSESSID dans la chaîne du lead).
 * `Secure` seulement en HTTPS (sinon le cookie serait refusé sur un host de test HTTP). Hors
 * `*.hellopro.fr`, on pose un cookie host-only (le partage cross-sous-domaine n'a alors pas lieu).
 */
function setLandingSessionCookie(value: string): void {
  if (typeof document === 'undefined') return;
  const host = window.location.hostname;
  const domainAttr =
    host === 'hellopro.fr' || host.endsWith('.hellopro.fr') ? '; domain=.hellopro.fr' : '';
  const secureAttr = window.location.protocol === 'https:' ? '; Secure' : '';
  const oneYear = 60 * 60 * 24 * 365;
  document.cookie =
    'tracking_landing_session_id=' +
    encodeURIComponent(value) +
    '; path=/' +
    domainAttr +
    '; max-age=' +
    oneYear +
    '; SameSite=Lax' +
    secureAttr;
}

/**
 * Id de session à envoyer : cookie existant (`tracking_landing_session_id` → `PHPSESSID`) ou,
 * à défaut, un id généré et persisté. Indispensable car `ajax_trace_session.php` `exit` si
 * `session_id` est vide et ne consulte jamais les cookies serveur.
 */
export function resolveTrackingSessionId(): string {
  // Sanitisé pour matcher exactement l'id que le lead reconstruira depuis le même cookie.
  const existing = sanitizeSessionId(getTrackingSessionId());
  if (existing) return existing;
  const generated = generateSessionId();
  setLandingSessionCookie(generated);
  return generated;
}

/**
 * Horodatage au format MySQL DATETIME `Y-m-d H:i:s` (heure locale du navigateur).
 * Indispensable : le PHP insère cette valeur telle quelle dans des colonnes DATETIME —
 * un ISO 8601 (`...T...Z`, millisecondes) y serait rejeté/mis à zéro.
 */
function formatMysqlDatetime(d: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  );
}

/**
 * Envoie un payload de tracking à l'endpoint PHP.
 * Transport : navigator.sendBeacon (survit au déchargement de page), avec repli sur
 * fetch keepalive si sendBeacon est indisponible ou refuse de mettre en file la requête.
 * text/plain : type CORS-safelisted → envoi cross-origin sans préflight (cf. en-tête du fichier ;
 * le PHP lit le corps brut via php://input).
 */
function postTrace(payload: Record<string, unknown>): void {
  const body = JSON.stringify(payload);

  if (typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function') {
    const blob = new Blob([body], { type: 'text/plain;charset=UTF-8' });
    if (navigator.sendBeacon(TRACE_SESSION_ENDPOINT, blob)) return;
  }

  // Repli : fetch keepalive (survit au déchargement). mode:'no-cors' = envoi cross-origin
  // sans préflight (réponse opaque, non lue) ; credentials:'include' joint PHPSESSID.
  void fetch(TRACE_SESSION_ENDPOINT, {
    method: 'POST',
    body,
    keepalive: true,
    mode: 'no-cors',
    credentials: 'include',
  }).catch(() => {
    /* endpoint/réseau indisponible : on ignore silencieusement */
  });
}

/**
 * Émet une « page vue » (action `page_view`) — à CHAQUE page conseil affichée.
 * `session_id` est toujours non vide (résolu ou généré) : le PHP `exit` sinon.
 */
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
