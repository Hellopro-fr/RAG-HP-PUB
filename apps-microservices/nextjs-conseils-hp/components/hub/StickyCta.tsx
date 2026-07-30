'use client';

import { Download } from 'lucide-react';
import { openAssistantDialog } from './AssistantForm';

/**
 * Barre d'action fixe en bas d'écran, mobile uniquement (`lg:hidden`).
 *
 * Sur mobile le questionnaire du hero sort du champ de vision dès le premier
 * défilement : cette barre garde un point d'entrée accessible. Masquée sur
 * grand écran, où le hero et le CTA final suffisent.
 *
 * La barre étant `fixed`, elle ne réserve pas d'espace : elle recouvrirait la fin
 * du contenu. D'où le réservataire ci-dessous, rendu dans le MÊME composant et
 * masqué avec la même condition `lg:hidden`. Le mettre en `pb-20 lg:pb-0` sur le
 * conteneur de page laissait une bande de fond visible sous le footer.
 */
export function StickyCta({ label }: { label: string }) {
  return (
    <>
      {/* Réservataire d'espace — solidaire de la barre, jamais l'un sans l'autre. */}
      <div aria-hidden className="h-20 lg:hidden" />

      <div className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-card/95 p-3 backdrop-blur lg:hidden">
        <button
          type="button"
          onClick={openAssistantDialog}
          className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-cta text-sm font-bold text-cta-foreground shadow-cta transition hover:bg-cta-hover"
        >
          <Download className="h-4 w-4" />
          {label}
        </button>
      </div>
    </>
  );
}
