'use client';

import { useEffect, useRef, useState } from 'react';
import { ArrowRight } from 'lucide-react';
import type { CtaSticky } from '@/types/conseils';

interface StickyCtaBarProps {
  ctaSticky: CtaSticky;
}

export function StickyCtaBar({ ctaSticky }: StickyCtaBarProps) {
  const { wording, sous_titre, label_bouton } = ctaSticky;
  const [heroGone, setHeroGone] = useState(false);
  const [footerVisible, setFooterVisible] = useState(false);
  const visible = heroGone && !footerVisible;

  useEffect(() => {
    const hero = document.getElementById('hero-trigger');
    const footer = document.getElementById('site-footer');

    const observers: IntersectionObserver[] = [];

    if (hero) {
      const heroObs = new IntersectionObserver(
        ([entry]) => setHeroGone(!entry.isIntersecting),
        { threshold: 0 },
      );
      heroObs.observe(hero);
      observers.push(heroObs);
    }

    if (footer) {
      const footerObs = new IntersectionObserver(
        ([entry]) => setFooterVisible(entry.isIntersecting),
        { threshold: 0 },
      );
      footerObs.observe(footer);
      observers.push(footerObs);
    }

    return () => observers.forEach((o) => o.disconnect());
  }, []);

  function handleClick() {
    window.dispatchEvent(new CustomEvent('hellopro:open-ao-form'));
  }

  return (
    /*
     * Outer : left-0 right-0 width-full — aucun offset horizontal → jamais de scroll horizontal.
     * La directive originale utilise width:100% sans left/right numériques pour cette raison.
     */
    <div
      role="region"
      aria-label="Demande de devis"
      className={[
        'fixed bottom-0 left-0 right-0 z-[500] transition-transform duration-300 ease-in',
        visible ? 'translate-y-0' : 'translate-y-[120%]',
      ].join(' ')}
    >
      {/* Inner card : centrée, max-width, bordure orange — arrondie en haut sur mobile */}
      <div className="mx-auto w-full max-w-[1208px] rounded-t-lg border-2 border-cta bg-background shadow-sm sm:mb-4 sm:rounded-lg">
        <div className="flex items-center gap-4 px-6 py-3 sm:justify-between sm:px-8 sm:py-4">

          {/* Titre + sous-titre — masqués sur mobile (directive: bandeau-sticky-tarification hidden) */}
          <div className="hidden min-w-0 flex-1 sm:block">
            <span className="text-2xl font-semibold leading-[29px] text-foreground">{wording}</span>
            {sous_titre && (
              <p className="text-base text-muted-foreground">{sous_titre}</p>
            )}
          </div>

          {/* Bouton — pleine largeur mobile, auto desktop */}
          <button
            type="button"
            onClick={handleClick}
            className="flex w-full cursor-pointer items-center justify-center gap-2 rounded-md bg-cta px-5 py-3 text-base font-bold text-cta-foreground transition hover:bg-cta-hover sm:w-auto sm:shrink-0"
          >
            {label_bouton} <ArrowRight className="h-4 w-4 shrink-0" />
          </button>
        </div>
      </div>
    </div>
  );
}
