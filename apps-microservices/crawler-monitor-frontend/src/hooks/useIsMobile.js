import { useEffect, useState } from 'react';

/**
 * Hook — retourne true si la largeur de la fenêtre est < 640px (breakpoint sm de Tailwind).
 * Réactif : met à jour dès que la fenêtre change de taille.
 */
export function useIsMobile() {
  const [is, setIs] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(max-width: 639px)').matches
  );

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mq = window.matchMedia('(max-width: 639px)');
    const fn = (e) => setIs(e.matches);
    mq.addEventListener('change', fn);
    return () => mq.removeEventListener('change', fn);
  }, []);

  return is;
}
