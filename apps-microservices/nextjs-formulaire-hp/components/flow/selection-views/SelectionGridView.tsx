'use client';

import { useState } from 'react';
import { ChevronDown, ChevronUp, RotateCcw } from 'lucide-react';
import { cn } from '@/lib/utils';
import SupplierCard from '@/components/flow/SupplierCard';
import WarningBanner from '@/components/flow/WarningBanner';
import { getCategorySelection } from '@/data/category-static-content';
import { Supplier } from '@/types';

interface CategoryStats {
  productsCount?: number;
}

interface SelectionGridViewProps {
  selectedSuppliersList: Supplier[];
  unselectedSuppliersList: Supplier[];
  searchQuery: string;
  isModified: boolean;
  resetSelection: () => void;
  onToggle: (id: string) => void;
  onViewDetails: (id: string) => void;
  categoryId?: number | null;
  categoryName?: string | null;
  categoryStats?: CategoryStats | null;
}

export default function SelectionGridView({
  selectedSuppliersList,
  unselectedSuppliersList,
  searchQuery,
  isModified,
  resetSelection,
  onToggle,
  onViewDetails,
  categoryId,
  categoryName,
  categoryStats,
}: SelectionGridViewProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [mobileViewMode] = useState<'grid' | 'list'>('list');

  const categorySelection = categoryId ? getCategorySelection(categoryId) : undefined;

  return (
    <>
      {/* Warning Banner (only when expanded and modified) */}
      {isExpanded && isModified && (
        <WarningBanner message="En modifiant notre sélection, vous risquez de passer à côté des fournisseurs les plus adaptés à votre besoin." />
      )}

      {/* Supplier Lists */}
      <div className="space-y-6">
        {/* When collapsed: show only selected suppliers */}
        {!isExpanded && (
          <div className={cn(
            'grid gap-4 sm:gap-5',
            'grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4'
          )}>
            {selectedSuppliersList.map((supplier) => (
              <SupplierCard
                key={supplier.id}
                {...supplier}
                isSelected={true}
                onToggle={onToggle}
                onViewDetails={onViewDetails}
                viewMode={mobileViewMode}
              />
            ))}
          </div>
        )}

        {/* When expanded: show all with sections */}
        {isExpanded && (
          <>
            {/* Selected Section */}
            <div className="space-y-4">
              <h3 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                <span className="h-px flex-1 bg-border" />
                Produits sélectionnés ({selectedSuppliersList.length})
                <span className="h-px flex-1 bg-border" />
              </h3>
              {selectedSuppliersList.length > 0 ? (
                <div className={cn(
                  'grid gap-4 sm:gap-5',
                  'grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4'
                )}>
                  {selectedSuppliersList.map((supplier) => (
                    <SupplierCard
                      key={supplier.id}
                      {...supplier}
                      isSelected={true}
                      onToggle={onToggle}
                      onViewDetails={onViewDetails}
                      viewMode={mobileViewMode}
                    />
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  <p>Aucun produit sélectionné</p>
                </div>
              )}
            </div>

            {/* Other Results Section */}
            <div className="space-y-4 pt-4">
              <h3 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                <span className="h-px flex-1 bg-border" />
                Autres résultats ({unselectedSuppliersList.length})
                <span className="h-px flex-1 bg-border" />
              </h3>

              {unselectedSuppliersList.length > 0 ? (
                <div className={cn(
                  'grid gap-4 sm:gap-5',
                  'grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4'
                )}>
                  {unselectedSuppliersList.map((supplier) => (
                    <SupplierCard
                      key={supplier.id}
                      {...supplier}
                      isSelected={false}
                      onToggle={onToggle}
                      onViewDetails={onViewDetails}
                      viewMode={mobileViewMode}
                    />
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  {searchQuery ? (
                    <p>Aucun résultat pour "{searchQuery}"</p>
                  ) : (
                    <p>Tous les produits sont sélectionnés</p>
                  )}
                </div>
              )}
            </div>

            {/* Reset link */}
            {isModified && (
              <button
                onClick={() => {
                  resetSelection();
                  setIsExpanded(false);
                }}
                className="flex w-full items-center justify-center gap-2 py-2 text-sm text-primary hover:text-primary/80 transition-colors"
              >
                <RotateCcw className="h-4 w-4" />
                Revenir à la sélection recommandée
              </button>
            )}
          </>
        )}

        {/* Expand/Collapse toggle */}
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className={cn(
            'flex w-full items-center justify-center gap-2 py-3 text-sm transition-colors rounded-lg border',
            isExpanded
              ? 'text-muted-foreground hover:text-foreground border-transparent'
              : 'text-foreground font-medium border-border hover:bg-muted'
          )}
        >
          {isExpanded ? (
            <>
              Réduire
              <ChevronUp className="h-4 w-4" />
            </>
          ) : (
            <>
              {categorySelection?.voirPlus || `Voir plus de ${(categoryName || 'produits').toLowerCase()}`}
              <ChevronDown className="h-4 w-4" />
            </>
          )}
        </button>
      </div>

      {/* Bloc réassurance "Recommandé" */}
      {categorySelection?.recommandeReassurance && (
        <div className="mt-4 rounded-lg border border-border bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
          <span className="font-semibold text-foreground">Idéal</span> = {categorySelection.recommandeReassurance.replace(/xx/g, String(categoryStats?.productsCount ?? ''))}
        </div>
      )}
    </>
  );
}
