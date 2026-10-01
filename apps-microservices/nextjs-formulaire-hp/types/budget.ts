/**
 * Option de réponse pour la question budget de la page /budget.
 * Source de vérité unique, consommée par BudgetQuestionScreen et budget-client.
 */
export interface BudgetOption {
  id: string;
  label: string;
  description?: string;
}
