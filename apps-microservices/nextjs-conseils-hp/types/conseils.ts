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

export interface ConseilPage {
  slug: string;
  pageType: ConseilPageType;
  meta: ConseilPageMeta;
  hero: HeroData;
  blocks: ConseilBlock[];
  author?: AuthorInfo;
  // Spécifiques au pageType (gérés HORS BlockRenderer)
  priceData?: unknown;        // À typer en Phase 8
  topFabricants?: unknown;    // À typer en Phase 8
  rulesTable?: unknown;       // À typer en Phase 8
}
