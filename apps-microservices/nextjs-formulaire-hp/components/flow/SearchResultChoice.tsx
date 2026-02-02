'use client';

import { Package, AlertTriangle, Info } from "lucide-react";

interface SearchResultChoiceProps {
  onChooseSelection: () => void;
  onChooseSomethingToAdd: () => void;
}

const SearchResultChoice = ({ onChooseSelection, onChooseSomethingToAdd }: SearchResultChoiceProps) => {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
      <div className="w-full max-w-2xl mx-4 bg-card border border-border rounded-2xl shadow-2xl p-8 space-y-6">
        {/* Dev notice */}
        <div className="flex items-center gap-2 rounded-lg bg-amber-500/10 border border-amber-500/20 px-4 py-2 text-sm text-amber-600">
          <Info className="h-4 w-4 shrink-0" />
          <span>Mode équipe : Cette modale permet de visualiser les deux scénarios possibles.</span>
        </div>

        {/* Title */}
        <div className="text-center">
          <h2 className="text-2xl font-bold text-foreground">
            Choix du scénario
          </h2>
          <p className="mt-2 text-muted-foreground">
            Sélectionnez le parcours à visualiser
          </p>
        </div>

        {/* Choice cards */}
        <div className="grid gap-4 sm:grid-cols-2">
          {/* Scenario 1: Enough products */}
          <button
            onClick={onChooseSelection}
            className="group flex flex-col items-center gap-4 rounded-xl border-2 border-border bg-background p-6 text-center transition-all hover:border-primary hover:bg-primary/5 hover:shadow-lg"
          >
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 text-primary transition-transform group-hover:scale-110">
              <Package className="h-8 w-8" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-foreground">
                Assez de produits
              </h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Scénario où suffisamment de produits correspondent à la recherche
              </p>
            </div>
          </button>

          {/* Scenario 2: Not enough products */}
          <button
            onClick={onChooseSomethingToAdd}
            className="group flex flex-col items-center gap-4 rounded-xl border-2 border-border bg-background p-6 text-center transition-all hover:border-accent hover:bg-accent/5 hover:shadow-lg"
          >
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-accent/10 text-accent transition-transform group-hover:scale-110">
              <AlertTriangle className="h-8 w-8" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-foreground">
                Pas assez de produits
              </h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Scénario où il n'y a pas suffisamment de produits correspondants
              </p>
            </div>
          </button>
        </div>
      </div>
    </div>
  );
};

export default SearchResultChoice;
