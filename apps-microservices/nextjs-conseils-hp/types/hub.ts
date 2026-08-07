/**
 * Types du template HUB « projet » — pages `/<slug>-<id>-projet.html`.
 *
 * Différences assumées avec les pages conseils (`types/conseils.ts`) :
 *  - Contenu 100 % STOCKÉ (`data/hub/*.ts`) : pas de BFF, pas de transformer,
 *    les projets HUB n'existent pas en base SQL.
 *  - Composition à SLOTS NOMMÉS et non liste de blocs `BlockRenderer` : les
 *    3 pages partagent un template figé, seul le contenu varie. Les parties
 *    répétables (`thematiques`, `editos`, `ressources`…) sont des tableaux ordonnés.
 *
 * Règles à respecter dans les fichiers de données :
 *  1. AUCUN JSX, AUCUN composant importé. Les icônes passent par un nom
 *     (`HubIconName`) résolu par `lib/hub/icons.ts` — sinon un fichier de données
 *     devient un fichier React et n'est plus éditable sans connaître Next.
 *  2. AUCUN `import` d'image. Chemins string sous `public/images/hub/<slug>/`,
 *     avec `width`/`height` obligatoires (évite le CLS, `next/image` en Server Component).
 */

import type { HubIconName } from '@/lib/hub/icons';

export type { HubIconName };

/**
 * Image servie par next/image depuis /public.
 *
 * ⚠️ PAS de `width`/`height`, volontairement. Toutes les images du template sont
 * rendues avec **`fill`**, dans une boîte dont la taille est imposée par la mise
 * en page (`object-cover` pour les vignettes, `object-contain` pour les visuels
 * produit). Leurs dimensions d'origine n'ont donc aucun effet — les déclarer
 * n'apportait rien et ouvrait la porte à un ratio faux, qui a été le défaut le
 * plus fréquent de ce fichier. Aucun risque de CLS non plus : le conteneur a
 * toujours une taille définie.
 *
 * ⚠️ Tous les champs `image` du modèle sont OPTIONNELS. Une image pas encore
 * livrée doit être ABSENTE des données — jamais remplacée par un chemin inventé.
 * `__tests__/data/hub/registry.test.ts` vérifie que chaque image déclarée existe
 * bien sur le disque.
 */
export interface HubImage {
  /** Chemin absolu depuis /public — ex. '/images/hub/creer-food-truck/hero.jpg' */
  src: string;
  alt: string;
}

/** Fil d'ariane. Convention GtmFooterScripts : 1er = Accueil, dernier = titre de page. */
export interface HubBreadcrumbItem {
  label: string;
  href?: string;
}

/**
 * Titre découpé en fragments, pour styler une partie du titre sans mettre de JSX
 * dans les données. `accent: true` → rendu en `text-cta`.
 */
export interface HubTitlePart {
  text: string;
  accent?: boolean;
}

/* ------------------------------------------------------------------ Sections */

export interface HubHeroFeature {
  icon: HubIconName;
  title: string;
  desc: string;
}

export interface HubHero {
  badge: string;
  titleParts: HubTitlePart[];
  subtitle: string;
  /** Absente → fond uni + dégradé, sans image. */
  background?: HubImage;
  features: HubHeroFeature[];
  trust: {
    /** ex. '4.3/5 de satisfaction' — affiché avec 5 étoiles */
    rating?: string;
    /** ex. '+15 000 fournisseurs certifiés' */
    suppliers?: string;
  };
}

/** Entrée du sommaire sticky. `id` doit correspondre à un id de section rendu. */
export interface HubNavItem {
  id: string;
  label: string;
  icon: HubIconName;
}

export interface HubValuePropItem {
  tag: string;
  title: string;
  desc: string;
  icon: HubIconName;
  accent: 'primary' | 'cta';
}

export interface HubValueProps {
  title: string;
  subtitle: string;
  /** Phrase de clôture sous la grille */
  closing: string;
  items: HubValuePropItem[];
}

/**
 * Carte « overlay » : image plein cadre + dégradé + titre + puces.
 * Utilisée comme pièce maîtresse d'un bloc thématique.
 */
