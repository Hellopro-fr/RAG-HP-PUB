// Catalogue statique des options de budget proposées à l'utilisateur sur la
// page /budget. À terme, ces options viendront de l'API HelloPro
// (probablement servies en fonction de la catégorie et de l'estimatif).
//
// Conservation de la shape : `BudgetOption[]` permet de brancher un fetch API
// (ex: `useBudgetOptions(categoryId)`) sans refacto côté composants.

export interface BudgetOption {
  id: string;
  label: string;
  description?: string;
}

export const BUDGET_OPTIONS: BudgetOption[] = [
  {
    id: "less_than_2500",
    label: "Moins de 2 500 €",
    description: "Mon budget est nettement en dessous de l'estimatif",
  },
  { id: "between_2500_3000", label: "2 500 € – 3 000 €" },
  { id: "between_3000_3500", label: "3 000 € – 3 500 €" },
  { id: "between_3500_4000", label: "3 500 € – 4 000 €" },
  { id: "more_than_4000", label: "Plus de 4 000 €" },
  { id: "no_idea", label: "Je ne sais pas encore" },
];
