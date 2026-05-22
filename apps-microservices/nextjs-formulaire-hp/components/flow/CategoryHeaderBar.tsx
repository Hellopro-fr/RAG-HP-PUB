'use client';

import { getAssetPath } from "@/lib/utils";

const categoryPlaceholder = getAssetPath("/images/product-lift-1.jpg");

interface CategoryHeaderBarProps {
  categoryName: string;
  categoryVignette: string | null;
}

/**
 * Bandeau simplifié vignette + nom catégorie pour les pages hors questionnaire
 * (page budget notamment). Pas de barre de progression, pas de "(1 min max.)" :
 * c'est juste un rappel discret du contexte.
 *
 * Conforme au HTML Lovable de la page /budget : vignette 44px + nom catégorie
 * en text-base font-semibold sur un container max-w-2xl.
 */
const CategoryHeaderBar = ({ categoryName, categoryVignette }: CategoryHeaderBarProps) => {
  return (
    <div className="px-4 py-3 sm:px-6 border-b border-border/60">
      <div className="mx-auto max-w-2xl flex items-center gap-3">
        <img
          src={categoryVignette || categoryPlaceholder}
          alt={categoryName || "Catégorie"}
          width={44}
          height={44}
          className="h-11 w-11 rounded-lg object-cover shrink-0 ring-1 ring-border"
        />
        <div className="flex-1 min-w-0">
          <span className="text-base font-semibold text-foreground">
            {categoryName || "Catégorie"}
          </span>
        </div>
      </div>
    </div>
  );
};

export default CategoryHeaderBar;
