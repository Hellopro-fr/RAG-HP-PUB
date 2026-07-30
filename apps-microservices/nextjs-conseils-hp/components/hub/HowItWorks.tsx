import { ChevronRight } from 'lucide-react';
import { HubSection, HubIcon } from './primitives';
import type { HubHowItWorks as HubHowItWorksData } from '@/types/hub';

/**
 * Parcours en étapes numérotées, séparées par un chevron.
 *
 * Le numéro fait partie du TITRE (« 1. Vous décrivez votre projet ») : c'est ce
 * qui rend l'ordre lisible dans le texte lui-même, y compris pour un lecteur
 * d'écran qui parcourt les titres. Un gros chiffre décoratif à côté de l'icône ne
 * porte pas la même information.
 *
 * Le chevron pivote : vertical en colonne (mobile), horizontal en ligne (desktop).
 * Il est purement décoratif, d'où `aria-hidden` — la numérotation et le `<ol>`
 * suffisent à exprimer la séquence.
 */
export function HowItWorks({ data }: { data: HubHowItWorksData }) {
  return (
    <HubSection id="comment-ca-marche">
      <div className="mx-auto max-w-3xl text-center">
        <h2 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
          {data.title}
        </h2>
      </div>

      <ol className="mt-10 flex flex-col items-stretch gap-5 lg:flex-row">
        {data.steps.map((step, index) => (
          <li key={step.title} className="flex flex-col items-stretch gap-5 lg:flex-1 lg:flex-row">
            <div className="flex-1 rounded-2xl border border-border bg-card p-6 shadow-sm">
              <span className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/10 text-primary">
                <HubIcon name={step.icon} className="h-6 w-6" />
              </span>
              <h3 className="mt-5 text-base font-bold text-foreground">
                {index + 1}. {step.title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{step.desc}</p>
            </div>

            {index < data.steps.length - 1 && (
              <span
                aria-hidden
                className="flex items-center justify-center text-muted-foreground"
              >
                <ChevronRight className="h-6 w-6 rotate-90 lg:rotate-0" />
              </span>
            )}
          </li>
        ))}
      </ol>
    </HubSection>
  );
}
