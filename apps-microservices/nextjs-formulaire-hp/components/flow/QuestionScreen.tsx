'use client';

import { useState } from "react";
import { ArrowLeft, ArrowRight, Info, Check, Package, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Question } from "@/types";

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
  const [showJustification, setShowJustification] = useState(false);

  const showOtherOption = question.id === 3;
  const isOtherSelected = selectedAnswers.includes("other");
  const hasSelection = selectedAnswers.length > 0;

  const handleAnswerClick = (answerId: string) => {
    // For single select, auto-advance after selection - except for "other" which needs text input
    const shouldAutoAdvance = !question.multiSelect && answerId !== "other";
    onSelectAnswer(answerId, shouldAutoAdvance);
  };

  return (
    <div className="flex flex-col min-h-full">
      {/* Scrollable content */}
      <div className="flex-1 p-4 sm:p-6 lg:p-10 pb-32 sm:pb-6">
        <div className="mx-auto max-w-[44em] space-y-6 sm:space-y-8">
          {/* Question counter */}

          {/* Question counter */}
          <div className="text-center">
            <span className="inline-flex items-center gap-2 rounded-full bg-secondary px-4 py-1.5 text-sm font-medium text-secondary-foreground">
              {totalQuestions == 1 ? "Question 1" : `Question ${currentIndex + 1} sur ${totalQuestions}`}              
            </span>
          </div>

          {/* Question title */}
          <div className="text-center space-y-3 sm:space-y-4">
            <h2 className="text-lg sm:text-xl lg:text-2xl font-bold text-foreground leading-tight">
              {question.title}
            </h2>
            
            {/* Justification toggle */}
            <button
              onClick={() => setShowJustification(!showJustification)}
              className="inline-flex items-center gap-1.5 text-sm text-primary hover:text-primary/80 transition-colors"
            >
              <Info className="h-4 w-4" />
              {showJustification ? "Masquer l'explication" : "Pourquoi cette question ?"}
            </button>

            
            {showJustification && (
              <div className="rounded-lg bg-primary/5 border border-primary/20 p-4 text-sm text-muted-foreground text-left">
                {question.justification}
              </div>
            )}
          </div>

          {/* Answer options */}
          <div className="space-y-3">

            {/* Regular answers (excluding quick option) */}
            {question.answers
              .filter((answer) => answer.id !== "1-quick")
              .map((answer) => {
                const isSelected = selectedAnswers.includes(answer.id);

                return (
                  <button
                    key={answer.id}
                    onClick={() => handleAnswerClick(answer.id)}
                    className={cn(
                      "w-full text-left rounded-xl border-2 p-4 transition-all",
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
                          question.multiSelect ? "rounded" : "rounded-full",
                          isSelected
                            ? "border-2 border-primary bg-primary"
                            : "border-2 border-muted-foreground/30"
                        )}
                      >
                        {isSelected && (
                          question.multiSelect ? (
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
                  "w-full text-left rounded-xl border-2 p-4 transition-all",
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
                        question.multiSelect ? "rounded" : "rounded-full",
                        isOtherSelected
                          ? "border-2 border-primary bg-primary"
                          : "border-2 border-muted-foreground/30"
                      )}
                    >
                      {isOtherSelected && (
                        question.multiSelect ? (
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


          {/* Desktop navigation with reassurance - hidden on mobile */}
          <div className="hidden sm:block pt-4 space-y-3">
            <div className="flex items-center justify-between">
              <button
                onClick={onBack}
                disabled={isFirst}
                className={cn(
                  "flex items-center gap-2 rounded-lg border-2 border-border bg-background px-5 py-3 text-sm font-medium transition-colors",
                  isFirst
                    ? "opacity-50 cursor-not-allowed"
                    : "hover:bg-muted text-foreground"
                )}
              >
                <ArrowLeft className="h-4 w-4" />
                Précédent
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
            
            {/* Desktop reassurance - below buttons */}
            <div className="flex items-center justify-center gap-4 text-sm">
              <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1.5">
                <Package className="h-4 w-4 text-primary" />
                <span className="text-foreground">
                  <span className="font-semibold text-primary">Ponts élévateurs</span>
                  <span className="text-muted-foreground"> : 347 produits analysés • 24 fournisseurs</span>
                </span>
              </div>
              <div className="inline-flex items-center gap-2 text-muted-foreground">
                <Users className="h-4 w-4" />
                <span>+ de 10 000 pros équipés / mois</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Mobile sticky footer with reassurance */}
      <div className="sm:hidden fixed bottom-0 left-0 right-0 bg-background border-t border-border shadow-[0_-4px_20px_rgba(0,0,0,0.1)]">
        {/* Reassurance line */}
        <div className="flex flex-col items-center gap-1.5 px-4 py-2 border-b border-border/50 bg-primary/5">
          <div className="inline-flex items-center gap-1.5 text-xs">
            <Package className="h-3.5 w-3.5 text-primary" />
            <span className="font-semibold text-primary">Ponts élévateurs</span>
            <span className="text-muted-foreground">: 347 produits analysés • 24 fournisseurs</span>
          </div>
          <div className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            <Users className="h-3.5 w-3.5" />
            <span>+ de 10 000 pros équipés / mois</span>
          </div>
        </div>
        
        {/* Navigation buttons */}
        <div className="flex items-center gap-3 p-4">
          <button
            onClick={onBack}
            disabled={isFirst}
            className={cn(
              "flex items-center justify-center rounded-lg border-2 border-border bg-background px-4 py-3 text-sm font-medium transition-colors",
              isFirst
                ? "opacity-50 cursor-not-allowed"
                : "hover:bg-muted text-foreground"
            )}
          >
            <ArrowLeft className="h-5 w-5" />
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
            {isLast ? "Voir ma sélection" : "Suivant"}
            <ArrowRight className="h-5 w-5" />
          </button>
        </div>
      </div>
    </div>
  );
};

export default QuestionScreen;
