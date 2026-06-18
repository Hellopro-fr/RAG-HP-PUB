/**
 * Types centraux pour le système de blocs conseils.
 * Voir CLAUDE.md §2 (Architecture BlockRenderer).
 */

export type ConseilPageType = 'prix' | 'top' | 'autre';

export type ConseilBlockType =
  | 'h2'
  | 'h3'
  | 'texte'
  | 'pros-cons'
  | 'resume'
  | 'image'
  | 'texte-image'
  | 'image-texte'
  | 'image-image'
  | 'video'
  | 'cta'
  | 'produits'
  | 'tableau-html'
  | 'tableau-prix'
  | 'estimation-prix' // Tableau prix "single" (type 11 BO non fusionné) — box estimation
  | 'faq'
  | 'type-section'  // Section par type (animal, produit…) avec image, estimation, bullets
  | 'brochure'      // Bloc guide/brochure téléchargeable avec form email
  | 'quote-form';   // Formulaire devis inline mid-article

export interface ConseilBlock<T = Record<string, unknown>> {
  id: string;
  type: ConseilBlockType;
  order: number;
  data: T;
}

export interface ConseilPageMeta {
  title: string;
  description: string;
  ogImage?: string;
}

export interface HeroData {
  title: string;
  subtitle?: string;
  image?: string;
  estimation?: { min: number; max: number; unit: string };
}

export interface AuthorInfo {
  name: string;
  role: string;
  bio: string;
  photo?: string;
  linkedinUrl?: string;
  contactEmail?: string;
}

export interface AoChoix {
  id: string | number;
  label: string;
  image?: string;
  /** 1 = champ libre associé au choix (révèle .input-autre dans le formulaire) */
  typeInput?: string | number;
}

export interface AoFormQuestion {
  id: string | number;
  question: string;
  avecImage: boolean;
  /** 1 = choix unique (radio) → clic direct ouvre le modal  /  2+ = choix multiple (checkbox) → bouton CTA */
  typeSelection: string | number;
  /** 1 = réponse obligatoire avant de valider / 0 = facultatif */
  obligatoire: 0 | 1;
  /** Nombre d'écrans dans le formulaire — utilisé pour step_number dans le push GTM quote_form_funnel */
  stepNumber?: number;
  choix: AoChoix[];
}

export interface Supplier {
  id: string;
  name: string;
  /** URL complète du logo, construite par le fetcher (ex. https://www.hellopro.fr/images/logo/...) */
  logoPath: string;
  description?: string;
}

/** Page conseil associée — "Pour aller plus loin" */
export interface ConseilAssocie {
  id: string;
  titre: string;
  url: string;
  /** 0 = autre, 1 = prix, 2 = top */
  idTag: number;
}

/** Lien interne issu du champ liens_intexts de l'API PHP */
export interface LienInterne {
  id: number;
  /** 0 = feuille produit, 1 = rubrique, 2 = page conseil */
  type: 0 | 1 | 2;
  photo: string;
  titre: string;
  description: string;
  url: string;
  prix?: string;
}

export interface ConseilPage {
  slug: string;
  pageType: ConseilPageType;
  meta: ConseilPageMeta;
  /** URL canonique complète renvoyée par l'API (ex. https://conseils.hellopro.fr/slug-id.html). Sert à la balise canonical + redirection 301. */
  canonicalUrl?: string;
  hero: HeroData;
  blocks: ConseilBlock[];
  author?: AuthorInfo;
  /** Date de dernière mise à jour, formatée en français (ex: "Mis à jour le 28 avril 2026") */
  updatedAt?: string;
  breadcrumb?: Array<{ label: string; href?: string }>;
  formulaire_ao?: AoFormQuestion | null;
  /** Rubrique principale de la page — source de l'id_rubrique et du libellé pour l'iframe */
  infoRubrique?: { id: number; libelle: string } | null;
  liensIntexts?: LienInterne[];
  conseilsAssocies?: ConseilAssocie[];
  /** Catégories pour le menu "Tous les produits" du header */
  headerCategories?: Array<{ id: number; nom: string; url: string }>;
  /** Fournisseurs référencés issus du champ top_clients de l'API */
  suppliers?: Supplier[];
  schemaGuide?: Record<string, unknown>;
  schemaBreadcrumb?: Record<string, unknown>;
  // Spécifiques au pageType (gérés HORS BlockRenderer)
  priceData?: unknown;        // À typer en Phase 8
  topFabricants?: unknown;    // À typer en Phase 8
  rulesTable?: unknown;       // À typer en Phase 8
}
