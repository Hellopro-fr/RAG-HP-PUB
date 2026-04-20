import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

/**
 * ScrollToTop — reset la position de scroll quand la route change vers une
 * PAGE différente.
 *
 * Ne pas fire sur /jobs/:id (qui réutilise le composant Overview pour afficher
 * un job sélectionné) : Overview gère lui-même le scrollIntoView vers le
 * détail. Sans cette exception, on avait une race où window.scrollTo(0,0)
 * écrasait le scrollIntoView → l'utilisateur restait figé sur Timeline/Replicas.
 *
 * Les sous-routes /jobs/:id/queue|dataset|replay utilisent d'autres composants
 * (QueuePage, DatasetPage, ReplayPage) et profitent bien du reset de scroll.
 */
export function ScrollToTop() {
  const { pathname } = useLocation();

  useEffect(() => {
    // /jobs/<id> pile (pas de /queue /dataset /replay derrière) → Overview est
    // déjà monté et fait son propre scrollIntoView, ne pas lutter contre.
    if (/^\/jobs\/[^/]+$/.test(pathname)) return;
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
  }, [pathname]);

  return null;
}
