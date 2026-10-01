export interface TextBlockData {
  /** Contenu HTML formaté (balises p, strong, em, ul, a autorisées) */
  html: string;
  /** Encadré estimation optionnel affiché en badge */
  estimation?: {
    value: string;  // ex : "200 € à 13 500 € par place"
    label?: string; // ex : "Estimation"
  };
  /** Afficher un bouton CTA "Demander un devis" en bas du bloc */
  hasCta?: boolean;
}
