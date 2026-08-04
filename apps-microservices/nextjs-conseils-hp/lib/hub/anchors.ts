/**
 * Ids des sections FIXES du template HUB — celles dont l'identifiant est porté par
 * le composant et non par les données.
 *
 * Pourquoi les centraliser : ces ids servent de cibles à trois choses distinctes —
 * le sommaire sticky (`page.nav`), les tuiles « grandes étapes »
 * (`grandesEtapes[].href`) et les liens internes du contenu. Éparpillés en chaînes
 * littérales dans huit composants, renommer une section cassait silencieusement
 * les liens qui la visaient, et le test des ancres ne pouvait pas les connaître.
 *
 * Ce que ces ancres SONT et NE SONT PAS, côté SEO :
 *  - Google **ignore le fragment pour l'indexation** : `page.html#bloc-budget` et
 *    `page.html` sont la même URL. Le nom de l'ancre n'a aucune valeur de
 *    classement, et le renommer ne fait perdre aucun référencement.
 *  - En revanche elles servent aux « liens vers une section » que Google peut
 *    afficher sous un résultat, à la navigation du sommaire, et aux liens
 *    profonds que les visiteurs partagent. Une ancre renommée après mise en ligne
 *    casse ces liens partagés — d'où l'intérêt de fixer les noms AVANT.
 *
 * ⚠️ Ne pas confondre avec le cas des pages CONSEILS : là, l'ancien template PHP
 * posait des ids numériques (`#4`, `#18`) que Google avait effectivement repris
 * dans ses liens de section, ce qui obligeait à les conserver. Les pages HUB sont
 * neuves (namespace `-projet.html` inédit) : aucun historique à préserver.
 *
 * Les sections issues des données portent leur propre id : `thematiques[].id`
 * (`bloc-budget`…) et `editos[].id` (`edito-budget`…).
 */
/**
 * ⚠️ Nommage : chaque ancre décrit le SUJET de sa section, en mots que comprend un
 * visiteur — jamais le composant qui la rend. Les noms initiaux venaient du
 * prototype et faisaient fuiter du vocabulaire d'implémentation dans des URL
 * publiques (`intro-hub`, `cta-final`, `bloc-*`, `edito-*`).
 */
export const HUB_SECTION_IDS = {
  valueProps: 'ce-que-vous-gagnez',
  guideCta: 'guide-gratuit',
  ressources: 'nos-ressources',
  grandesEtapes: 'grandes-etapes',
  howItWorks: 'comment-ca-marche',
  accompagnement: 'accompagnement',
  finalCta: 'etre-accompagne',
  faq: 'faq',
} as const;

export type HubSectionId = (typeof HUB_SECTION_IDS)[keyof typeof HUB_SECTION_IDS];

/** Toutes les ancres fixes, pour les contrôles de cohérence. */
export const HUB_SECTION_ID_LIST = Object.values(HUB_SECTION_IDS) as readonly string[];
