'use client';

import { cn } from "@/lib/utils";
import type { BudgetOption } from "@/data/budget-options";

interface BudgetQuestionScreenProps {
  options: BudgetOption[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

/**
 * Question budget single-select. Style aligné avec les boutons réponse de
 * QuestionScreen : carte bordée, radio circle à gauche, label + description
 * optionnelle. Aucune logique d'auto-advance — l'utilisateur choisit puis
 * clique le CTA "Voir ma sélection" pour avancer.
 */
const BudgetQuestionScreen = ({ options, selectedId, onSelect }: BudgetQuestionScreenProps) => {
  return (
    <div className="space-y-5">
      <div className="text-center">
        <h2 className="text-lg sm:text-xl lg:text-2xl font-bold text-foreground leading-tight">
          Et vous, quel budget avez-vous prévu pour ce projet ?
        </h2>
      </div>

      <div className="space-y-2">
        {options.map((option) => {
          const isSelected = selectedId === option.id;
          return (
            <button
              key={option.id}
              type="button"
              onClick={() => onSelect(option.id)}
              className={cn(
                "w-full text-left rounded-xl border-2 px-4 py-3 transition-all",
                "hover:border-primary/50 hover:bg-primary/5",
                isSelected
                  ? "border-primary bg-primary/10"
                  : "border-border bg-background"
              )}
            >
              <div className="flex items-center gap-3">
                <div
                  className={cn(
                    "flex h-5 w-5 shrink-0 items-center justify-center rounded-full transition-colors",
                    isSelected
                      ? "border-2 border-primary bg-primary"
                      : "border-2 border-muted-foreground/30"
                  )}
                >
                  {isSelected && (
                    <div className="h-2 w-2 rounded-full bg-primary-foreground" />
                  )}
                </div>
                <div className="flex-1">
                  <span className="text-sm sm:text-base text-foreground font-medium">
                    {option.label}
                  </span>
                  {option.description && (
                    <span className="ml-1.5 text-xs sm:text-sm text-muted-foreground">
                      — {option.description}
                    </span>
                  )}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};

export default BudgetQuestionScreen;
