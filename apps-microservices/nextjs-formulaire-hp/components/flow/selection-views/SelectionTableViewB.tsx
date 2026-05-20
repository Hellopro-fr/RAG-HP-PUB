'use client';

import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import {
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Loader2,
  Plus,
  ShieldCheck,
  X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useFlowStore } from '@/lib/stores/flow-store';
import { getProductImageUrl } from '@/lib/utils/image-url';
import { useTableScrollNav } from '@/hooks/useTableScrollNav';
import { Supplier } from '@/types';

interface SelectionTableViewBProps {
  selectedSuppliers: Supplier[];
  otherSuppliers: Supplier[];
  selectedIds: Set<string>;
  onToggle: (id: string) => void;
  onViewDetails: (id: string) => void;
}

const VISIBLE_SPECS_DEFAULT = 5;
const DESKTOP_COLUMN_WIDTH = 220;

/**
 * Vignette produit avec lazy-load horizontal (IntersectionObserver scoped au
 * conteneur scrollable passé en `scrollRootRef`) + spinner pendant le chargement
 * + fade-in opacity à l'arrivée + fallback silencieux sur erreur d'URL.
 *
 * Se positionne en `absolute inset-0` dans un conteneur parent positionné.
 */
function LazyThumbnail({
  src,
  alt,
  className,
  scrollRootRef,
}: {
  src: string;
  alt: string;
  className?: string;
  scrollRootRef?: RefObject<HTMLDivElement | null>;
}) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [inView, setInView] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (inView || !wrapperRef.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          observer.disconnect();
        }
      },
      { root: scrollRootRef?.current ?? null, rootMargin: '200px' }
    );
    observer.observe(wrapperRef.current);
    return () => observer.disconnect();
  }, [inView, scrollRootRef]);

  return (
    <div ref={wrapperRef} className="absolute inset-0">
      {inView && !error && (
        <img
          src={src}
          alt={alt}
          className={cn(
            'h-full w-full object-contain transition-opacity duration-300',
            loaded ? 'opacity-100' : 'opacity-0',
            className
          )}
          onLoad={() => setLoaded(true)}
          onError={() => setError(true)}
        />
      )}
      {(!inView || (inView && !loaded && !error)) && (
        <div className="absolute inset-0 flex items-center justify-center">
          <Loader2 className="h-5 w-5 text-muted-foreground animate-spin" />
        </div>
      )}
    </div>
  );
}

function formatPrice(supplier: Supplier): { prefix?: string; value: string } | null {
  if (supplier.priceLabel) {
    return { value: supplier.priceLabel };
  }
  if (supplier.price?.amount) {
    const formatted = `${new Intl.NumberFormat('fr-FR', {
      maximumFractionDigits: 0,
    }).format(supplier.price.amount)} € HT`;
    return supplier.price.isStartingFrom
      ? { prefix: 'à partir de', value: formatted }
      : { value: formatted };
  }
  return null;
}

