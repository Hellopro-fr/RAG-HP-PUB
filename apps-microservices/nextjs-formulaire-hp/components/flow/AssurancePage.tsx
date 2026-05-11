'use client';

import { FileText, RefreshCw, ListChecks, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface AssurancePageProps {
  categoryName: string;
  categoryVignette: string | null;
  totalQuestions: number;
  onContinue: () => void;
}

interface AssuranceStep {
  number: string;
  icon: React.ComponentType<{ className?: string }>;
  iconBg: string;
  title: string;
  description: string;
}

// Stack de fonts système — identique à celle utilisée par Lovable V1
// (override de la font Inter appliquée globalement via app/layout.tsx).
const SYSTEM_FONT_STACK = 'ui-sans-serif, system-ui, sans-serif, "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji"';

const STEPS: AssuranceStep[] = [
  {
    number: "01.",
    icon: FileText,
    iconBg: "bg-primary",
    title: "Répondez à quelques questions",
    description: "Nous comprenons vos besoins, votre contexte et vos objectifs.",
  },
  {
    number: "02.",
    icon: RefreshCw,
    iconBg: "bg-accent",
    title: "Notre agent IA analyse vos besoins",
    description: "Plus de 250 produits sont comparés afin de trouver les plus adaptés pour vous.",
  },
  {
    number: "03.",
    icon: ListChecks,
    iconBg: "bg-primary",
    title: "Recevez votre short-list personnalisée",
    description: "4 solutions adaptées + estimation du budget.",
  },
];

const AssurancePage = ({ onContinue }: AssurancePageProps) => {
  return (
    <div
      className="flex flex-col min-h-full"
      style={{ fontFamily: SYSTEM_FONT_STACK }}
    >
      <div className="flex-1 px-4 sm:px-6 lg:px-10 py-8 sm:py-12 lg:py-16 pb-32 sm:pb-12">
        <div className="mx-auto max-w-5xl">
          {/* Titre + sous-titre — match Lovable : 36px / 800 / tracking-tight */}
          <div className="text-center">
            <h2 className="text-3xl sm:text-4xl font-extrabold text-foreground leading-[1.1] tracking-tight">
              Comment ça se passe ?
            </h2>
            <p className="mt-3 text-sm sm:text-base text-muted-foreground">
              3 étapes pour recevoir votre short-list personnalisée.
            </p>
          </div>

          {/* 3 cards */}
          <div className="mt-8 sm:mt-10 grid grid-cols-1 lg:grid-cols-3 gap-4 lg:gap-6">
            {STEPS.map((step, index) => {
              const Icon = step.icon;
              return (
                <div
                  key={step.number}
                  className="rounded-2xl border border-border bg-card p-6 sm:p-7 animate-fade-in"
                  style={{ animationDelay: `${index * 80}ms`, animationFillMode: "both" }}
                >
                  <div className={cn("h-12 w-12 rounded-xl flex items-center justify-center text-white", step.iconBg)}>
                    <Icon className="h-6 w-6" />
                  </div>
                  <p className="mt-6 text-sm text-muted-foreground">{step.number}</p>
                  {/* Card title — match Lovable : 24px / 800 */}
                  <h3 className="mt-2 text-2xl font-extrabold text-foreground leading-[1.25]">
                    {step.title}
                  </h3>
                  <p className="mt-3 text-sm text-muted-foreground leading-relaxed">
                    {step.description}
                  </p>
                </div>
              );
            })}
          </div>

          {/* CTA desktop (visible en sm+) — match Lovable : 16px / 700 */}
          <div className="hidden sm:block mt-10 text-center">
            <button
              onClick={onContinue}
              className="inline-flex items-center gap-2 rounded-lg bg-accent px-8 py-4 text-base font-bold text-accent-foreground shadow-lg shadow-accent/25 hover:bg-accent/90 hover:scale-[1.02] transition-all"
            >
              Commencer le questionnaire (1 min) <ArrowRight className="h-4 w-4" />
            </button>
            <p className="mt-3 text-xs text-muted-foreground">
              Pas de mail nécessaire pour voir le résultat
            </p>
          </div>
        </div>
      </div>

      {/* CTA sticky mobile (pleine largeur, en bas) */}
      <div
        className="sm:hidden fixed bottom-0 left-0 right-0 bg-background border-t border-border shadow-[0_-4px_20px_rgba(0,0,0,0.1)]"
        style={{ fontFamily: SYSTEM_FONT_STACK }}
      >
        <div className="px-4 py-3 text-center border-b border-border/50">
          <p className="text-[10px] text-muted-foreground">
            Pas de mail nécessaire pour voir le résultat
          </p>
        </div>
        <div className="p-4">
          <button
            onClick={onContinue}
            className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-accent px-6 py-3.5 text-base font-bold text-accent-foreground shadow-lg shadow-accent/25 transition-all"
          >
            Commencer le questionnaire <ArrowRight className="h-5 w-5" />
          </button>
        </div>
      </div>
    </div>
  );
};

export default AssurancePage;
