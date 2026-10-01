/**
 * staleChunk.js -- detection et recuperation automatique des erreurs de chunks perimes.
 *
 * Apres un redeploiement, les utilisateurs qui ont encore l'ancienne version de
 * index.html en cache (ou en session SPA) tentent de charger des chunks avec les
 * anciens hashes. Le serveur renvoie les nouveaux hashes => import() echoue.
 *
 * Ce module detecte ce pattern et recharge la page une seule fois pour recuperer
 * le nouvel index.html avec les bons hashes. Un flag sessionStorage evite les
 * boucles de rechargement infinies.
 */

const STALE_CHUNK_PATTERNS = [
  /Failed to fetch dynamically imported module/i,
  /Importing a module script failed/i,
  /error loading dynamically imported module/i,
];

const RELOAD_FLAG_KEY = 'staleChunkReloadAttempted';

/**
 * Determine si une erreur correspond a un echec de chargement de chunk perime.
 * @param {unknown} error
 * @returns {boolean}
 */
export function isStaleChunkError(error) {
  if (!error) return false;
  if (error.name === 'ChunkLoadError') return true;
  const msg = error.message ?? String(error);
  return STALE_CHUNK_PATTERNS.some((re) => re.test(msg));
}

/**
 * Tente un rechargement automatique si l'erreur est un chunk perime et qu'on
 * n'a pas deja tente un rechargement dans cette session.
 *
 * @param {unknown} error
 * @returns {boolean} true si un rechargement a ete declenche, false sinon
 */
export function tryAutoReloadOnStaleChunk(error) {
  if (!isStaleChunkError(error)) return false;

  try {
    if (sessionStorage.getItem(RELOAD_FLAG_KEY) === '1') {
      // Deja tente -- ne pas boucler
      return false;
    }
    sessionStorage.setItem(RELOAD_FLAG_KEY, '1');
  } catch {
    // sessionStorage indisponible (navigation privee) -- on recharge quand meme
  }

  // Petit delai pour que le message console soit visible si DevTools est ouvert
  console.warn('[staleChunk] Chunk perime detecte apres deploiement -- rechargement automatique...');
  setTimeout(() => window.location.reload(), 100);
  return true;
}

/**
 * Indique si le flag de rechargement est deja positionne dans cette session.
 * Utilise par ErrorBoundary pour adapter le message affiche a l'utilisateur.
 * @returns {boolean}
 */
export function hasAlreadyTriedReload() {
  try {
    return sessionStorage.getItem(RELOAD_FLAG_KEY) === '1';
  } catch {
    return false;
  }
}

/**
 * Supprime le flag de rechargement -- a appeler une fois que l'application est
 * montee avec succes pour reinitialiser le compteur de tentatives.
 */
export function clearStaleChunkReloadFlag() {
  try {
    sessionStorage.removeItem(RELOAD_FLAG_KEY);
  } catch {
    // sessionStorage indisponible -- rien a faire
  }
}
