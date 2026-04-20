import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

/**
 * ScrollToTop — reset la position de scroll quand la route change.
 *
 * React Router ne restaure pas le scroll par défaut (contrairement aux navigateurs
 * natifs sur full-reload). Sans ça, naviguer de Overview (scrollé en bas sur un
 * job sélectionné) vers /jobs/:id/queue arrive "au milieu" de la Queue.
 *
 * On écoute `pathname` uniquement : changer uniquement `search` ou `hash` ne
 * doit pas faire sauter l'utilisateur au top (pagination côté Queue, etc).
 */
export function ScrollToTop() {
  const { pathname } = useLocation();

  useEffect(() => {
    // instant — pas de `smooth` ici, la page change, pas besoin d'animation
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
  }, [pathname]);

  return null;
}