export interface HubOverlayCard {
  title: string;
  /** Absente → carte à fond sombre uni, sans photo. */
  image?: HubImage;
  /**
   * Phrase de cadrage entre le titre et les puces.
   * Accepte du HTML restreint (`<strong>`, `<em>`…) — toujours assaini au rendu.
   */
  intro?: string;
  /**
   * Puces à coche. Acceptent aussi du HTML restreint : les chiffres clés sont
   * souvent mis en gras au milieu de la phrase, ce qu'un texte plat ne permet pas
   * d'exprimer sans mettre du JSX dans les données.
   */
  bullets: string[];
  /** Libellé du bouton d'action de la carte. Absent → pas de bouton. */
  ctaLabel?: string;
  /**
   * URL de l'article. Présente → vrai lien. Absente → ouverture du questionnaire.
   */
  href?: string;
}

/**
 * Carte d'un bloc thématique.
 *
 * ⚠️ Deux rendus selon le `layout` du bloc, et donc deux jeux de champs utiles :
 *  - layouts `overlay-left` / `overlay-right` → carte compacte : `icon`, `title`,
 *    `description`/`descriptionHtml`, `linkLabel`. Le champ `image` est IGNORÉ.
 *  - layouts `grid` / `carousel` → carte vignette : `image`, `title`, `href`.
 *    Le champ `icon` est IGNORÉ.
 *
 * Renseigner un champ hors de son layout est sans effet à l'écran — c'est ce qui a
 * laissé 5 vignettes orphelines sur le disque. `registry.test.ts` refuse
 * désormais ces combinaisons.
 */
export interface HubInfoCard {
  /** Layouts `overlay-*` uniquement. */
  icon?: HubIconName;
  title: string;
  /** Texte simple. Pour du gras, utiliser `descriptionHtml`. */
  description?: string;
  /** HTML restreint (<strong>, <em>, <br>) — sanitisé au rendu. */
  descriptionHtml?: string;
  /** Layouts `grid` / `carousel` uniquement. */
  image?: HubImage;
  /** Libellé du lien de bas de carte — ex. « Lire l'article ». Absent → pas de lien. */
  linkLabel?: string;
  /**
   * URL de l'article. Présente → vrai lien `<a>` (lien interne crawlable).
   * Absente → repli sur l'ouverture du questionnaire, pour ne pas exposer de lien
   * mort. Toujours préférer une URL réelle : c'est ce qui donne au HUB sa valeur
   * de maillage interne.
   */
  href?: string;
}

/**
 * Layout d'un bloc thématique :
 *  - `overlay-left`  : overlay à gauche, cartes à droite
 *  - `overlay-right` : cartes à gauche, overlay à droite
 *  - `grid`          : cartes seules en grille
 *  - `carousel`      : cartes seules en carrousel scroll-snap
 */
export type HubThematiqueLayout = 'overlay-left' | 'overlay-right' | 'grid' | 'carousel';

/**
 * Bloc thématique — c'est LA brique réutilisable du template.
 * Les 4 blocs de la page (budget, dimensionnement, réglementation, équipements)
 * sont le même composant avec un `layout` différent. Toute page HUB doit pouvoir
 * se décrire uniquement en changeant ce tableau.
 */
export interface HubThematique {
  /** Ancre + cible du sommaire — ex. 'bloc-budget'. NE PLUS CHANGER une fois indexé. */
  id: string;
  /** Pastille de rubrique — ex. 'Budget & financement' */
  tag: string;
  /** Icône de la pastille de rubrique. */
  tagIcon?: HubIconName;
  layout: HubThematiqueLayout;
  intro?: string;
  overlay?: HubOverlayCard;
  cards: HubInfoCard[];
  /** Libellé du bouton d'ouverture du dialog guide. Absent → pas de bouton. */
  guideButtonLabel?: string;
}

export interface HubRessource {
  tag: string;
  title: string;
  image?: HubImage;
  /** URL de l'article. Absente → repli sur le questionnaire. */
  href?: string;
}

export interface HubRessources {
  title: string;
  subtitle: string;
  items: HubRessource[];
}

export interface HubGrandeEtape {
  image?: HubImage;
  label: string;
  /** Ancre interne — ex. '#bloc-budget'. Absent → tuile non cliquable. */
  href?: string;
}