export default function SelectionTableViewB({
  selectedSuppliers,
  otherSuppliers,
  selectedIds,
  onToggle,
  onViewDetails,
}: SelectionTableViewBProps) {
  const { removedCritiqueCriteriaIds, removedSecondaireCriteriaIds } = useFlowStore();

  const products = useMemo<Supplier[]>(
    () => [...selectedSuppliers, ...otherSuppliers],
    [selectedSuppliers, otherSuppliers]
  );

  const removedIdsSet = useMemo(
    () => new Set([...removedCritiqueCriteriaIds, ...removedSecondaireCriteriaIds]),
    [removedCritiqueCriteriaIds, removedSecondaireCriteriaIds]
  );

  const allSpecLabels = useMemo<string[]>(
    () =>
      Array.from(
        new Set(
          products.flatMap((p) =>
            p.specs
              .filter(
                (s) =>
                  !!s.label &&
                  (!s.id_caracteristique || !removedIdsSet.has(s.id_caracteristique))
              )
              .map((s) => s.label)
          )
        )
      ),
    [products, removedIdsSet]
  );

  const [isExpanded, setIsExpanded] = useState(false);
  const [currentPairIndex, setCurrentPairIndex] = useState(0);
  const tableScrollRef = useRef<HTMLDivElement | null>(null);
  const { canScrollLeft, canScrollRight } = useTableScrollNav(tableScrollRef);

  const visibleSpecLabels = useMemo(
    () => (isExpanded ? allSpecLabels : allSpecLabels.slice(0, VISIBLE_SPECS_DEFAULT)),
    [isExpanded, allSpecLabels]
  );
  const hiddenSpecsCount = Math.max(0, allSpecLabels.length - VISIBLE_SPECS_DEFAULT);

  const totalPairs = Math.max(1, Math.ceil(products.length / 2));
  const pairStart = currentPairIndex * 2;
  const pairProducts = products.slice(pairStart, pairStart + 2);

  const goToPrevPair = useCallback(() => {
    setCurrentPairIndex((i) => Math.max(0, i - 1));
  }, []);
  const goToNextPair = useCallback(() => {
    setCurrentPairIndex((i) => Math.min(totalPairs - 1, i + 1));
  }, [totalPairs]);

  const scrollTable = useCallback((direction: 1 | -1) => {
    const el = tableScrollRef.current;
    if (!el) return;
    el.scrollBy({ left: direction * DESKTOP_COLUMN_WIDTH, behavior: 'smooth' });
  }, []);

  const getSpecValue = (product: Supplier, label: string) =>
    product.specs.find((s) => s.label === label) ?? null;

  const renderSelectionButton = (product: Supplier, size: 'mobile' | 'desktop') => {
    const isSelected = selectedIds.has(product.id);
    return (
      <button
        type="button"
        onClick={() => onToggle(product.id)}
        className={cn(
          'w-full flex items-center justify-center gap-1.5 rounded-md font-semibold transition-colors border',
          size === 'mobile' ? 'h-8 px-1.5 py-1.5 text-[11px]' : 'h-9 px-2.5 py-2 text-xs',
          isSelected
            ? 'bg-primary text-primary-foreground border-primary shadow-sm hover:bg-primary/90'
            : 'border-primary/40 bg-primary/5 text-primary hover:bg-primary/10'
        )}
      >
        {isSelected ? (
          <>
            <Check className={size === 'mobile' ? 'h-3 w-3' : 'h-3.5 w-3.5'} />
            Sélectionné
          </>
        ) : (
          <>
            <Plus className={size === 'mobile' ? 'h-3 w-3' : 'h-3.5 w-3.5'} />
            Ajouter
          </>
        )}
      </button>
    );
  };

  const renderPriceCell = (product: Supplier, compact: boolean) => {
    const formatted = formatPrice(product);
    if (!formatted) {
      return (
        <span className={cn('text-muted-foreground', compact ? 'text-[10px]' : 'text-xs')}>
          Prix sur demande
        </span>
      );
    }
    return (
      <div className={cn(compact ? 'text-sm' : 'text-sm')}>
        {formatted.prefix && (
          <span className={cn('text-muted-foreground mr-1', compact ? 'text-[10px]' : 'text-xs')}>
            {formatted.prefix}
          </span>
        )}
        <span className="font-bold text-foreground">{formatted.value}</span>
      </div>
    );
  };

  const renderSpecCell = (product: Supplier, label: string, compact: boolean) => {
    const spec = getSpecValue(product, label);
    if (!spec) {
      return <span className="text-muted-foreground text-xs">—</span>;
    }
    if (spec.matches === false) {
      return (
        <div className="flex flex-col items-center gap-0.5">
          <div className="flex items-center gap-1.5">
            <X className={cn('text-amber-600 flex-shrink-0 mt-0.5', compact ? 'h-3 w-3' : 'h-4 w-4')} />
            <span className={cn('text-amber-700 font-medium', compact ? 'text-[11px]' : 'text-sm')}>
              {spec.value}
            </span>
          </div>
          {spec.expected && (
            <span className={cn('text-amber-600 leading-tight', compact ? 'text-[9px]' : 'text-[11px]')}>
              (demandé : {spec.expected})
            </span>
          )}
        </div>
      );
    }
    return (
      <div className="flex items-center gap-1.5 justify-center">
        {spec.matches === true && (
          <Check className={cn('text-match-high flex-shrink-0 mt-0.5', compact ? 'h-3 w-3' : 'h-4 w-4')} />
        )}
        <span className={cn('text-foreground', compact ? 'text-[11px]' : 'text-sm')}>
          {spec.value}
        </span>
      </div>
    );
  };

  // Empty state
  if (products.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-card p-10 text-center text-muted-foreground">
        Aucun produit à afficher.
      </div>
    );
  }

  return (
    <div className="space-y-4 sm:space-y-8">
      {/* ============== MOBILE ============== */}
      <div className="md:hidden">
        <div className="relative rounded-xl border border-border bg-card">
          {/* Pagination header */}
          <div className="px-3 py-2 bg-muted/30 border-b border-border flex items-center justify-between rounded-t-xl">
            <span className="text-[11px] font-medium text-muted-foreground tabular-nums">
              {pairStart + 1}
              {pairProducts.length > 1 ? `–${pairStart + pairProducts.length}` : ''} sur {products.length}
            </span>
            <div className="flex items-center gap-1 overflow-x-auto scrollbar-hide">
              {Array.from({ length: totalPairs }).map((_, idx) => (
                <button
                  key={idx}
                  type="button"
                  aria-label={`Aller à la page ${idx + 1}`}
                  onClick={() => setCurrentPairIndex(idx)}
                  className={cn(
                    'h-1.5 rounded-full transition-all flex-shrink-0',
                    idx === currentPairIndex ? 'w-4 bg-primary' : 'w-1.5 bg-muted-foreground/30'
                  )}
                />
              ))}
            </div>
          </div>

          {/* Sticky product header (image + name) */}
          <div className="sticky top-0 z-30 bg-card border-b border-border grid grid-cols-2 divide-x divide-border shadow-sm">
            {pairProducts.map((product) => {
              const isSelected = selectedIds.has(product.id);
              return (
                <div
                  key={product.id}
                  className={cn(
                    'flex flex-col p-2 transition-colors relative',
                    isSelected && 'bg-primary/[0.08]'
                  )}
                >
                  {isSelected && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onToggle(product.id);
                      }}
                      aria-label={`Désélectionner ${product.productName}`}
                      className="absolute top-1 right-1 z-10 h-5 w-5 rounded-full bg-primary text-primary-foreground flex items-center justify-center shadow cursor-pointer hover:bg-primary/90 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1"
                    >
                      <Check className="h-3 w-3" />
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => onViewDetails(product.id)}
                    className="relative w-full h-20 overflow-hidden rounded-md bg-muted"
                  >
                    <LazyThumbnail
                      src={getProductImageUrl(product.image)}
                      alt={product.productName}
                      className="p-1"
                    />
                  </button>
                  <button
                    type="button"
                    onClick={() => onViewDetails(product.id)}
                    className="text-left mt-1.5 h-8"
                  >
                    <h4 className="font-semibold text-foreground text-[11px] leading-tight line-clamp-2">
                      {product.productName}
                    </h4>
                  </button>
                </div>
              );
            })}
            {pairProducts.length === 1 && <div aria-hidden="true" />}
          </div>

          {/* Supplier + price + selection button */}
          <div className="grid grid-cols-2 border-b border-border divide-x divide-border">
            {pairProducts.map((product) => {
              const isSelected = selectedIds.has(product.id);
              return (
                <div
                  key={product.id}
                  className={cn(
                    'flex flex-col p-2 pt-1 transition-colors',
                    isSelected && 'bg-primary/[0.08]'
                  )}
                >
                  <p className="text-[10px] text-muted-foreground truncate h-3.5">
                    {product.supplierName}
                  </p>
                  <div className="h-5 mt-1 flex items-center">
                    {renderPriceCell(product, true)}
                  </div>
                  <div className="mt-2">{renderSelectionButton(product, 'mobile')}</div>
                  <button
                    type="button"
                    onClick={() => onViewDetails(product.id)}
                    className="text-[10px] text-primary hover:underline inline-flex items-center justify-center gap-0.5 h-5 mt-1"
                  >
                    Voir détails <ChevronRight className="h-3 w-3" />
                  </button>
                </div>
              );
            })}
            {pairProducts.length === 1 && <div aria-hidden="true" />}
          </div>

          {/* Specs rows */}
          <div className="divide-y divide-border">
            {/* Système : Fournisseur certifié */}
            <div className="px-3 py-2">
              <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-1.5">
                Fournisseur certifié
              </div>
              <div className="grid grid-cols-2 gap-2 items-center">
                {pairProducts.map((product) => (
                  <div key={product.id} className="flex justify-center">
                    {product.isCertified ? (
                      <ShieldCheck className="h-4 w-4 text-match-high" />
                    ) : (
                      <span className="text-muted-foreground text-xs">—</span>
                    )}
                  </div>
                ))}
                {pairProducts.length === 1 && <div aria-hidden="true" />}
              </div>
            </div>

            {/* Specs dynamiques */}
            {visibleSpecLabels.map((label) => (
              <div key={label} className="px-3 py-2">
                <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-1.5">
                  {label}
                </div>
                <div className="grid grid-cols-2 gap-2 items-start">
                  {pairProducts.map((product) => (
                    <div key={product.id} className="flex justify-center">
                      {renderSpecCell(product, label, true)}
                    </div>
                  ))}
                  {pairProducts.length === 1 && <div aria-hidden="true" />}
                </div>
              </div>
            ))}
          </div>

          {/* Voir plus toggle (mobile) */}
          {hiddenSpecsCount > 0 && (
            <button
              type="button"
              onClick={() => setIsExpanded((v) => !v)}
              className="w-full flex items-center justify-center gap-1.5 py-3 text-sm font-medium text-primary hover:bg-muted/40 transition-colors rounded-b-xl border-t border-border"
            >
              {isExpanded ? (
                <>
                  Voir moins <ChevronUp className="h-4 w-4" />
                </>
              ) : (
                <>
                  Voir plus de caractéristiques ({hiddenSpecsCount}) <ChevronDown className="h-4 w-4" />
                </>
              )}
            </button>
          )}
        </div>

        {/* Floating prev/next (mobile) */}
        <button
          type="button"
          aria-label="Produits précédents"
          disabled={currentPairIndex === 0}
          onClick={goToPrevPair}
          className="fixed left-3 top-1/2 -translate-y-1/2 z-40 h-12 w-12 rounded-full bg-primary text-primary-foreground shadow-lg flex items-center justify-center active:scale-95 transition-transform disabled:opacity-40 disabled:cursor-not-allowed md:hidden"
        >
          <ChevronLeft className="h-6 w-6" />
        </button>
        <button
          type="button"
          aria-label="Produits suivants"
          disabled={currentPairIndex >= totalPairs - 1}
          onClick={goToNextPair}
          className="fixed right-3 top-1/2 -translate-y-1/2 z-40 h-12 w-12 rounded-full bg-primary text-primary-foreground shadow-lg flex items-center justify-center active:scale-95 transition-transform disabled:opacity-40 disabled:cursor-not-allowed md:hidden"
        >
          <ChevronRight className="h-6 w-6" />
        </button>
      </div>

      {/* ============== DESKTOP ============== */}
      <div
        className="hidden md:block relative rounded-xl border border-border bg-card mx-auto"
        style={{ maxWidth: 1170 }}
      >
        <div
          ref={tableScrollRef}
          className="overflow-x-auto scroll-smooth [overflow-y:visible] [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]"
        >
          <table className="w-full border-collapse">
            <thead>
              {/* Row 1: image + name */}
              <tr>
                <th className="bg-card border-r border-border p-3 text-left align-bottom sticky left-0 top-0 z-40 min-w-[180px] w-[180px]">
                  <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Caractéristiques
                  </span>
                </th>
                {products.map((product) => {
                  const isSelected = selectedIds.has(product.id);
                  return (
                    <th
                      key={product.id}
                      className="border-l border-border p-3 pb-2 align-top sticky top-0 z-20 bg-card min-w-[220px] w-[220px]"
                    >
                      {isSelected && (
                        <div className="absolute inset-0 bg-primary/[0.07] pointer-events-none" />
                      )}
                      <div className="relative flex flex-col">
                        <button
                          type="button"
                          onClick={() => onViewDetails(product.id)}
                          className="relative w-full h-40 overflow-hidden rounded-lg bg-muted group"
                        >
                          <LazyThumbnail
                            src={getProductImageUrl(product.image)}
                            alt={product.productName}
                            className="p-2 transition-transform duration-300 group-hover:scale-105"
                            scrollRootRef={tableScrollRef}
                          />
                        </button>
                        <button
                          type="button"
                          onClick={() => onViewDetails(product.id)}
                          className="text-left mt-2 h-10"
                        >
                          <h4 className="font-semibold text-foreground text-sm leading-tight line-clamp-2 hover:text-primary transition-colors">
                            {product.productName}
                          </h4>
                        </button>
                      </div>
                    </th>
                  );
                })}
              </tr>
              {/* Row 2: supplier + price + button + voir détails */}
              <tr>
                <th className="bg-card border-b-2 border-r border-border p-0 sticky left-0 z-30 min-w-[180px] w-[180px]" />
                {products.map((product) => {
                  const isSelected = selectedIds.has(product.id);
                  return (
                    <th
                      key={product.id}
                      className={cn(
                        'border-b-2 border-l border-border p-3 pt-1 align-top relative min-w-[220px] w-[220px]',
                        isSelected ? 'bg-primary/[0.07]' : 'bg-card'
                      )}
                    >
                      {isSelected && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onToggle(product.id);
                          }}
                          aria-label={`Désélectionner ${product.productName}`}
                          className="absolute top-1 right-2 z-10 h-6 w-6 rounded-full bg-primary text-primary-foreground flex items-center justify-center shadow cursor-pointer hover:bg-primary/90 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1"
                        >
                          <Check className="h-3.5 w-3.5" />
                        </button>
                      )}
                      <div className="flex flex-col">
                        <p className="text-xs text-muted-foreground truncate h-4 mt-1">
                          {product.supplierName}
                        </p>
                        <div className="h-6 mt-2 flex items-center">
                          {renderPriceCell(product, false)}
                        </div>
                        <div className="mt-2">{renderSelectionButton(product, 'desktop')}</div>
                        <button
                          type="button"
                          onClick={() => onViewDetails(product.id)}
                          className="text-[11px] text-primary hover:underline inline-flex items-center justify-center gap-0.5 h-6 mt-1"
                        >
                          Voir détails <ChevronRight className="h-3 w-3" />
                        </button>
                      </div>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {/* Système : Fournisseur certifié */}
              <tr className="border-b border-border">
                <td className="bg-muted border-r border-border p-3 text-sm font-medium text-foreground sticky left-0 z-10 min-w-[180px] w-[180px]">
                  Fournisseur certifié
                </td>
                {products.map((product) => (
                  <td
                    key={product.id}
                    className={cn(
                      'border-l border-border p-3 text-center align-middle min-w-[220px] w-[220px]',
                      selectedIds.has(product.id) && 'bg-primary/5'
                    )}
                  >
                    {product.isCertified ? (
                      <ShieldCheck className="h-4 w-4 text-match-high mx-auto" />
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                ))}
              </tr>

              {/* Specs dynamiques */}
              {visibleSpecLabels.map((label) => (
                <tr key={label} className="border-b border-border last:border-b-0">
                  <td className="bg-muted border-r border-border p-3 text-sm font-medium text-foreground sticky left-0 z-10 min-w-[180px] w-[180px]">
                    {label}
                  </td>
                  {products.map((product) => (
                    <td
                      key={product.id}
                      className={cn(
                        'border-l border-border p-3 text-center text-sm align-top min-w-[220px] w-[220px]',
                        selectedIds.has(product.id) && 'bg-primary/5'
                      )}
                    >
                      {renderSpecCell(product, label, false)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Voir plus toggle (desktop) */}
        {hiddenSpecsCount > 0 && (
          <div className="border-t border-border bg-card">
            <button
              type="button"
              onClick={() => setIsExpanded((v) => !v)}
              className="w-full flex items-center justify-center gap-1.5 py-3 text-sm font-medium text-primary hover:bg-muted/40 transition-colors rounded-b-xl"
            >
              {isExpanded ? (
                <>
                  Voir moins <ChevronUp className="h-4 w-4" />
                </>
              ) : (
                <>
                  Voir plus de caractéristiques ({hiddenSpecsCount}) <ChevronDown className="h-4 w-4" />
                </>
              )}
            </button>
          </div>
        )}

        {/* Floating prev/next (desktop) — auto-hide aux bords */}
        {canScrollLeft && (
          <button
            type="button"
            aria-label="Produits précédents"
            onClick={() => scrollTable(-1)}
            className="absolute left-2 top-1/2 -translate-y-1/2 z-30 h-11 w-11 rounded-full bg-primary/90 backdrop-blur-sm text-primary-foreground shadow-lg flex items-center justify-center hover:scale-105 active:scale-95 transition-all"
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
        )}
        {canScrollRight && (
          <button
            type="button"
            aria-label="Produits suivants"
            onClick={() => scrollTable(1)}
            className="absolute right-2 top-1/2 -translate-y-1/2 z-30 h-11 w-11 rounded-full bg-primary/90 backdrop-blur-sm text-primary-foreground shadow-lg flex items-center justify-center hover:scale-105 active:scale-95 transition-all"
          >
            <ChevronRight className="h-5 w-5" />
          </button>
        )}
      </div>
    </div>
  );
}
