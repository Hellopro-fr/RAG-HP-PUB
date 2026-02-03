"use client";

import { RefreshCw, X } from "lucide-react";

interface CriteriaChangedBannerProps {
  onNewSelection: () => void;
  onDismiss: () => void;
}

const CriteriaChangedBanner = ({ onNewSelection, onDismiss }: CriteriaChangedBannerProps) => {
  return (
    <div className="rounded-xl border border-primary/20 bg-primary/5 p-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex-1">
          <p className="font-medium text-foreground">
            Vos critères ont changé
          </p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Souhaitez-vous repartir d'une nouvelle sélection adaptée à ces critères ?
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={onDismiss}
            className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="h-4 w-4" />
            Non merci
          </button>
          <button
            onClick={onNewSelection}
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            <RefreshCw className="h-4 w-4" />
            Nouvelle sélection
          </button>
        </div>
      </div>
    </div>
  );
};

export default CriteriaChangedBanner;