/** Section éditoriale (texte SEO). */
/**
 * Section éditoriale. `intro`, `items`, `bodyHtml` et `note` acceptent tous du
 * HTML restreint (`<strong>`, `<p>`, `<ul>`, `<li>`…), assaini au rendu : le
 * contenu SEO met systématiquement en gras les chiffres clés et les intitulés de
 * puce au milieu des phrases.
 *
 * Ordre de rendu : `intro` → `bodyHtml` → `items` → `note`. Pour plusieurs
 * paragraphes, utiliser `bodyHtml` avec des `<p>`.
 */
export interface HubEdito {
  /** ex. 'edito-budget' */
  id: string;
  title: string;
  intro?: string;
  /** Liste à puces */
  items?: string[];
  bodyHtml?: string;
  /** Encart de fin de section */
  note?: string;
}

export interface HubHowItWorks {
  title: string;
  steps: { icon: HubIconName; title: string; desc: string }[];
  /**
   * Id de la section éditoriale APRÈS laquelle insérer ce bloc. Absent → après
   * tous les editos. Même logique que `afterThematiqueId`.
   */
  afterEditoId?: string;
}

export interface HubAccompagnement {
  title: string;
  /**
   * HTML restreint, assaini au rendu. Utiliser des `<p>` pour plusieurs
   * paragraphes — le texte de référence en compte deux.
   */
  text: string;
  image?: HubImage;
  points: string[];
}

export interface HubAccompagnementBanner {
  tag: string;
  title: string;
  text: string;
  ctaLabel: string;
  image?: HubImage;
  /**
   * Id du bloc thématique APRÈS lequel insérer la bannière. Absent → en fin de
   * liste. Permet de reproduire l'entrelacement du prototype sans coder d'index
   * en dur dans le template, donc sans casser sur une page qui aurait un nombre
   * de blocs différent.
   */
  afterThematiqueId?: string;
}

export interface HubGuideCta {
  tag: string;
  title: string;
  text: string;
  ctaLabel: string;
  image?: HubImage;
}

export interface HubFinalCta {
  badge: string;
  titleParts: HubTitlePart[];
  text: string;
  items: { icon: HubIconName; label: string }[];
  ctaLabel: string;
  reassurance: string;
  image?: HubImage;
}

export interface HubFaq {
  title: string;
  items: { q: string; a: string }[];
}

/* ----------------------------------------------------------- Formulaires POC */

/**
 * Une étape du questionnaire. `multi: true` → sélection multiple.
 * `illustrations` : une icône par option, dans le même ordre (optionnel).
 */
export interface HubAssistantStep {
  id: string;
  label: string;
  multi: boolean;
  options: string[];
  illustrations?: HubIconName[];
}

/**
 * ⚠️ POC — le questionnaire n'envoie RIEN (aucun POST, aucun lead collecté).
 * Décision du 28/07/2026 : on porte l'UI telle quelle, branchement plus tard.
 */
export interface HubAssistant {
  /** Titre de la carte du hero */
  cardTitle: string;
  ctaLabel: string;
  reassurance: string;
  steps: HubAssistantStep[];
  contact: {
    badge: string;
    label: string;
    /** Sous-titre optionnel sous le champ e-mail. */
    helper?: string;
    emailPlaceholder: string;
    submitLabel: string;
  };
  /**
   * Étape « coordonnées » insérée entre l'e-mail et l'écran de succès.
   * L'e-mail est déjà saisi à l'étape précédente : il n'est pas repris ici.
   * Tous les champs sont requis pour activer l'envoi (⚠️ POC — rien n'est transmis).
   */
  coordinates: {
    badge: string;
    label: string;
    helper: string;
    /** Libellé de l'encart civilité, ex. 'Civilité'. */
    civilityLabel: string;
    /** Options de civilité (radios), ex. ['Monsieur', 'Madame']. */
    civilityOptions: string[];
    fields: {
      name: string;
      prenom: string;
      phone: string;
      postalCode: string;
    };
    submitLabel: string;
  };
  success: {
    title: string;
    /** Texte descriptif sous la couverture du guide. */
    subtitle: string;
    /** Couverture du guide affichée sur l'écran de remerciement. */
    image: HubImage;
    /** Bouton de téléchargement du guide (outline). */
    downloadLabel: string;
    /** URL du PDF. Design-only : peut rester '#'. */
    fileUrl?: string;
  };
}

