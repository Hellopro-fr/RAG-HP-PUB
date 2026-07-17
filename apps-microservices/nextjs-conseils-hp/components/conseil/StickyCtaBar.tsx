'use client';

import { useEffect, useRef, useState } from 'react';
import { ArrowRight } from 'lucide-react';
import type { CtaSticky } from '@/types/conseils';

interface StickyCtaBarProps {
  ctaSticky: CtaSticky;
}

export function StickyCtaBar({ ctaSticky }: StickyCtaBarProps) {
  const { wording, sous_titre, label_bouton, eligible_ao, lien_redirection } = ctaSticky;
  const [heroGone, setHeroGone] = useState(false);
  const [footerVisible, setFooterVisible] = useState(false);
  // Bloc « Trouvez les fournisseurs » (QuoteFormBlock) visible à l'écran :
  // on masque la barre tant qu'il est affiché (doublon de CTA), réaffichage à sa sortie.
  const [quoteFormVisible, setQuoteFormVisible] = useState(false);
  const visible = heroGone && !footerVisible && !quoteFormVisible;

  useEffect(() => {
    const hero = document.getElementById('hero-trigger');
    const footer = document.getElementById('site-footer');
    const quoteForm = document.getElementById('quote-form-trigger');

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

    if (quoteForm) {
      const quoteFormObs = new IntersectionObserver(
        ([entry]) => setQuoteFormVisible(entry.isIntersecting),
        { threshold: 0 },
      );
      quoteFormObs.observe(quoteForm);
      observers.push(quoteFormObs);
    }

    return () => observers.forEach((o) => o.disconnect());
  }, []);

  function handleClick() {
    // Page éligible AO → ouvrir le formulaire groupée (écouté par HeroQuoteForm).
    // Sinon → simple redirection vers le lien fourni par l'API (pas de formulaire AO).
    if (eligible_ao) {
      window.dispatchEvent(new CustomEvent('hellopro:open-ao-form'));
    } else if (lien_redirection) {
      location.assign(lien_redirection);
    }
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
      {/* Inner card : centrée, max-width, bordure orange — détachée du bas (marge) sur mobile et desktop */}
      <div className="mx-3 mb-3 w-auto max-w-[1208px] rounded-lg border-2 border-cta bg-background shadow-sm sm:mx-auto sm:mb-4 sm:w-full">
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
