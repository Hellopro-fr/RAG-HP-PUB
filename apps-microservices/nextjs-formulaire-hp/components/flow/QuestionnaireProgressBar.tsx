'use client';

import Image from "next/image";
import { getAssetPath } from "@/lib/utils";

// TODO: remplacer par l'image réelle de la catégorie quand l'API la fournira
const categoryPlaceholder = getAssetPath("/images/product-lift-1.jpg");

interface QuestionnaireProgressBarProps {
  categoryName: string;
  currentIndex: number;
  totalQuestions: number;
}

const QuestionnaireProgressBar = ({ categoryName, currentIndex, totalQuestions }: QuestionnaireProgressBarProps) => {
  // Q1 (index 0) → 0%, Q2 (index 1) → (1/total)*100, ... Qn → ((n-1)/total)*100
  const progressPercent = totalQuestions > 0 ? (currentIndex / totalQuestions) * 100 : 0;

  return (
    <div className="px-4 py-3 sm:px-6 border-b border-border/60">
      <div className="mx-auto max-w-2xl flex items-center gap-3">
        <Image
          src={categoryPlaceholder}
          alt={categoryName || "Catégorie"}
          width={44}
          height={44}
          className="h-11 w-11 rounded-lg object-cover shrink-0 ring-1 ring-border"
        />
        <div className="flex-1 min-w-0">
          <div>
            <span className="text-base font-semibold text-foreground">
              1 minute pour trouver votre {categoryName || "produit"}
            </span>
          </div>
          <div className="mt-1.5 h-1.5 w-full rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-primary transition-all duration-500 ease-out"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default QuestionnaireProgressBar;
