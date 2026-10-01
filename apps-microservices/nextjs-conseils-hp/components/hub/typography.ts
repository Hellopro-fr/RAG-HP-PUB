/**
 * ÉCHELLE TYPOGRAPHIQUE DU TEMPLATE HUB — source unique.
 *
 * POURQUOI CE FICHIER EXISTE
 * Les tailles de texte avaient été portées composant par composant depuis le
 * prototype Lovable. Résultat mesuré sur la page 1000 : trois échelles de titre de
 * section (`text-3xl sm:text-4xl`, `text-2xl`, `text-xl sm:text-2xl`) et quatre de
 * titre de carte (`text-lg`, `text-[17px]`, `text-base`, `text-2xl sm:text-3xl`),
 * pour six niveaux de hiérarchie réels. À la lecture, en scrollant, ça donne
 * l'impression de changer de police à chaque bloc — c'est le défaut qui a été
 * signalé, et c'est un défaut de COHÉRENCE, pas de goût : chaque valeur prise
 * isolément était défendable.
 *
 * Ce n'est donc PAS « une seule taille partout ». Une carte a légitimement un
 * texte plus petit qu'un paragraphe éditorial. Ce qu'on supprime, c'est
 * l'improvisation : six niveaux DÉCLARÉS au lieu de treize valeurs éparpillées.
 * Le précédent est la constante `PROSE`, introduite pour le bloc éditorial seul,
 * qui avait réglé le problème sur ce bloc — ce fichier généralise le procédé.
 *
 * RÈGLE : aucune couleur dans ces constantes.
 * Le même niveau sert sur fond clair (`text-foreground`) et sur fond sombre
 * (`text-white`, `text-white/80`) : `FinalCta`, `OverlayCard` et le hero sont sur
 * aplat foncé. Et surtout, concaténer deux classes de couleur Tailwind ne les
 * départage PAS de façon déterministe — c'est l'ordre dans la feuille compilée qui
 * tranche, pas l'ordre dans l'attribut. Une couleur par défaut dans la constante
 * serait donc un piège pour le prochain appelant. La taille, le poids, l'interligne
 * et le tracking sont ici ; la couleur reste au point d'appel.
 *
 * AJOUTER UN NIVEAU : seulement si aucun existant ne convient, et avec le motif
 * écrit en commentaire. Un `text-*` littéral sur un titre d'un composant
 * `components/hub/` fait échouer `__tests__/components/hub/typography.test.ts`.
 *
 * HORS PÉRIMÈTRE, volontairement :
 *  - `AssistantForm` (questionnaire du hero) — laissé tel quel sur demande ;
 *  - `components/conseil/blocks/FaqBlock` — partagé avec les pages conseils, le
 *    modifier changerait le rendu de tout le template conseils. Il rend son titre
 *    en `text-3xl font-extrabold` sans palier `sm:`, seul écart restant en bas de
 *    page HUB (cf. CLAUDE.md).
 */

/** `h1` de la page. Un seul par page, d'où un niveau à part. */
export const PAGE_TITLE =
  'text-4xl font-bold leading-[1.05] tracking-tight sm:text-5xl lg:text-6xl';

/**
 * `h2` de section — le niveau le plus grand du corps de page.
 * Utilisé par les 9 sections pleine largeur, y compris celles qui étaient restées
 * en dessous (`AccompagnementSplit` en `text-2xl`).
 */
export const SECTION_TITLE = 'text-3xl font-bold leading-tight tracking-tight sm:text-4xl';

/** Chapeau sous un titre de section, ou paragraphe d'introduction d'un bloc. */
export const SECTION_SUBTITLE = 'text-base leading-relaxed sm:text-lg';

/**
 * Titre des deux bandeaux horizontaux (accompagnement, guide gratuit).
 * Niveau intermédiaire ASSUMÉ : ce sont des bandes fines de 130 px de haut, un
 * `SECTION_TITLE` y écraserait le CTA placé sur la même ligne. La différence avec
 * les sections devient une décision, au lieu d'un héritage du prototype.
 */
export const BANNER_TITLE = 'text-xl font-bold leading-tight tracking-tight sm:text-2xl';

/**
 * Titre de carte VEDETTE : carte overlay des blocs thématiques (photo pleine
 * hauteur) et grand modal d'accroche de `LeadPopup`. Une carte qui occupe une
 * demi-section porte un titre plus fort qu'une carte de grille.
 */
export const FEATURE_TITLE = 'text-2xl font-bold leading-tight sm:text-3xl';

/**
 * Titre de carte — TOUTES les cartes de grille, de colonne et de carrousel.
 * Remplace `text-lg` / `text-[17px]` / `text-base`. La valeur arbitraire
 * `text-[17px]` était unique dans tout le service : un pixel de plus que `text-base`
 * pour un écart invisible seul, mais visible à côté d'une carte voisine en `text-lg`.
 */
export const CARD_TITLE = 'text-lg font-bold leading-snug';

/** Corps de texte dans une carte. */
export const CARD_BODY = 'text-sm leading-relaxed';

/**
 * Prose éditoriale — blocs SEO. Une seule taille, une seule couleur au point
 * d'appel, le gras dans la couleur du texte courant.
 *
 * Le bloc éditorial en comptait trois combinaisons (paragraphes gris `text-base`,
 * puces noires `text-base`, encart « À noter » gris `text-sm`) plus des pastilles
 * bleues. Toute nuance de hiérarchie passe désormais par la STRUCTURE (titre,
 * cadre de l'encart), jamais par la couleur ni la taille du texte.
 */
export const PROSE = 'text-base leading-relaxed [&_strong]:font-semibold';

/** Titre de dialog (parcours guide, coordonnées, remerciement). */
export const DIALOG_TITLE = 'text-xl font-bold leading-snug sm:text-2xl';

/** Pastille de rubrique, badge, tag. */
export const TAG = 'text-[11px] font-bold uppercase tracking-wider';

/** Libellé de lien inline (« Lire l'article », « En savoir plus »). */
export const LINK_LABEL = 'text-sm font-semibold';

/** Élément d'une liste à coche (garanties, arguments de réassurance). */
export const CHECK_ITEM = 'text-sm font-medium';

/** Légende de vignette (tuiles « Explorez les grandes étapes »). */
export const TILE_LABEL = 'text-sm font-semibold';

/** Mention discrète : réassurance sous un CTA, note légale. */
export const META = 'text-xs';
