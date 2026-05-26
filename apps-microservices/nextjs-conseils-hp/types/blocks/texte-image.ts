export interface TexteImageBlockData {
  /** Contenu HTML du côté texte */
  html: string;
  image: {
    src: string;
    alt: string;
  };
  /** Estimation optionnelle affichée en badge sur le bloc */
  estimate?: string;
  estimateLabel?: string;
  /** Liste de bullets points */
  bullets?: string[];
  ctaLabel?: string;
  /** Position de l'image : droite (texte-image) ou gauche (image-texte) */
  imagePosition: 'right' | 'left';
}
