/**
 * CARTE ENTIÈREMENT CLIQUABLE — source unique.
 *
 * Le pseudo-élément appartient au `<a>` et couvre la boîte de la carte : un seul
 * lien dans le DOM, aucun `onClick`, donc les composants de cartes restent des
 * SERVER COMPONENTS. Un handler les ferait basculer côté client et hydraterait
 * tout le contenu des blocs — soit une quarantaine de cartes sur une page HUB —
 * pour ne gérer qu'un clic que le navigateur sait déjà traiter seul.
 *
 * Trois conséquences à connaître :
 *
 * - `hub_article_click` continue de fonctionner sans rien changer. L'écouteur
 *   délégué de `HubArticleClickTracker` fait `target.closest('a[href]')`, et la
 *   cible d'un clic sur un pseudo-élément est l'élément qui le génère — donc le
 *   lien lui-même. Le maillage SEO est intact pour la même raison : un seul `<a>`.
 * - le `:hover` du lien se déclenche depuis n'importe quel point de la carte, ce
 *   qui fournit le retour visuel (soulignement, couleur du CTA) sans une classe
 *   de plus.
 * - le texte de la carte n'est PLUS sélectionnable à la souris, l'overlay le
 *   recouvre. C'est le compromis assumé du procédé (celui de `.stretched-link` de
 *   Bootstrap) ; sur des cartes d'appel, personne ne copie le texte.
 *
 * DEUX CONDITIONS, toutes deux vérifiées par les tests des composants appelants :
 *
 * 1. La carte porteuse DOIT être `relative`. L'oublier ne casse RIEN de visible :
 *    l'overlay remonte simplement jusqu'au premier ancêtre positionné et rend
 *    cliquable une zone bien plus large que la carte. Aucune erreur, aucun test
 *    rouge — d'où les tests dédiés.
 * 2. Il ne doit rester AUCUN autre élément interactif dans la carte. Un second
 *    lien ou un bouton passerait sous l'overlay et deviendrait inatteignable.
 *
 * ⚠️ À n'appliquer que sur un lien qui NAVIGUE. Les replis `AssistantButton`
 * (carte sans `href`) ouvrent un dialog : étirer un déclencheur de dialog sur
 * toute la carte transforme un survol distrait en ouverture de questionnaire.
 */
export const STRETCHED_LINK = "after:absolute after:inset-0 after:content-['']";
