export interface ProductItem {
  id: string;
  name: string;
  image: string;
  /** Prix HT en nombre, null si non renseigné (→ "Prix sur demande") */
  priceHt: number | null;
  url: string;
}

export interface ProduitsBlockData {
  /** IDs bruts (conservés pour fallback fetch éventuel) */
  productIds: string[];
  /** Titre affiché au-dessus du carousel (depuis contenu.titre) */
  titre?: string;
  /** Objets produits complets issus de l'API PHP */
  produits: ProductItem[];
}
