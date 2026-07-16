/**
 * Bloc « tableau prix single » (type 11 BO) non fusionné dans un texte-image.
 * Rendu en box estimation pleine largeur (label ~30 % / valeur ~70 %).
 */
export interface EstimationPrixBlockData {
  /** Libellé de gauche (ex. « Estimation de prix »). */
  label: string;
  /** Valeur de droite (ex. « Entre 5 et 25 € annuel / m² »). */
  value: string;
}
