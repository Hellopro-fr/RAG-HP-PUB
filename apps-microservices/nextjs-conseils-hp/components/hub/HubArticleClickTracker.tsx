'use client';

import { useEffect } from 'react';
import { pushHubEvent, articleIdFromUrl } from '@/lib/analytics/hub';

/**
 * `hub_article_click` — clics du HUB vers les pages conseils.
 *
 * UN SEUL écouteur délégué sur `<main>`, et non un `onClick` par lien.
 *
 * Pourquoi c'est le bon choix ici : la page 1000 compte 20 liens sortants, répartis
 * dans `ThematiqueBloc`, `RessourcesGrid` et `GrandesEtapes` — tous des SERVER
 * COMPONENTS. Y poser un `onClick` les ferait basculer en composants client, donc
 * hydrater trois sections entières de contenu pour tracer un clic. Ici, un seul
 * composant client de quelques lignes couvre les 20 liens, et couvrira aussi ceux
 * qu'on ajoutera demain sans qu'on ait à y penser.
 *
 * `capture: true` : l'événement est intercepté à la descente, donc avant qu'un
 * handler intermédiaire ne puisse l'arrêter par `stopPropagation`.
 *
 * ⚠️ Aucune garantie de livraison sur navigation sortante. Le push part dans le
 * dataLayer juste avant que le navigateur ne quitte la page ; GTM peut ne pas
 * avoir le temps d'émettre la requête. C'est acceptable ici — on mesure une
 * tendance de maillage, pas une conversion — mais il ne faut pas bâtir de KPI
 * critique sur ce volume. Le rendre fiable demanderait `sendBeacon` côté tag GTM.
 */
const CONSEILS_HOST = 'conseils.hellopro.fr';

export function HubArticleClickTracker() {
  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      const link = target?.closest?.('a[href]') as HTMLAnchorElement | null;
      if (!link) return;

      const href = link.getAttribute('href') ?? '';
      if (!href.includes(CONSEILS_HOST)) return;

      // ⚠️ Exclut les téléchargements de fichier.
      //
      // `useAutoDownload` crée un `<a download>`, l'insère dans le document et
      // appelle `.click()` : ce clic synthétique remonte jusqu'ici comme un vrai.
      // Tant que le guide est servi en chemin relatif (`/…​.pdf`) le filtre d'hôte
      // suffit, mais dès que le PDF définitif sera servi depuis
      // `conseils.hellopro.fr`, chaque téléchargement produirait un
      // `hub_article_click` fantôme — attribué qui plus est à la section où se
      // trouve le dialog. Bug silencieux et pénible à diagnostiquer : on le coupe
      // maintenant, pendant qu'on y pense.
      if (link.hasAttribute('download')) return;
      if (/\.(pdf|zip|docx?|xlsx?|pptx?|csv)(?:[?#].*)?$/i.test(href)) return;

      // `source_block` = id de la section conteneur (`budget-financement`,
      // `nos-ressources`, `grandes-etapes`…). Déjà rendu par `HubSection`, donc
      // aucun attribut supplémentaire à poser dans le balisage.
      const section = link.closest('section[id]');

      pushHubEvent('hub_article_click', 'engagement', {
        article_url: href,
        article_id: articleIdFromUrl(href),
        source_block: section?.id,
      });
    };

    document.addEventListener('click', onClick, { capture: true });
    return () => document.removeEventListener('click', onClick, { capture: true });
  }, []);

  return null;
}
