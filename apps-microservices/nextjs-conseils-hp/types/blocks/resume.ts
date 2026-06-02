export interface ResumeItem {
  label: string;
  text: string;
}

export interface ResumeBlockData {
  items: ResumeItem[];
  /** HTML brut du bloc type 15 de l'API PHP — prioritaire sur items si présent */
  html?: string;
}
