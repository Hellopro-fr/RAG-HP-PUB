'use client';

import { Check, CheckCircle, AlertTriangle, ShieldCheck, HelpCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ProductSpec, PriceInfo } from "@/types";

interface SupplierCardProps {
  id: string;
  productName: string;
  supplierName: string;
  rating: number;
  distance: number;
  matchScore: number;
  image: string;
  description?: string;
  specs?: ProductSpec[];
  isRecommended?: boolean;
  isCertified?: boolean;
  isSelected: boolean;
  onToggle: (id: string) => void;
  onViewDetails?: (id: string) => void;
  matchGaps?: string[];
  viewMode?: "grid" | "list";
  price?: PriceInfo;
}

// Format price with French locale
const formatPrice = (amount: number): string => {
  return new Intl.NumberFormat('fr-FR', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount) + ' € HT';
};

// Price display component
const PriceDisplay = ({ price }: { price?: PriceInfo }) => {
  if (!price || price.amount === undefined || price.amount === null) {
    return (
      <span className="text-muted-foreground text-sm">
        Prix sur demande
      </span>
    );
  }

  if (price.isStartingFrom) {
    return (
      <span className="text-sm">
        <span className="text-muted-foreground">À partir de </span>
        <span className="font-semibold text-foreground">{formatPrice(price.amount)}</span>
      </span>
    );
  }

  return (
    <span className="text-sm font-semibold text-foreground">
      {formatPrice(price.amount)}
    </span>
  );
};

