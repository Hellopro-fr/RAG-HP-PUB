export interface TableauPrixRow {
  type: string;        // ex : "Bâtiment vaches allaitantes"
  price: string;       // ex : "2 900 – 4 150 €"
  surface?: string;    // ex : "13 – 15 m²"
  pricePerM2?: string; // ex : "190 – 310 €/m²"
}

export interface TableauPrixBlockData {
  rows: TableauPrixRow[];
}
