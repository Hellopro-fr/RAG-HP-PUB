export interface ProductItem {
  id: string;
  name: string;
  image: string;
  /** Prix HT en nombre, null si non renseigné (→ "Prix sur demande") */
  priceHt: number | null;
  url: string;
  /** GTM: nom_fabricant */
  brand?: string;
  /** GTM: id_rubrique (catégorie produit) */
  category?: string;
  /** GTM: variant_gtm (ex. "cert") */
  variant?: string;
  /** Source du produit : 0 = base edgb2b (catalogue officiel), 1 = base hellopro_ia (scrapé) */
  srcInteg?: 0 | 1;
}

export interface ProduitsBlockData {
  /** IDs bruts (conservés pour fallback fetch éventuel) */
  productIds: string[];
  /** Titre affiché au-dessus du carousel (depuis contenu.titre) */
  titre?: string;
  /** Objets produits complets issus de l'API PHP */
  produits: ProductItem[];
}
