'use client';

import { FileText, LoaderCircle, ListChecks, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface AssurancePageProps {
  categoryName: string;
  categoryVignette: string | null;
  totalQuestions: number;
  onContinue: () => void;
}

interface AssuranceStep {
  number: string;
  icon: LucideIcon;
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
    icon: LoaderCircle,
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
      <section className="py-12 lg:py-16 pb-32 sm:pb-12">
        <div className="max-w-7xl mx-auto px-6 lg:px-10">
          {/* Titre — Lovable : text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight */}
          <h2 className="text-center text-4xl sm:text-5xl lg:text-6xl font-extrabold text-foreground tracking-tight">
            Comment ça se passe ?
          </h2>
          <p className="text-center mt-4 text-base sm:text-lg text-muted-foreground max-w-2xl mx-auto">
            3 étapes pour recevoir votre short-list personnalisée.
          </p>

          {/* Grid 3 cards — Lovable : md:grid-cols-3 gap-6 lg:gap-8 */}
          <div className="mt-12 lg:mt-16 grid grid-cols-1 md:grid-cols-3 gap-6 lg:gap-8">
            {STEPS.map((step, index) => {
              const Icon = step.icon;
              return (
                <div
                  key={step.number}
                  className="rounded-xl bg-card border border-border p-8 lg:p-10 shadow-sm hover:shadow-md transition-shadow animate-fade-in"
                  style={{ animationDelay: `${index * 80}ms`, animationFillMode: "both" }}
                >
                  {/* Icône — Lovable : h-14 w-14 rounded-xl mb-6 / SVG h-7 w-7 */}
                  <div className={cn("flex h-14 w-14 items-center justify-center rounded-xl mb-6", step.iconBg)}>
                    <Icon className={cn("h-7 w-7", step.iconBg === "bg-primary" ? "text-primary-foreground" : "text-accent-foreground")} />
                  </div>
                  {/* Numéro — Lovable : text-lg font-semibold mb-2 (au-dessus du titre) */}
                  <p className="text-lg font-semibold text-muted-foreground mb-2">{step.number}</p>
                  {/* Card title — Lovable : text-2xl font-extrabold leading-tight mb-4 */}
                  <h3 className="text-2xl font-extrabold text-foreground leading-tight mb-4">
                    {step.title}
                  </h3>
                  {/* Description — Lovable : text-base leading-relaxed */}
                  <p className="text-base text-muted-foreground leading-relaxed">
                    {step.description}
                  </p>
                </div>
              );
            })}
          </div>

          {/* CTA desktop (sm+) — Lovable V1 : rounded-xl px-8 py-5 text-base sm:text-lg font-bold bg-accent, flèche dans le texte */}
          <div className="hidden sm:flex flex-col items-center gap-3 mt-12">
            <button
              onClick={onContinue}
              className="inline-flex items-center justify-center rounded-xl px-8 py-5 text-base sm:text-lg font-bold bg-accent text-accent-foreground hover:opacity-90 transition-opacity shadow-lg"
            >
              Commencer le questionnaire (1 min) →
            </button>
            <p className="text-sm text-muted-foreground">
              Pas de mail nécessaire pour voir le résultat
            </p>
          </div>
        </div>
      </section>

      {/* CTA sticky mobile — ajout par rapport à Lovable V1 pour booster la conversion sur petit écran */}
      <div
        className="sm:hidden fixed bottom-0 left-0 right-0 z-20 bg-background/95 backdrop-blur border-t border-border/40 px-4 py-3 flex flex-col items-center gap-1.5"
        style={{ fontFamily: SYSTEM_FONT_STACK }}
      >
        <button
          onClick={onContinue}
          className="w-full inline-flex items-center justify-center rounded-xl px-6 py-3.5 text-base font-bold bg-accent text-accent-foreground hover:opacity-90 transition-opacity shadow-lg"
        >
          Commencer le questionnaire (1 min) →
        </button>
        <p className="text-[11px] text-muted-foreground">
          Pas de mail nécessaire pour voir le résultat
        </p>
      </div>
    </div>
  );
};

export default AssurancePage;