const SupplierCard = ({
  id,
  productName,
  matchScore,
  image,
  specs = [],
  isRecommended = false,
  isCertified = false,
  isSelected,
  onToggle,
  onViewDetails,
  matchGaps = [],
  viewMode = "grid",
  price,
}: SupplierCardProps) => {
  
  const getMatchBadgeStyle = () => {
    if (matchScore >= 80) return "bg-match-high text-white";
    if (matchScore >= 60) return "bg-match-medium text-white";
    return "bg-match-low text-white";
  };

  const handleCardClick = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('.checkbox-area')) {
      return;
    }
    onViewDetails?.(id);
  };

  const handleCheckboxClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onToggle(id);
  };

  const matchingSpecs = specs.filter((spec) => spec.matches === true);
  const nonMatchingSpecs = specs.filter((spec) => spec.matches === false);
  const unknownSpecs = specs.filter((spec) => spec.matches === undefined || spec.matches === null);
  const isMobileList = viewMode === "list";
  
  // Calculate total gaps (non-matching specs or matchGaps)
  const totalGaps = nonMatchingSpecs.length > 0 ? nonMatchingSpecs.length : matchGaps.length;

  // Mobile List View
  const mobileListView = isMobileList ? (
    <div
      className={cn(
        "group relative flex rounded-xl border overflow-hidden transition-all duration-200 cursor-pointer sm:hidden",
        isSelected
          ? "border-primary bg-primary/5 shadow-md ring-2 ring-primary/20"
          : "border-border bg-card hover:border-primary/40 hover:shadow-md"
      )}
      onClick={handleCardClick}
    >
      {/* Image */}
      <div className="relative w-24 h-24 flex-shrink-0 overflow-hidden bg-muted">
        <img
          src={image}
          alt={productName}
          className="h-full w-full object-cover"
        />
        {isRecommended && (
          <div className="absolute top-1 left-1">
            <span className="rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold text-primary-foreground">
              Top
            </span>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 p-3 flex flex-col justify-between min-w-0">
        <div>
          <h4 className="font-semibold text-foreground text-sm leading-tight line-clamp-2">
            {productName}
          </h4>
          <div className="flex items-center gap-3 mt-1.5">
            <span className={cn(
              "rounded px-1.5 py-0.5 font-bold text-xs",
              getMatchBadgeStyle()
            )}>
              {matchScore}%
            </span>
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className={matchingSpecs.length > 0 ? "text-match-high" : "text-muted-foreground"}>
                {matchingSpecs.length}/{specs.length} ✓
              </span>
              {totalGaps > 0 && (
                <span className="text-amber-600">{totalGaps} écart{totalGaps > 1 ? 's' : ''}</span>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center justify-between mt-2">
          <PriceDisplay price={price} />
        </div>
      </div>

      {/* Checkbox */}
      <div
        className="checkbox-area absolute top-2 right-2 z-10"
        onClick={handleCheckboxClick}
      >
        <div
          className={cn(
            "flex h-6 w-6 items-center justify-center rounded-lg border-2 transition-all duration-200 shadow-sm",
            isSelected
              ? "border-primary bg-primary"
              : "border-muted-foreground/30 bg-background/90 backdrop-blur-sm"
          )}
        >
          {isSelected && (
            <Check className="h-3.5 w-3.5 text-primary-foreground animate-check-bounce" />
          )}
        </div>
      </div>
    </div>
  ) : null;

  // Grid view component (desktop) - with fixed height sections for alignment
  const gridView = (
    <div
      className={cn(
        "group relative flex flex-col rounded-xl border overflow-hidden transition-all duration-200 cursor-pointer h-full",
        isMobileList ? "hidden sm:flex" : "flex",
        isSelected
          ? "border-primary bg-primary/5 shadow-md ring-2 ring-primary/20"
          : "border-border bg-card hover:border-primary/40 hover:shadow-md"
      )}
      onClick={handleCardClick}
    >
      {/* Checkbox */}
      <div
        className="checkbox-area absolute top-3 right-3 z-10"
        onClick={handleCheckboxClick}
      >
        <div
          className={cn(
            "flex h-7 w-7 items-center justify-center rounded-lg border-2 transition-all duration-200 shadow-sm",
            isSelected
              ? "border-primary bg-primary"
              : "border-muted-foreground/30 bg-background/90 backdrop-blur-sm group-hover:border-primary/50"
          )}
        >
          {isSelected && (
            <Check className="h-4 w-4 text-primary-foreground animate-check-bounce" />
          )}
        </div>
      </div>

      {/* Recommended Badge */}
      {isRecommended && (
        <div className="absolute top-3 left-3 z-10">
          <span className="rounded-full bg-primary px-2.5 py-1 text-xs font-semibold text-primary-foreground shadow-sm">
            Recommandé
          </span>
        </div>
      )}

      {/* Product Image - Fixed height */}
      <div className="relative h-32 sm:h-36 w-full overflow-hidden bg-muted flex-shrink-0">
        <img
          src={image}
          alt={productName}
          className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
        />
        {/* Match Score Badge */}
        <div className={cn(
          "absolute bottom-2 right-2 rounded-lg px-2.5 py-1 font-bold text-sm shadow-lg",
          getMatchBadgeStyle()
        )}>
          {matchScore}%
        </div>
      </div>

      {/* Content - Structured with fixed heights for alignment */}
      <div className="flex flex-1 flex-col p-4">
        {/* Title - Fixed height with line-clamp */}
        <div className="h-10 mb-2">
          <h4 className="font-semibold text-foreground text-sm leading-tight line-clamp-2">
            {productName}
          </h4>
        </div>

        {/* Price - Fixed height */}
        <div className="h-6 mb-3 flex items-center">
          <PriceDisplay price={price} />
        </div>

        {/* Criteria Match - Prominent display */}
        <div className="h-8 mb-2 flex items-center">
          <div className={cn(
            "flex items-center gap-2 rounded-lg px-2.5 py-1.5",
            matchingSpecs.length > 0
              ? "bg-match-high/10"
              : "bg-muted"
          )}>
            <CheckCircle className={cn(
              "h-4 w-4",
              matchingSpecs.length > 0
                ? "text-match-high"
                : "text-muted-foreground"
            )} />
            <span className={cn(
              "text-sm font-medium",
              matchingSpecs.length > 0
                ? "text-match-high"
                : "text-muted-foreground"
            )}>
              {matchingSpecs.length}/{specs.length} critères OK
            </span>
          </div>
        </div>

        {/* Gaps + Unknown - More discrete */}
        <div className="flex items-center gap-3 text-xs text-muted-foreground mb-1">
          {totalGaps > 0 && (
            <div className="flex items-center gap-1 opacity-70">
              <AlertTriangle className="h-3 w-3 text-amber-500" />
              <span>{totalGaps} écart{totalGaps > 1 ? 's' : ''}</span>
            </div>
          )}
          {unknownSpecs.length > 0 && (
            <div className="flex items-center gap-1 opacity-70">
              <HelpCircle className="h-3 w-3" />
              <span>{unknownSpecs.length} N/A</span>
            </div>
          )}
        </div>

        {/* Gap details - Orange style with expected value */}
        <div className="hidden sm:flex items-center justify-between mb-1">
          {totalGaps > 0 ? (
            <>
              <div className="flex flex-wrap gap-1 overflow-hidden flex-1">
                {(nonMatchingSpecs.length > 0 ? nonMatchingSpecs : matchGaps).slice(0, 1).map((item, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center rounded bg-amber-50 border border-amber-200/50 px-1.5 py-0.5 text-[10px] text-amber-700"
                  >
                    {typeof item === 'string' 
                      ? item 
                      : (
                        <>
                          {item.label}: {item.value}
                          {item.expected && (
                            <span className="text-amber-500 ml-1">(demandé: {item.expected})</span>
                          )}
                        </>
                      )
                    }
                  </span>
                ))}
              </div>
              {(nonMatchingSpecs.length > 1 || matchGaps.length > 1) && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onViewDetails?.(id);
                  }}
                  className="text-[10px] text-amber-600 hover:text-amber-800 transition-colors ml-2 flex-shrink-0"
                >
                  +{Math.max(nonMatchingSpecs.length, matchGaps.length) - 1}
                </button>
              )}
            </>
          ) : <div className="h-4" />}
        </div>

        {/* Certified Badge - Fixed height at bottom */}
        <div className="h-6 mt-auto flex items-center">
          {isCertified && (
            <div className="inline-flex items-center gap-1 text-xs text-primary">
              <ShieldCheck className="h-3.5 w-3.5" />
              <span>Certifié</span>
            </div>
          )}
        </div>
      </div>

      {/* View Details Footer */}
      <div className="border-t border-border px-4 py-2.5 text-center bg-muted/30 flex-shrink-0">
        <span className="text-xs font-medium text-primary group-hover:underline">
          Voir détails →
        </span>
      </div>
    </div>
  );

  return (
    <>
      {mobileListView}
      {gridView}
    </>
  );
};

export default SupplierCard;
