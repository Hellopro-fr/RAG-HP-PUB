'use client';

/**
 * Enrichissement de l'objet `user` du dataLayer pour les visiteurs identifiés.
 *
 * Contexte : les pages conseils Next sont mises en cache (ISR), donc les données
 * par-visiteur (type, pays, service, id société…) ne peuvent pas être rendues côté
 * serveur dans le HTML. On les récupère côté client via le Route Handler BFF
 * `/api/gtm-user` (same-origin) : le navigateur l'appelle avec ses cookies .hellopro.fr,
 * et le serveur Next relaie vers l'API conseils (api/hp/view/gtm_user.php) avec le Bearer
 * token (gardé côté serveur, jamais exposé au navigateur). Le résultat est poussé dans le
 * dataLayer — consommé par la balise GA4 (user properties : user_login_state,
 * user_visitor_type, user_visitor_country, user_visitor_department, user_visitor_id).
 * Cf. ticket GTM.
 *
 * Anonyme (pas de cookie d'identité) → aucun appel : le `user` dégradé "unlogged" est déjà
 * poussé par GtmFooterScripts avant GTM. Résultat mis en cache en sessionStorage (1 appel/session).
 */

const MD5_EMPTY = 'd41d8cd98f00b204e9800998ecf8427e';
const CACHE_KEY = 'hp_gtm_user';
const ENDPOINT = '/api/gtm-user';

interface DataLayerWindow extends Window {
  dataLayer?: Array<Record<string, unknown>>;
}

function getCookie(name: string): string {
  if (typeof document === 'undefined') return '';
  const m = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
  return m ? decodeURIComponent(m[1]) : '';
}

/** Un cookie d'identité société est-il présent ? (sinon visiteur anonyme → pas d'appel). */
function hasIdentityCookie(): boolean {
  const email = getCookie('email_preremplissage_di');
  const idSoc = getCookie('id_societe');
  return (email !== '' && email !== MD5_EMPTY) || idSoc !== '';
}

function pushUser(user: Record<string, unknown>): void {
  const w = window as DataLayerWindow;
  w.dataLayer = w.dataLayer || [];
  w.dataLayer.push({ user });
}

export async function fetchAndPushUser(): Promise<void> {
  if (typeof window === 'undefined') return;

  /* Cache de session : un seul appel réseau par session. */
  try {
    const cached = window.sessionStorage.getItem(CACHE_KEY);
    if (cached) {
      pushUser(JSON.parse(cached) as Record<string, unknown>);
      return;
    }
  } catch {
    /* sessionStorage indisponible : on continue sans cache */
  }

  if (!hasIdentityCookie()) return; // visiteur anonyme → rien à enrichir

  try {
    const res = await fetch(ENDPOINT, {
      credentials: 'same-origin', // /api/gtm-user est same-origin (cookies .hellopro.fr envoyés)
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) return;
    const data = (await res.json()) as { user?: Record<string, unknown> };
    if (data?.user) {
      pushUser(data.user);
      try {
        window.sessionStorage.setItem(CACHE_KEY, JSON.stringify(data.user));
      } catch {
        /* ignore */
      }
    }
  } catch {
    /* endpoint/réseau indisponible (ex. dev sur IP) : on garde le user dégradé */
  }
}
