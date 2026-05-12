'use client';

import { ListChecks, Sparkles, Target, ArrowRight, Lock, type LucideIcon } from "lucide-react";

interface AssurancePageProps {
  categoryName: string;
  categoryVignette: string | null;
  totalQuestions: number;
  onContinue: () => void;
}

interface AssuranceStat {
  value: string;
  label: string;
}

interface AssuranceStep {
  number: string;
  icon: LucideIcon;
  title: string;
  description: string;
  stats: AssuranceStat[];
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
    stats: [
      { value: "7", label: "questions" },
      { value: "<1 min", label: "chrono" },
    ],
  },
  {
    number: "02",
    icon: Sparkles,
    title: "On scanne tout le marché français",
    description: "Notre base couvre l'intégralité de l'offre disponible en France, mise à jour en continu.",
    stats: [
      { value: "+250", label: "produits référencés" },
      { value: "45", label: "fournisseurs" },
      { value: "100%", label: "du marché FR" },
    ],
    live: true,
  },
  {
    number: "03",
    icon: Target,
    title: "On vous propose le bon match",
    description: "Une short-list personnalisée et une estimation budgétaire fiable, en quelques secondes.",
    stats: [
      { value: "3-5", label: "produits" },
      { value: "€", label: "budget estimé" },
    ],
  },
];

const AssurancePage = ({ categoryName, onContinue }: AssurancePageProps) => {
  const safeCategoryName = (categoryName || "produit").toLowerCase();

  return (
    <div
      className="flex flex-col min-h-full"
      style={{ fontFamily: SYSTEM_FONT_STACK }}
    >
      <div className="flex-1 px-4 sm:px-6 lg:px-10 pt-4 sm:pt-12 pb-28 sm:pb-12">
        <div className="mx-auto max-w-2xl space-y-4 sm:space-y-8">
          {/* Titre + sous-titre — Lovable : text-lg sm:text-2xl lg:text-3xl / font-bold */}
          <div className="text-center space-y-1 sm:space-y-2">
            <h2 className="text-lg sm:text-2xl lg:text-3xl font-bold text-foreground leading-tight">
              Trouvons ensemble votre {safeCategoryName}
            </h2>
            <p className="text-xs sm:text-base text-muted-foreground">
              En 1 minute, voici comment ça se passe :
            </p>
          </div>

          {/* Liste cards — Lovable : <ol max-w-xl mx-auto space-y-2 sm:space-y-3> */}
          <ol className="max-w-xl mx-auto space-y-2 sm:space-y-3">
            {STEPS.map((step, index) => {
              const Icon = step.icon;
              return (
                <li
                  key={step.number}
                  className="relative flex gap-3 sm:gap-4 rounded-xl border border-border/60 bg-card/50 px-3 sm:px-4 py-2.5 sm:py-3.5 animate-fade-in"
                  style={{ animationDelay: `${index * 120}ms`, animationFillMode: "both" }}
                >
                  {/* Numéro discret top-right — Lovable : text-[10px] sm:text-[11px] font-mono /60 */}
                  <span className="absolute top-2 right-2 sm:top-3 sm:right-3 text-[10px] sm:text-[11px] font-mono text-muted-foreground/60">
                    {step.number}
                  </span>

                  {/* Icône ronde pastel — Lovable : h-8 w-8 sm:h-9 sm:w-9 + ring-1 ring-primary/15 */}
                  <span className="flex h-8 w-8 sm:h-9 sm:w-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary ring-1 ring-primary/15">
                    <Icon className="h-3.5 w-3.5 sm:h-4 sm:w-4" strokeWidth={2.25} />
                  </span>

                  <div className="min-w-0 flex-1">
                    {/* Titre card + badge Live optionnel — Lovable : text-[13px] sm:text-[15px] font-semibold */}
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-[13px] sm:text-[15px] font-semibold text-foreground leading-tight">
                        {step.title}
                      </p>
                      {step.live && (
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-600 dark:text-emerald-400 ring-1 ring-emerald-500/20">
                          <span className="relative flex h-1.5 w-1.5">
                            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-500 opacity-75" />
                            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
                          </span>
                          Live
                        </span>
                      )}
                    </div>

                    {/* Description — Lovable : text-xs sm:text-sm mt-1 leading-relaxed */}
                    <p className="text-xs sm:text-sm text-muted-foreground mt-1 leading-relaxed">
                      {step.description}
                    </p>

                    {/* Badges stats — Lovable : rounded-md bg-muted/60 px-1.5 sm:px-2 py-0.5 text-[10px] sm:text-[11px] */}
                    {step.stats.length > 0 && (
                      <div className="mt-1.5 sm:mt-2.5 flex flex-wrap gap-1 sm:gap-1.5">
                        {step.stats.map((stat) => (
                          <span
                            key={stat.label}
                            className="inline-flex items-baseline gap-1 rounded-md bg-muted/60 px-1.5 sm:px-2 py-0.5 text-[10px] sm:text-[11px] text-muted-foreground"
                          >
                            <span className="font-semibold text-foreground tabular-nums">{stat.value}</span>
                            <span>{stat.label}</span>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>

          {/* CTA desktop (sm+) — Lovable : flex flex-col items-center gap-3 pt-2 */}
          <div className="hidden sm:flex flex-col items-center gap-3 pt-2">
            <button
              onClick={onContinue}
              className="inline-flex items-center gap-2 rounded-lg bg-accent text-accent-foreground hover:bg-accent/90 shadow-lg shadow-accent/25 px-6 py-3 text-sm sm:text-base font-semibold transition-all"
            >
              C'est parti
              <ArrowRight className="h-4 w-4" />
            </button>
            <p className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
              <Lock className="h-3 w-3" />
              Pas besoin d'email pour voir votre résultat
            </p>
          </div>
        </div>
      </div>

      {/* CTA sticky mobile — Lovable : bg-background/95 backdrop-blur border-border/40 */}
      <div
        className="sm:hidden fixed bottom-0 left-0 right-0 z-20 bg-background/95 backdrop-blur border-t border-border/40 px-4 py-3 flex flex-col items-center gap-1.5"
        style={{ fontFamily: SYSTEM_FONT_STACK }}
      >
        <button
          onClick={onContinue}
          className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-accent text-accent-foreground shadow-lg shadow-accent/25 px-6 py-3 text-base font-semibold transition-all"
        >
          C'est parti
          <ArrowRight className="h-4 w-4" />
        </button>
        <p className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <Lock className="h-3 w-3" />
          Pas besoin d'email pour voir votre résultat
        </p>
      </div>
    </div>
  );
};

export default AssurancePage;
