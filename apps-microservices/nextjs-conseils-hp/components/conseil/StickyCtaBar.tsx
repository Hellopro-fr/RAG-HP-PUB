'use client';

import { useEffect, useRef, useState } from 'react';
import { ArrowRight } from 'lucide-react';
import type { CtaSticky } from '@/types/conseils';

interface StickyCtaBarProps {
  ctaSticky: CtaSticky;
}

export function StickyCtaBar({ ctaSticky }: StickyCtaBarProps) {
  const { wording, sous_titre, label_bouton } = ctaSticky;
  const [visible, setVisible] = useState(false);
  const hasObserver = useRef(false);

  useEffect(() => {
    const hero = document.getElementById('hero-trigger');
    if (!hero || hasObserver.current) return;
    hasObserver.current = true;

    const observer = new IntersectionObserver(
      ([entry]) => setVisible(!entry.isIntersecting),
      { threshold: 0 },
    );
    observer.observe(hero);
    return () => observer.disconnect();
  }, []);

  function handleClick() {
    window.dispatchEvent(new CustomEvent('hellopro:open-ao-form'));
  }

  return (
    <div
      role="region"
      aria-label="Demande de devis"
      className={[
        'fixed inset-x-0 bottom-0 z-50 border-t-2 border-primary bg-background shadow-[0_-6px_32px_rgba(0,0,0,0.12)] transition-transform duration-300',
        visible ? 'translate-y-0' : 'translate-y-full',
      ].join(' ')}
    >
      <div className="mx-auto flex max-w-[1400px] flex-col gap-2.5 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4 sm:px-6 sm:py-4">
        {/* Texte */}
        <div>
          <p className="text-sm font-bold text-foreground sm:text-lg">{wording}</p>
          {sous_titre && (
            <p className="text-xs text-muted-foreground sm:text-sm">{sous_titre}</p>
          )}
        </div>

        {/* Bouton CTA — pleine largeur mobile, auto desktop */}
        <button
          type="button"
          onClick={handleClick}
          className="flex w-full cursor-pointer items-center justify-center gap-2 rounded-md bg-cta px-5 py-2.5 text-sm font-bold text-cta-foreground shadow transition hover:bg-cta-hover sm:w-auto sm:shrink-0 sm:text-base"
        >
          {label_bouton} <ArrowRight className="h-4 w-4 shrink-0" />
        </button>
      </div>
    </div>
  );
}
