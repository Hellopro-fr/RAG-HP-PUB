'use client';

import { useEffect, useState } from 'react';
import { Download } from 'lucide-react';
import { openAssistantDialog } from './AssistantForm';

/**
 * Barre d'action fixe en bas d'écran, mobile uniquement (`lg:hidden`).
 *
 * Sur mobile le questionnaire du hero sort du champ de vision dès le premier
 * défilement : cette barre garde un point d'entrée accessible. Masquée sur
 * grand écran, où le hero et le CTA final suffisent.
 *
 * ⚠️ ANTI-DOUBLON : quand un CTA « assistant » proéminent (`[data-assistant-cta]`
 * — formulaire du hero, bouton « Être accompagné gratuitement » des bandeaux…)
 * est visible à l'écran, la barre se masque : inutile de dupliquer le même bouton.
 * Observé via IntersectionObserver (absent de jsdom → dégrade en barre visible).
 *
 * La barre étant `fixed`, elle ne réserve pas d'espace : elle recouvrirait la fin
 * du contenu. D'où le réservataire ci-dessous, rendu dans le MÊME composant et
 * masqué avec la même condition `lg:hidden`.
 */
export function StickyCta({ label }: { label: string }) {
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return;
    const anchors = Array.from(document.querySelectorAll('[data-assistant-cta]'));
    if (anchors.length === 0) return;

    const visible = new Set<Element>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) visible.add(entry.target);
          else visible.delete(entry.target);
        }
        setHidden(visible.size > 0);
      },
      // Marge basse ≈ hauteur de la barre : un CTA masqué derrière la barre ne
      // compte pas comme « visible ».
      { rootMargin: '0px 0px -64px 0px' }
    );
    anchors.forEach((anchor) => observer.observe(anchor));
    return () => observer.disconnect();
  }, []);

  return (
    <>
      {/* Réservataire d'espace — solidaire de la barre, jamais l'un sans l'autre. */}
      <div aria-hidden className="h-20 lg:hidden" />

      <div
        className={`fixed inset-x-0 bottom-0 z-40 border-t border-border bg-card/95 p-3 backdrop-blur transition-transform duration-300 lg:hidden ${
          hidden ? 'translate-y-full' : 'translate-y-0'
        }`}
      >
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
