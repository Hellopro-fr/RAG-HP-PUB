"use client";

import { X, Check, Plus, Minus, ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { useState, useCallback, useMemo } from "react";
import type { ProductSpec, Supplier } from "@/types";
import { useFlowStore } from "@/lib/stores/flow-store";
import { getProductImageUrl } from "@/lib/utils/image-url";

interface ProductComparisonModalProps {
  products: Supplier[];
  selectedIds: Set<string>;
  onToggle: (id: string) => void;
  onClose: () => void;
}

const ProductComparisonModal = ({
  products,
  selectedIds,
  onToggle,
  onClose,
}: ProductComparisonModalProps) => {
  const [currentProductIndex, setCurrentProductIndex] = useState(0);

  // Récupérer les IDs des critères supprimés depuis le store
  const { removedCritiqueCriteriaIds, removedSecondaireCriteriaIds } = useFlowStore();

  // Créer un Set des IDs supprimés pour filtrage rapide
  const removedIdsSet = useMemo(
    () => new Set([...removedCritiqueCriteriaIds, ...removedSecondaireCriteriaIds]),
    [removedCritiqueCriteriaIds, removedSecondaireCriteriaIds]
  );

  // Collecter tous les labels uniques des critères demandés (isRequested: true)
  // en excluant les critères supprimés
  const allSpecLabels: string[] = useMemo(() => Array.from(
    new Set(
      products.flatMap((p) =>
        p.specs
          .filter((s) => s.isRequested && (!s.id_caracteristique || !removedIdsSet.has(s.id_caracteristique)))
          .map((s) => s.label)
      )
    )
  ), [products, removedIdsSet]);

  const getSpecValue = (product: Supplier, label: string) => {
    const spec = product.specs.find((s) => s.label === label);
    return spec || null;
  };

  const currentProduct = products[currentProductIndex];

  const goToPrevious = useCallback(() => {
    setCurrentProductIndex((prev) => (prev > 0 ? prev - 1 : products.length - 1));
  }, [products.length]);

  const goToNext = useCallback(() => {
    setCurrentProductIndex((prev) => (prev < products.length - 1 ? prev + 1 : 0));
  }, [products.length]);

  // Mobile card view for a single product
  const MobileProductCard = ({ product }: { product: Supplier }) => (
    <div className="flex flex-col gap-4">
      {/* Product header */}
      <div className="relative flex flex-col items-center gap-3 rounded-xl bg-card border border-border p-4">
        {/* Badge top-left */}
        <span
          className={cn(
            "absolute top-3 left-3 rounded-full px-2.5 py-1 text-xs font-semibold text-white shadow-sm",
            product.matchScore >= 80
              ? "bg-match-high"
              : product.matchScore >= 60
              ? "bg-match-medium"
              : "invisible"
          )}
        >
          {product.matchScore >= 80 ? "Idéal" : "À considérer"}
        </span>
        <div className="h-24 w-24 overflow-hidden rounded-lg bg-muted">
          <img
            src={getProductImageUrl(product.image)}
            alt={product.productName}
            loading="lazy"
            className="h-full w-full object-contain"
          />
        </div>
        <div className="text-center">
          <p className="font-semibold text-foreground">{product.productName}</p>
          <p className="text-sm text-muted-foreground">{product.supplierName}</p>
        </div>
        <button
          onClick={() => onToggle(product.id)}
          className={cn(
            "flex items-center gap-2 rounded-lg px-6 py-2.5 text-sm font-medium transition-colors w-full justify-center",
            selectedIds.has(product.id)
              ? "bg-primary text-primary-foreground hover:bg-primary/90"
              : "border-2 border-primary text-primary hover:bg-primary/10"
          )}
        >
          {selectedIds.has(product.id) ? (
            <>
              <Minus className="h-4 w-4" />
              Retirer de la sélection
            </>
          ) : (
            <>
              <Plus className="h-4 w-4" />
              Ajouter à la sélection
            </>
          )}
        </button>
      </div>

      {/* Specs list */}
      <div className="rounded-xl bg-card border border-border overflow-hidden">
        <div className="border-b border-border bg-muted/50 px-4 py-3">
          <h3 className="font-semibold text-foreground text-sm">Caractéristiques</h3>
        </div>
        <div className="divide-y divide-border">
          {/* Certified */}
          <div className="flex justify-between items-center px-4 py-3">
            <span className="text-sm text-muted-foreground">Fournisseur certifié</span>
            <span className="text-sm font-medium">
              {product.isCertified ? (
                <Check className="h-5 w-5 text-match-high" />
              ) : (
                <span className="text-muted-foreground">—</span>
              )}
            </span>
          </div>
          {/* Specs */}
          {allSpecLabels.map((label) => {
            const spec = getSpecValue(product, label);
            return (
              <div key={label} className="flex justify-between items-start px-4 py-3">
                <span className="text-sm text-muted-foreground">{label}</span>
                <div className="flex flex-col items-end gap-0.5">
                  {spec ? (
                    <>
                      <div className="flex items-center gap-1.5">
                        <span
                          className={cn(
                            "text-sm font-medium",
                            spec.matches === true
                              ? "text-foreground"
                              : spec.matches === false
                              ? "text-amber-700"
                              : "text-muted-foreground"
                          )}
                        >
                          {spec.value}
                        </span>
                        {spec.matches === true && (
                          <Check className="h-4 w-4 text-match-high" />
                        )}
                      </div>
                      {spec.matches === false && spec.expected && (
                        <span className="text-xs text-amber-600">
                          (demandé: {spec.expected})
                        </span>
                      )}
                    </>
                  ) : (
                    <span className="text-sm text-muted-foreground">—</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );

  return (
    <div className="fixed inset-0 z-[60] flex flex-col bg-background">
      {/* Header */}
      <div className="border-b border-border bg-card px-4 md:px-6 py-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg md:text-xl font-bold text-foreground">
            Tableau comparatif
          </h2>
          <p className="text-xs md:text-sm text-muted-foreground">
            Comparez {products.length} produits
          </p>
        </div>
        <button
          onClick={onClose}
          className="flex items-center gap-2 rounded-lg border-2 border-border bg-background px-3 md:px-4 py-2 text-sm font-medium text-foreground hover:bg-muted transition-colors"
        >
          <X className="h-4 w-4" />
          <span className="hidden sm:inline">Fermer</span>
        </button>
      </div>

      {/* Mobile view - Card carousel */}
      <div className="flex-1 overflow-auto p-4 md:hidden">
        {/* Navigation indicators */}
        <div className="flex items-center gap-2 mb-4">
          <button
            type="button"
            onClick={goToPrevious}
            className="flex-shrink-0 flex items-center gap-0.5 rounded-lg bg-muted px-2 py-2 text-xs font-medium text-foreground hover:bg-muted/80 transition-colors"
          >
            <ChevronLeft className="h-4 w-4" />
            Préc.
          </button>
          <div className="flex-1 overflow-x-auto scrollbar-hide">
            <div className="flex items-center justify-center gap-1.5 min-w-max px-1">
              {products.map((_, idx) => (
                <button
                  type="button"
                  key={idx}
                  onClick={() => setCurrentProductIndex(idx)}
                  className={cn(
                    "h-2 w-2 flex-shrink-0 rounded-full transition-colors",
                    idx === currentProductIndex
                      ? "bg-primary"
                      : "bg-muted-foreground/30 hover:bg-muted-foreground/50"
                  )}
                />
              ))}
            </div>
          </div>
          <button
            type="button"
            onClick={goToNext}
            className="flex-shrink-0 flex items-center gap-0.5 rounded-lg bg-muted px-2 py-2 text-xs font-medium text-foreground hover:bg-muted/80 transition-colors"
          >
            Suiv.
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>

        {/* Product indicator */}
        <p className="text-center text-sm text-muted-foreground mb-4">
          Produit {currentProductIndex + 1} sur {products.length}
        </p>

        {/* Current product card */}
        {currentProduct && <MobileProductCard product={currentProduct} />}
      </div>

      {/* Desktop view - Table */}
      <div className="hidden md:flex flex-1 flex-col overflow-hidden p-6">
        {/* Table container avec scrollbars natifs */}
        <div className="flex-1 overflow-x-auto overflow-y-auto relative">
          <table className="w-full border-collapse">
            <thead className="sticky top-0 z-20">
              <tr>
                {/* Fixed column header */}
                <th className="sticky left-0 z-30 bg-card border-b-2 border-r border-border p-4 text-left text-sm font-semibold text-muted-foreground min-w-[180px]">
                  Caractéristiques
                </th>
                {/* Product headers */}
                {products.map((product) => (
                  <th
                    key={product.id}
                    className={cn(
                      "border-b-2 border-border p-4 min-w-[200px] text-center bg-card relative",
                      selectedIds.has(product.id) && "before:absolute before:inset-0 before:bg-primary/5 before:pointer-events-none"
                    )}
                  >
                    <div className="flex flex-col items-center gap-3">
                      {/* Product image */}
                      <div className="h-20 w-20 overflow-hidden rounded-lg bg-muted">
                        <img
                          src={getProductImageUrl(product.image)}
                          alt={product.productName}
                          loading="lazy"
                          className="h-full w-full object-contain"
                        />
                      </div>
                      {/* Product name */}
                      <div className="text-center">
                        <p className="font-semibold text-foreground text-sm line-clamp-2" title={product.productName}>
                          {product.productName}
                        </p>
                        <p className="text-xs text-muted-foreground mt-0.5 h-8">
                          {product.supplierName}
                        </p>
                      </div>
                      {/* Match score badge */}
                      <span
                        className={cn(
                          "rounded-full px-2.5 py-1 text-xs font-semibold text-white shadow-sm",
                          product.matchScore >= 80
                            ? "bg-match-high"
                            : product.matchScore >= 60
                            ? "bg-match-medium"
                            : "invisible"
                        )}
                      >
                        {product.matchScore >= 80 ? "Idéal" : "À considérer"}
                      </span>
                      {/* Add/Remove button */}
                      <button
                        onClick={() => onToggle(product.id)}
                        className={cn(
                          "flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium transition-colors",
                          selectedIds.has(product.id)
                            ? "bg-primary text-primary-foreground hover:bg-primary/90"
                            : "border-2 border-primary text-primary hover:bg-primary/10"
                        )}
                      >
                        {selectedIds.has(product.id) ? (
                          <>
                            <Minus className="h-4 w-4" />
                            Retirer
                          </>
                        ) : (
                          <>
                            <Plus className="h-4 w-4" />
                            Ajouter
                          </>
                        )}
                      </button>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {/* Certified row */}
              <tr className="border-b border-border">
                <td className="sticky left-0 z-10 bg-card border-r border-border p-4 text-sm font-medium text-foreground">
                  Fournisseur certifié
                </td>
                {products.map((product) => (
                  <td
                    key={product.id}
                    className={cn(
                      "p-4 text-center",
                      selectedIds.has(product.id) && "bg-primary/5"
                    )}
                  >
                    {product.isCertified ? (
                      <Check className="h-5 w-5 text-match-high mx-auto" />
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                ))}
              </tr>
              {/* Spec rows */}
              {allSpecLabels.map((label) => (
                <tr key={label} className="border-b border-border">
                  <td className="sticky left-0 z-10 bg-card border-r border-border p-4 text-sm font-medium text-foreground">
                    {label}
                  </td>
                  {products.map((product) => {
                    const spec = getSpecValue(product, label);
                    return (
                      <td
                        key={product.id}
                        className={cn(
                          "p-4 text-center text-sm",
                          selectedIds.has(product.id) && "bg-primary/5"
                        )}
                      >
                        {spec ? (
                          <div className="flex flex-col items-center gap-1">
                            <span
                              className={cn(
                                spec.matches === true
                                  ? "text-foreground"
                                  : spec.matches === false
                                  ? "text-amber-700"
                                  : "text-muted-foreground"
                              )}
                            >
                              {spec.value}
                            </span>
                            {spec.matches === false && spec.expected && (
                              <span className="text-xs text-amber-600">
                                (demandé: {spec.expected})
                              </span>
                            )}
                            {spec.matches === true && (
                              <Check className="h-4 w-4 text-match-high" />
                            )}
                          </div>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Footer */}
      <div className="border-t border-border bg-card px-4 md:px-6 py-4 flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {selectedIds.size} produit{selectedIds.size > 1 ? "s" : ""} sélectionné{selectedIds.size > 1 ? "s" : ""}
        </p>
        <button
          onClick={onClose}
          className="rounded-lg bg-accent px-4 md:px-6 py-2.5 text-sm font-semibold text-accent-foreground hover:bg-accent/90 transition-colors"
        >
          Valider
        </button>
      </div>
    </div>
  );
};

export default ProductComparisonModal;
