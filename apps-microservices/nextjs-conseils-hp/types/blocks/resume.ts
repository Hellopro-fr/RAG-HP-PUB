export interface ResumeItem {
  label: string;
  text: string;
}

export interface ResumeBlockData {
  /** Titre du bloc (emoji déjà retiré) — utilisé tel quel en majuscules dans le Hero */
  title?: string;
  items: ResumeItem[];
  /** HTML brut du bloc type 15 de l'API PHP — prioritaire sur items si présent */
  html?: string;
}