/**
 * ⚠️ POC — design multi-étapes (mock). Parcours : e-mail → coordonnées →
 * téléchargement. La bascule « e-mail connu → saut direct au téléchargement »
 * n'est pas encore câblée (design d'abord) ; le flux est linéaire pour l'instant.
 */
export interface HubGuideDialog {
  badge: string;
  titleParts: HubTitlePart[];
  fields: { name: string; prenom: string; email: string; phone: string; postalCode: string };
  /** Placeholder du champ e-mail (le libellé `fields.email` sert de label visible). */
  emailPlaceholder: string;
  /** Bouton de l'étape 1 (e-mail). */
  emailSubmitLabel: string;
  /** Badge de l'étape 2 (coordonnées), ex. 'Dernière étape'. */
  coordinatesBadge: string;
  /** Titre de l'étape 2 (coordonnées). */
  coordinatesTitle: string;
  /** Sous-titre de l'étape 2 (coordonnées). */
  coordinatesSubtitle: string;
  /** Libellé de l'encart civilité + options (radios). */
  civilityLabel: string;
  civilityOptions: string[];
  /** Bouton de l'étape 2 (coordonnées). */
  coordinatesSubmitLabel: string;
  trust: string[];
  /** Étape finale : incitation au téléchargement du guide. */
  download: {
    title: string;
    subtitle?: string;
    /** Texte sous la couverture (ex. « Vous pouvez aussi le récupérer… »). */
    note?: string;
    image: HubImage;
    buttonLabel: string;
    /** URL du PDF. Design-only : peut rester '#' tant que le fichier n'est pas livré. */
    fileUrl?: string;
  };
}

/** ⚠️ POC — mock, aucune donnée transmise. */
export interface HubLeadPopup {
  badge: string;
  title: string;
  scriptLine: string;
  text: string;
  emailPlaceholder: string;
  submitLabel: string;
  reassurance: string;
  /** Visuel du guide, colonne de gauche. */
  image?: HubImage;
  /** Bandeau photo en tête de la pop-up, pleine largeur. */
  bannerImage?: HubImage;
  /**
   * Pastille ronde « 100% / Gratuit », une ligne par entrée. Chevauche le bas du
   * bandeau quand `bannerImage` est fourni. Absente → pas de pastille.
   */
  circleBadgeLines?: string[];
  /** Id de la section dont la sortie de viewport déclenche le popup. */
  triggerSectionId: string;
}

/* -------------------------------------------------------------------- Page */

export interface HubPage {
  /** Clé de récupération dans le registry — présente dans l'URL. */
  id: number;
  /** Slug canonique, sans l'id ni le suffixe `-projet`. */
  slug: string;

  meta: {
    title: string;
    description: string;
    ogImage?: string;
  };

  /** 1er item = Accueil, dernier = titre de la page (convention GtmFooterScripts). */
  breadcrumb: HubBreadcrumbItem[];

  hero: HubHero;
  nav: HubNavItem[];
  valueProps: HubValueProps;
  /** L'ordre du tableau = l'ordre de rendu. */
  thematiques: HubThematique[];
  accompagnementBanner: HubAccompagnementBanner;
  guideCta: HubGuideCta;
  ressources: HubRessources;
  grandesEtapes: { title: string; items: HubGrandeEtape[] };
  editos: HubEdito[];
  howItWorks: HubHowItWorks;
  accompagnement: HubAccompagnement;
  finalCta: HubFinalCta;
  faq: HubFaq;
  stickyCtaLabel: string;

  assistant: HubAssistant;
  guideDialog: HubGuideDialog;
  leadPopup: HubLeadPopup;
}

/** URL publique canonique d'une page HUB. Dérivée, jamais stockée. */
export function hubCanonicalPath(page: Pick<HubPage, 'slug' | 'id'>): string {
  return `/${page.slug}-${page.id}-projet.html`;
}
