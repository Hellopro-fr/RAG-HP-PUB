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
  choix: AoChoix[];
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
  hero: HeroData;
  blocks: ConseilBlock[];
  author?: AuthorInfo;
  breadcrumb?: Array<{ label: string; href?: string }>;
  formulaire_ao?: AoFormQuestion | null;
  /** Rubrique principale de la page — source de l'id_rubrique et du libellé pour l'iframe */
  infoRubrique?: { id: number; libelle: string } | null;
  liensIntexts?: LienInterne[];
  // Spécifiques au pageType (gérés HORS BlockRenderer)
  priceData?: unknown;        // À typer en Phase 8
  topFabricants?: unknown;    // À typer en Phase 8
  rulesTable?: unknown;       // À typer en Phase 8
}
