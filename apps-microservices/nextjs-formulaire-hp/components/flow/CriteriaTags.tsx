"use client";

import { Pencil } from "lucide-react";

interface CriterionItem {
  label: string;
  value: string;
}

interface CriteriaTagsProps {
  essentialCriteria?: CriterionItem[];
  secondaryCriteria?: CriterionItem[];
  // Legacy support
  criteria?: string[];
  onModify?: () => void;
}

const CriteriaTags = ({
  essentialCriteria,
  secondaryCriteria,
  criteria,
  onModify
}: CriteriaTagsProps) => {
  // Legacy mode: if only criteria is provided, use old display
  if (criteria && !essentialCriteria && !secondaryCriteria) {
    return (
      <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
        <span className="text-xs sm:text-sm text-muted-foreground">Critères :</span>
        <div className="flex flex-wrap items-center gap-1 sm:gap-2">
          {criteria.map((criterion, index) => (
            <span key={index} className="inline-flex items-center">
              <span className="inline-flex items-center rounded-full bg-secondary px-2 py-0.5 sm:px-3 sm:py-1 text-xs sm:text-sm font-medium text-secondary-foreground">
                {criterion}
              </span>
              {index < criteria.length - 1 && (
                <span className="ml-1 sm:ml-2 text-muted-foreground hidden sm:inline">•</span>
              )}
            </span>
          ))}
        </div>
        {onModify && (
          <button
            onClick={onModify}
            className="ml-1 sm:ml-2 inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-2.5 py-1 sm:px-3 sm:py-1.5 text-xs sm:text-sm font-medium text-primary hover:bg-primary/20 transition-colors"
          >
            <Pencil className="h-3 w-3 sm:h-3.5 sm:w-3.5" />
            <span className="hidden sm:inline">Modifier</span>
          </button>
        )}
      </div>
    );
  }

  // New mode: compact single line display
  return (
    <div className="flex items-center gap-2 overflow-x-auto pb-1">
      {/* Essential Criteria */}
      {essentialCriteria && essentialCriteria.length > 0 && (
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <span className="text-xs font-medium text-muted-foreground whitespace-nowrap">Ce qui compte vraiment :</span>
          {essentialCriteria.map((criterion, index) => (
            <span
              key={index}
              className="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary whitespace-nowrap"
            >
              {criterion.value}
            </span>
          ))}
        </div>
      )}

      {/* Separator */}
      {essentialCriteria && essentialCriteria.length > 0 && secondaryCriteria && secondaryCriteria.length > 0 && (
        <span className="text-muted-foreground/30 flex-shrink-0">|</span>
      )}

      {/* Secondary Criteria */}
      {secondaryCriteria && secondaryCriteria.length > 0 && (
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <span className="text-xs font-medium text-muted-foreground whitespace-nowrap">Les petits plus :</span>
          {secondaryCriteria.map((criterion, index) => (
            <span
              key={index}
              className="inline-flex items-center rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-700 whitespace-nowrap"
            >
              {criterion.value}
            </span>
          ))}
        </div>
      )}

      {/* Modify Button */}
      {onModify && (
        <button
          onClick={onModify}
          className="flex-shrink-0 inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary hover:bg-primary/20 transition-colors whitespace-nowrap"
        >
          <Pencil className="h-3 w-3" />
          Modifier
        </button>
      )}
    </div>
  );
};

export default CriteriaTags;
