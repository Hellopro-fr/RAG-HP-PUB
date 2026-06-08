/**
 * Types de la réponse brute de l'API PHP :
 * GET api/hp/view/page_conseil.php?p=<id_conseil>
 */

export interface PhpImage {
  path: string;
  title: string;
  legende: string;
  alternatif: string;
  taille: string;
}

export interface PhpEstimation {
  label: string;
  valeur: string;
}

/** Utilisé dans les blocs type 4 (inline) et type 7 (standalone CTA) */
export interface PhpCta {
  wording: string;
  color: string;
  wording_color: string;
  formulaire_popup: number;
  feuille_associe: string | number;
  url: string;
  // Champs présents uniquement sur le bloc CTA standalone (type 7)
  accroche_1?: string;
  accroche_2?: string;
  nom_feuille_associe?: string;
}

export interface PhpFaqItem {
  question: string;
  reponse: string;
}

export interface PhpProduit {
  id_produit: number;
  nom_produit: string;
  vignette: string;
  description: string;
  prix_ht: number | string | null;
  statut_prix: number | null;
  statut: string | null;
  affichage_dd_rd: number;
  url: string;
  nom_commercial: string;
  nom_fabricant: string;
  id_rubrique: number;
  variant_gtm: string;
}

export interface PhpProsConsData {
  label_avantages: string;
  liste_avantages: string[];
  label_inconvenients: string;
  liste_inconvenients: string[];
}

/**
 * Contenu d'un bloc — les champs présents dépendent du type numérique.
 * type 1  → items
 * type 2  → texte
 * type 4  → texte + image + estimation? + cta?
 * type 6  → video
 * type 7  → cta (avec accroche_1/accroche_2)
 * type 8  → titre + liste_id_produit + produits
 * type 9  → table
 * type 11 → texte (estimation prix)
 * type 16 → pros_cons
 */
export interface PhpBlocContenu {
  items?: PhpFaqItem[];
  texte?: string;
  image?: PhpImage;
  images?: PhpImage[]; // type 13 image-image
  estimation?: PhpEstimation;
  cta?: PhpCta;
  video?: string;
  titre?: string;
  liste_id_produit?: number[];
  id_feuille?: number;
  vignette?: string;
  produits?: PhpProduit[];
  table?: string[][];
  pros_cons?: PhpProsConsData;
}

export interface PhpBloc {
  id?: number;
  type: number;
  ordre: number;
  contenu: PhpBlocContenu;
}

export interface PhpSeo {
  meta_title: string;
  meta_description: string;
}

export interface PhpFilAriane {
  libelle: string;
  url: string;
  type: string;
}

export interface PhpLienInterne {
  id_mli: number;
  id_page: number;
  /** 0 = feuille produit, 1 = rubrique, 2 = page conseil */
  type: number;
  photo: string;
  titre: string;
  description: string;
  url: string;
  prix?: string;
}

export interface PhpAoChoix {
  id: string | number;
  choix: string;
  libelle_info: string;
  vignette: string;
  explication: string;
  ordre_choix: string | number;
  type_input: string | number;
  placeholder: string;
  visible: string | number;
  numero_critere: number;
  max_length: number | null;
}

export interface PhpAoQuestion {
  id: string | number;
  question: string;
  libelle_info: string;
  type_selection: string | number;
  visible: string | number;
  description: string;
  ordre: string | number;
  obligatoire: string | number;
  avec_image: 0 | 1;
  choix: PhpAoChoix[];
}

export interface PhpAuteur {
  nom_prenom: string;
  profession: string;
  description: string;
  url_photo?: string;
}

export interface PhpConseilAssocie {
  id: string;
  titre: string;
  url: string;
  /** 0 = autre, 1 = prix, 2 = top */
  id_tag: number;
}

export interface PhpTopClient {
  id_societe: string;
  nom_commercial: string;
  montant_alloue: number;
  /** Chemin relatif ex. "images/logo/logo_3002237.jpg" */
  logo: string;
  profil_societe_francais?: string;
}

export interface PhpConseilPage {
  id: number;
  titre: string;
  /** URL canonique — sert à extraire le slug et détecter les redirects 301 */
  url: string;
  seo: PhpSeo;
  fil_ariane: PhpFilAriane[];
  auteur?: PhpAuteur | null;
  date_modification: string;
  /** 0 = autre, 1 = prix, 2 = top */
  id_tag: number;
  prix: unknown;
  /** Texte du premier bloc, utilisé comme subtitle du Hero */
  premier_bloc_texte: string | null;
  blocs: PhpBloc[];
  schema_guide: Record<string, unknown>;
  schema_breadcrumb: Record<string, unknown>;
  liens_intexts?: PhpLienInterne[];
  pages_conseils_associees?: PhpConseilAssocie[];
  formulaire_ao?: PhpAoQuestion[];
  top_clients?: PhpTopClient[];
  header?: unknown;
  footer?: unknown;
}

export interface PhpConseilResponse {
  code: number;
  response: PhpConseilPage;
}
