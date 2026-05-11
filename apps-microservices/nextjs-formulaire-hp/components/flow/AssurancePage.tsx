'use client';

import { ListChecks, Sparkles, Target, ArrowRight, Lock } from "lucide-react";

interface AssurancePageProps {
  categoryName: string;
  categoryVignette: string | null;
  totalQuestions: number;
  onContinue: () => void;
}

interface AssuranceStep {
  number: string;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
  badges: string[];
  live?: boolean;
}

// Stack de fonts système — identique à celle utilisée par Lovable V2
// (override de la font Inter appliquée globalement via app/layout.tsx).
const SYSTEM_FONT_STACK = 'ui-sans-serif, system-ui, sans-serif, "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji"';

const STEPS: AssuranceStep[] = [
  {
    number: "01",
    icon: ListChecks,
    title: "On cerne votre besoin",
    description: "Quelques questions ciblées pour comprendre précisément ce qu'il vous faut.",
    badges: ["7 questions", "<1 min chrono"],
  },
  {
    number: "02",
    icon: Sparkles,
    title: "On scanne tout le marché français",
    description: "Notre base couvre l'intégralité de l'offre disponible en France, mise à jour en continu.",
    badges: ["+250 produits référencés", "45 fournisseurs", "100% du marché FR"],
    live: true,
  },
  {
    number: "03",
    icon: Target,
    title: "On vous propose le bon match",
    description: "Une short-list personnalisée et une estimation budgétaire fiable, en quelques secondes.",
    badges: ["3-5 produits", "€ budget estimé"],
  },
];

const AssurancePage = ({ categoryName, onContinue }: AssurancePageProps) => {
  const safeCategoryName = (categoryName || "produit").toLowerCase();

  return (
    <div
      className="flex flex-col min-h-full"
      style={{ fontFamily: SYSTEM_FONT_STACK }}
    >
      <div className="flex-1 px-4 sm:px-6 lg:px-10 py-8 sm:py-12 pb-32 sm:pb-12">
        <div className="mx-auto max-w-3xl">
          {/* Titre + sous-titre — match Lovable V2 : 30px / 700 */}
          <div className="text-center">
            <h2 className="text-2xl sm:text-3xl font-bold text-foreground leading-[1.2]">
              Trouvons ensemble votre {safeCategoryName}
            </h2>
            <p className="mt-2 text-sm sm:text-base text-muted-foreground">
              En 1 minute, voici comment ça se passe :
            </p>
          </div>

          {/* 3 cards verticales */}
          <div className="mt-6 sm:mt-8 space-y-3 sm:space-y-4">
            {STEPS.map((step, index) => {
              const Icon = step.icon;
              return (
                <div
                  key={step.number}
                  className="relative rounded-xl border border-border bg-card p-4 sm:p-5 flex gap-4 animate-fade-in"
                  style={{ animationDelay: `${index * 80}ms`, animationFillMode: "both" }}
                >
                  {/* Numéro discret top-right */}
                  <span className="absolute top-3 right-4 text-xs font-mono text-muted-foreground/60">
                    {step.number}
                  </span>

                  {/* Icône ronde pastel */}
                  <div className="h-10 w-10 shrink-0 rounded-full bg-primary/10 text-primary flex items-center justify-center">
                    <Icon className="h-5 w-5" />
                  </div>

                  <div className="flex-1 min-w-0 pr-6">
                    {/* Titre + badge Live optionnel */}
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="font-semibold text-foreground">{step.title}</h3>
                      {step.live && (
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 text-emerald-600 px-2 py-0.5 text-xs font-medium">
                          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                          Live
                        </span>
                      )}
                    </div>

                    {/* Description */}
                    <p className="mt-1 text-sm text-muted-foreground leading-relaxed">
                      {step.description}
                    </p>

                    {/* Badges stats */}
                    {step.badges.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {step.badges.map((badge) => (
                          <span
                            key={badge}
                            className="inline-flex items-center rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground"
                          >
                            {badge}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* CTA desktop (sm+) — match Lovable V2 : orange accent, 16px / 600, arrow-right */}
          <div className="hidden sm:block mt-8 text-center">
            <button
              onClick={onContinue}
              className="inline-flex items-center gap-2 rounded-lg bg-accent px-6 py-3 text-base font-semibold text-accent-foreground shadow-lg shadow-accent/25 hover:bg-accent/90 transition-colors"
            >
              C'est parti
              <ArrowRight className="h-4 w-4" />
            </button>
            <p className="mt-3 inline-flex items-center gap-1.5 text-xs text-muted-foreground">
              <Lock className="h-3 w-3" />
              Pas besoin d'email pour voir votre résultat
            </p>
          </div>
        </div>
      </div>

      {/* CTA sticky mobile — orange accent, arrow-right, cadenas */}
      <div
        className="sm:hidden fixed bottom-0 left-0 right-0 bg-background border-t border-border shadow-[0_-4px_20px_rgba(0,0,0,0.1)]"
        style={{ fontFamily: SYSTEM_FONT_STACK }}
      >
        <div className="px-4 py-3 text-center border-b border-border/50">
          <p className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <Lock className="h-3 w-3" />
            Pas besoin d'email pour voir votre résultat
          </p>
        </div>
        <div className="p-4">
          <button
            onClick={onContinue}
            className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-accent px-6 py-3.5 text-base font-semibold text-accent-foreground shadow-lg shadow-accent/25 transition-colors"
          >
            C'est parti
            <ArrowRight className="h-5 w-5" />
          </button>
        </div>
      </div>
    </div>
  );
};

export default AssurancePage;
