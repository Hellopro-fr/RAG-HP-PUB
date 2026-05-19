'use client';

import { useState, useEffect, useRef } from "react";
import { ArrowLeft, ArrowRight, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Question } from "@/types";
import { useFlowStore } from "@/lib/stores/flow-store";
import { getCategoryQuestion } from "@/data/category-static-content";
import { getQuestionExplanation } from "@/data/question-explanations";
import QuestionExplanationPanel from "@/components/flow/QuestionExplanationPanel";

interface QuestionScreenProps {
  question: Question;
  currentIndex: number;
  totalQuestions: number;
  selectedAnswers: string[];
  otherText: string;
  onSelectAnswer: (answerId: string, autoAdvance?: boolean) => void;
  onOtherTextChange: (text: string) => void;
  onNext: () => void;
  onBack: () => void;
  isFirst: boolean;
  isLast: boolean;
}

const QuestionScreen = ({
  question,
  currentIndex,
  totalQuestions,
  selectedAnswers,
  otherText,
  onSelectAnswer,
  onOtherTextChange,
  onNext,
  onBack,
  isFirst,
  isLast,
}: QuestionScreenProps) => {
  const { categoryName, categoryStats, categoryId } = useFlowStore();

  // Animation slide-fade : exit vers la gauche, enter depuis la droite
  const [isExiting, setIsExiting] = useState(false);
  const [displayedQuestion, setDisplayedQuestion] = useState(question);
  const prevIndexRef = useRef(currentIndex);

  useEffect(() => {
    if (currentIndex === prevIndexRef.current) {
      // Même index, juste mettre à jour la question (ex: re-render)
      setDisplayedQuestion(question);
      return;
    }

    // Phase exit : le contenu glisse vers la gauche et disparaît
    setIsExiting(true);

    const timer = setTimeout(() => {
      // Après l'exit, afficher le nouveau contenu et lancer l'entrée
      setDisplayedQuestion(question);
      setIsExiting(false);
      prevIndexRef.current = currentIndex;
    }, 300); // même durée que transition-all duration-300

    return () => clearTimeout(timer);
  }, [currentIndex, question]);

  // Stats avec fallback sur valeurs statiques
  const productsCount = categoryStats?.productsCount ?? 1400;
  const suppliersCount = categoryStats?.suppliersCount ?? 43;

  // Texte réassurance depuis categoryStaticContent si disponible
  const staticContent = categoryId ? getCategoryQuestion(categoryId) : undefined;
  const reassuranceText = staticContent?.reassurance
    ? staticContent.reassurance.replace('xx', String(productsCount)).replace('zz', String(suppliersCount))
    : `${productsCount} modèles de ${categoryName || "produits"} comparés chez ${suppliersCount} vendeurs`;

  // Utiliser displayedQuestion pour le rendu (suit l'animation exit/enter)
  const showOtherOption = displayedQuestion.id === 3;
  const isOtherSelected = selectedAnswers.includes("other");
  const hasSelection = selectedAnswers.length > 0;

  // Panneau d'aide latéral : exclusivement alimenté par `bulle_aide` API.
  // Si la donnée est absente ou malformée, le panneau est masqué (layout mono-colonne).
  const explanation = getQuestionExplanation(displayedQuestion.bulleAide);

  const handleAnswerClick = (answerId: string) => {
    // For single select, auto-advance after selection - except for "other" which needs text input
    const shouldAutoAdvance = !displayedQuestion.multiSelect && answerId !== "other";
    onSelectAnswer(answerId, shouldAutoAdvance);
  };

  return (
    <div className="flex flex-col min-h-full">
      {/* Scrollable content.
          pb-48 sur mobile : le sticky footer (réassurance + boutons + safe-area)
          fait ~150px, on ajoute 40px de marge pour que la card explication mobile
          ne se retrouve pas collée/cachée sous le footer en bas de scroll. */}
      <div className="flex-1 pb-48 sm:pb-6">
        <div className="px-4 sm:px-6 lg:px-10 pt-5 sm:pt-8">
        <div className={cn(
          "mx-auto grid gap-6 lg:gap-10",
          explanation
            ? "max-w-5xl grid-cols-1 lg:grid-cols-[minmax(0,1fr)_300px]"
            : "max-w-2xl grid-cols-1",
        )}>
        <div className={cn(
          "mx-auto w-full max-w-2xl space-y-5 lg:mx-0 lg:max-w-none transition-all duration-300",
          isExiting ? "opacity-0 -translate-x-5" : "opacity-100 translate-x-0",
        )}>
          {/* Question title */}
          <div className="space-y-3 sm:space-y-4">
            <h2 className="text-lg sm:text-xl lg:text-2xl font-bold text-foreground leading-tight">
              {displayedQuestion.title}
            </h2>
          </div>

          {/* Answer options */}
          <div className="space-y-3">

            {/* Regular answers (excluding quick option) */}
            {displayedQuestion.answers
              .filter((answer) => answer.id !== "1-quick")
              .map((answer) => {
                const isSelected = selectedAnswers.includes(answer.id);

                return (
                  <button
                    key={answer.id}
                    onClick={() => handleAnswerClick(answer.id)}
                    className={cn(
                      "w-full text-left rounded-xl border-2 px-4 py-3 transition-all",
                      "hover:border-primary/50 hover:bg-primary/5",
                      isSelected
                        ? "border-primary bg-primary/10"
                        : "border-border bg-background"
                    )}
                  >
                    <div className="flex items-start gap-3">
                      {/* Checkbox or Radio indicator */}
                      <div
                        className={cn(
                          "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center transition-colors",
                          displayedQuestion.multiSelect ? "rounded" : "rounded-full",
                          isSelected
                            ? "border-2 border-primary bg-primary"
                            : "border-2 border-muted-foreground/30"
                        )}
                      >
                        {isSelected && (
                          displayedQuestion.multiSelect ? (
                            <Check className="h-3 w-3 text-primary-foreground" />
                          ) : (
                            <div className="h-2 w-2 rounded-full bg-primary-foreground" />
                          )
                        )}
                      </div>
                      
                      {/* Answer text */}
                      <div className="flex-1">
                        <span className="text-sm sm:text-base text-foreground">
                          {answer.mainText}
                        </span>
                      </div>
                    </div>
                  </button>
                );
              })}

            {/* Other option - only for question 3 */}
            {showOtherOption && (
              <div
                className={cn(
                  "w-full text-left rounded-xl border-2 px-4 py-3 transition-all",
                  isOtherSelected
                    ? "border-primary bg-primary/10"
                    : "border-border bg-background hover:border-primary/50 hover:bg-primary/5"
                )}
              >
                <button
                  onClick={() => handleAnswerClick("other")}
                  className="w-full text-left"
                >
                  <div className="flex items-start gap-3">
                    {/* Checkbox or Radio indicator */}
                    <div
                      className={cn(
                        "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center transition-colors",
                        displayedQuestion.multiSelect ? "rounded" : "rounded-full",
                        isOtherSelected
                          ? "border-2 border-primary bg-primary"
                          : "border-2 border-muted-foreground/30"
                      )}
                    >
                      {isOtherSelected && (
                        displayedQuestion.multiSelect ? (
                          <Check className="h-3 w-3 text-primary-foreground" />
                        ) : (
                          <div className="h-2 w-2 rounded-full bg-primary-foreground" />
                        )
                      )}
                    </div>
                    
                    {/* Answer text */}
                    <div className="flex-1">
                      <span className="text-sm sm:text-base font-medium text-foreground">
                        Autre
                      </span>
                      <span className="ml-1.5 sm:ml-2 text-xs sm:text-sm text-muted-foreground">
                        — Précisez votre situation
                      </span>
                    </div>
                  </div>
                </button>
                
                {/* Text input when "Autre" is selected */}
                {isOtherSelected && (
                  <div className="mt-3 pl-8">
                    <input
                      type="text"
                      value={otherText}
                      onChange={(e) => onOtherTextChange(e.target.value)}
                      placeholder="Décrivez votre situation..."
                      className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                      autoFocus
                      onClick={(e) => e.stopPropagation()}
                    />
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Mobile / tablet explanation card — visible sous lg, le panneau desktop est rendu à droite */}
          {explanation && (
            <QuestionExplanationPanel
              explanation={explanation}
              isExiting={isExiting}
              variant="mobile"
              className="lg:hidden"
            />
          )}

          {/* Desktop navigation with reassurance - hidden on mobile */}
          <div className="hidden sm:block pt-4 space-y-3">
            <div className="flex items-center justify-between">             
              <button
                onClick={onBack}
                disabled={isFirst}
                className={cn(
                  "flex items-center gap-2 text-sm font-semibold uppercase tracking-wide transition-colors",
                  isFirst
                    ? "opacity-0 cursor-default pointer-events-none"
                    : "text-foreground hover:text-foreground/70"
                )}
              >
                <ArrowLeft className="h-4 w-4" />
                Retour
              </button>

              {/* Always show Suivant button for visual consistency */}
              <button
                onClick={onNext}
                disabled={!hasSelection}
                className={cn(
                  "flex items-center gap-2 rounded-lg px-6 py-3 text-sm font-semibold transition-all",
                  hasSelection
                    ? "bg-accent text-accent-foreground hover:bg-accent/90 shadow-lg shadow-accent/25"
                    : "bg-muted text-muted-foreground cursor-not-allowed"
                )}
              >
                {isLast && totalQuestions > 1 ? "Voir ma sélection" : "Suivant"}                

                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
            
            {/* Nouvelle réassurance desktop */}
            <div className="mt-5 rounded-lg border border-primary/15 bg-primary/5 px-4 py-3 text-center">
              <p className="text-sm text-foreground">
                À la fin de ce questionnaire → <span className="font-semibold text-primary">💰 Estimation de prix</span> + <span className="font-semibold text-primary">📦 Produits adaptés à votre besoin</span>
              </p>
              <p className="mt-1.5 text-xs text-muted-foreground">
                {reassuranceText}
              </p>
            </div>
          </div>
        </div>

        {/* Panneau d'explication latéral — desktop only (lg+) */}
        {explanation && (
          <div className="hidden lg:block">
            <QuestionExplanationPanel
              explanation={explanation}
              isExiting={isExiting}
              variant="desktop"
            />
          </div>
        )}
        </div>
        </div>
      </div>

      {/* Mobile sticky footer with reassurance */}
      <div className="sm:hidden fixed bottom-0 left-0 right-0 bg-background border-t border-border shadow-[0_-4px_20px_rgba(0,0,0,0.1)]">


        {/* Nouvelle réassurance mobile */}
        <div className="px-4 py-2 border-b border-border/50 text-center">
          <p className="text-xs text-foreground">
            À la fin → <span className="font-semibold text-primary">💰 Estimation de prix</span> + <span className="font-semibold text-primary">📦 Produits adaptés</span>
          </p>
          <p className="mt-1 text-[10px] text-muted-foreground">
            {reassuranceText}
          </p>
        </div>
        
        {/* Navigation buttons */}
        <div className="flex items-center gap-3 p-4">          
          <button
            onClick={onBack}
            disabled={isFirst}
            className={cn(
              "flex items-center gap-2 text-sm font-semibold uppercase tracking-wide transition-colors",
              isFirst
                ? "opacity-0 cursor-default pointer-events-none"
                : "text-foreground hover:text-foreground/70"
            )}
          >
            <ArrowLeft className="h-4 w-4" />
            Retour
          </button>

          {/* Always show Suivant button for visual consistency */}
          <button
            onClick={onNext}
            disabled={!hasSelection}
            className={cn(
              "flex-1 flex items-center justify-center gap-2 rounded-lg px-6 py-3.5 text-base font-semibold transition-all",
              hasSelection
                ? "bg-accent text-accent-foreground shadow-lg shadow-accent/25"
                : "bg-muted text-muted-foreground cursor-not-allowed"
            )}
          >
            {isLast && totalQuestions > 1 ? "Voir ma sélection" : "Suivant"}
            <ArrowRight className="h-5 w-5" />
          </button>
        </div>
      </div>
    </div>
  );
};

export default QuestionScreen;
