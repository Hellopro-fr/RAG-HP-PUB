'use client';

import { useRef, useState } from 'react';

/**
 * Carrousel des « value props » en MOBILE (`< sm`).
 *
 * ⚠️ On utilise une GRILLE HORIZONTALE (`grid-flow-col` + `auto-cols`), PAS un
 * flex : ainsi la carte garde EXACTEMENT le comportement qu'elle a en grille
 * verticale (`h-full`, `min-h`, hauteur de rangée) — le flex cassait `h-full`.
 * La carte n'est donc pas modifiée, seul le conteneur change de sens.
 *
 * `sm+` : retour à la grille verticale d'origine (2 puis 4 colonnes).
 * Indicateur de défilement (pastilles) sous le carrousel, `sm:hidden`, suit la
 * progression du scroll. Seul cet habillage est client ; les cartes restent
 * rendues côté serveur (passées en `children`) → SEO intact.
 */
export function ValuePropsCarousel({
  count,
  children,
}: {
  count: number;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);

  const onScroll = () => {
    const el = ref.current;
    if (!el || count < 2) return;
    const max = el.scrollWidth - el.clientWidth;
    const progress = max > 0 ? el.scrollLeft / max : 0;
    setActive(Math.round(progress * (count - 1)));
  };

  return (
    <>
      <div
        ref={ref}
        onScroll={onScroll}
        className="mt-8 grid grid-flow-col auto-cols-[100%] gap-4 overflow-x-auto pb-1 snap-x snap-mandatory [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden sm:grid-flow-row sm:auto-cols-auto sm:grid-cols-2 sm:overflow-visible lg:grid-cols-4"
      >
        {children}
      </div>

      {/* Indicateur de défilement — mobile uniquement, décoratif. */}
      <div className="mt-5 flex items-center justify-center gap-1.5 sm:hidden" aria-hidden>
        {Array.from({ length: count }).map((_, i) => (
          <span
            key={i}
            className={`h-1.5 rounded-full transition-all duration-300 ${
              i === active ? 'w-5 bg-primary' : 'w-1.5 bg-border'
            }`}
          />
        ))}
      </div>
    </>
  );
}
