'use client';

import { Lightbulb } from "lucide-react";
import { cn } from "@/lib/utils";
import { parseEmphasisSegments, type QuestionExplanation } from "@/data/question-explanations";

interface QuestionExplanationPanelProps {
  explanation: QuestionExplanation;
  isExiting: boolean;
  variant: "desktop" | "mobile";
  className?: string;
}

const QuestionExplanationPanel = ({
  explanation,
  isExiting,
  variant,
  className,
}: QuestionExplanationPanelProps) => {
  return (
    <aside
      className={cn(
        "rounded-2xl border border-primary/15 bg-primary/5 p-6 transition-all duration-300",
        // Anim miroir de la colonne gauche : sortie à droite, entrée depuis la position neutre
        isExiting ? "opacity-0 translate-x-5" : "opacity-100 translate-x-0",
        variant === "desktop" ? "sticky top-6" : "w-full",
        className,
      )}
    >
      <div className="flex items-center gap-2">
        <Lightbulb className="h-4 w-4 text-primary shrink-0" />
        <h3 className="text-xs font-semibold uppercase tracking-wide text-primary">
          {explanation.title}
        </h3>
      </div>

      <div className="mt-4 space-y-3 text-sm leading-relaxed text-muted-foreground">
        {explanation.paragraphs.map((paragraph, paragraphIndex) => (
          <p key={paragraphIndex}>
            {paragraph.segments.map((segment, segmentIndex) =>
              segment.emphasis ? (
                <strong key={segmentIndex} className="font-semibold text-foreground">
                  {segment.text}
                </strong>
              ) : (
                <span key={segmentIndex}>{segment.text}</span>
              ),
            )}
          </p>
        ))}
      </div>

      {explanation.tip && (
        <p className="mt-4 text-xs text-muted-foreground/80">
          {parseEmphasisSegments(explanation.tip).map((segment, index) =>
            segment.emphasis ? (
              <strong key={index} className="font-semibold text-foreground">
                {segment.text}
              </strong>
            ) : (
              <span key={index}>{segment.text}</span>
            ),
          )}
        </p>
      )}
    </aside>
  );
};

export default QuestionExplanationPanel;
