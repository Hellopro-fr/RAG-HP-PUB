import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

/**
 * ScrollToTop — remet le scroll en haut à chaque changement de route.
 *
 * Le conteneur scrollable est le <main> de l'AppShell (`flex-1 overflow-y-auto`),
 * pas la fenêtre : `window.scrollTo` ne faisait donc strictement rien et on
 * arrivait sur les pages au milieu du contenu précédent.
 *
 * ORDRE DE MONTAGE — NE PAS DÉPLACER. Ce composant doit rester monté AVANT
 * l'arbre des pages dans l'AppShell : React exécute les effets dans l'ordre du
 * document, donc ce remise-à-zéro du scroll passe avant le `scrollIntoView` par
 * lequel Overview ramène le job sélectionné dans le viewport. Monté après, il
 * écraserait ce cadrage et l'opérateur atterrirait en haut de la liste au lieu
 * du job qu'il vient d'ouvrir.
 */
export function ScrollToTop() {
  const { pathname } = useLocation();

  useEffect(() => {
    const main = typeof document !== 'undefined'
      ? document.querySelector('main')
      : null;
    if (main) {
      main.scrollTo({ top: 0, left: 0, behavior: 'instant' });
      return;
    }
    window.scrollTo?.({ top: 0, left: 0, behavior: 'instant' });
  }, [pathname]);

  return null;
}
