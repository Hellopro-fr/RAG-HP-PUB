export interface TableauHtmlBlockData {
  /** Première ligne du tableau PHP (titres de colonnes) */
  headers: string[];
  /** Lignes de données (sans la ligne de titres) */
  rows: string[][];
}
