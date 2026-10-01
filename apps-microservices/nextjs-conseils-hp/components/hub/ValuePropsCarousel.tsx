'use client';

import { useRef, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

/**
 * Carrousel des « value props » en MOBILE (`< sm`).
 *
 * ⚠️ GRILLE HORIZONTALE (`grid-flow-col` + `auto-cols-[100%]`), PAS un flex : la
 * carte garde EXACTEMENT son comportement de grille verticale (`h-full`, `min-h`)
 * — le flex cassait `h-full`. Une carte par vue, AUCUN aperçu de la suivante.
 *
 * Convention carrousel HUB : deux flèches cliquables EN HAUT + points EN BAS
 * (cf. mémoire hub-carousel-convention). `sm+` : grille verticale d'origine, flèches
 * et points masqués. Cartes rendues côté serveur (`children`) → SEO intact.
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

  const goTo = (index: number) => {
    const el = ref.current;
    if (!el) return;
    el.scrollTo({ left: index * el.clientWidth, behavior: 'smooth' });
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

      {/* Contrôles EN BAS (mobile) : flèche gauche · points au centre · flèche droite. */}
      <div className="mt-5 flex items-center gap-4 sm:hidden">
        <Arrow label="Cartes précédentes" disabled={active === 0} onClick={() => goTo(active - 1)}>
          <ChevronLeft className="h-5 w-5" />
        </Arrow>

        <div className="flex flex-1 items-center justify-center gap-2">
          {Array.from({ length: count }).map((_, i) => (
            <button
              key={i}
              type="button"
              onClick={() => goTo(i)}
              aria-label={`Aller à la page ${i + 1} sur ${count}`}
              aria-current={i === active ? 'true' : undefined}
              className={`h-2 rounded-full transition-all ${
                i === active ? 'w-6 bg-primary' : 'w-2 bg-border hover:bg-primary/40'
              }`}
            />
          ))}
        </div>

        <Arrow label="Cartes suivantes" disabled={active >= count - 1} onClick={() => goTo(active + 1)}>
          <ChevronRight className="h-5 w-5" />
        </Arrow>
      </div>
    </>
  );
}

function Arrow({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className="flex h-10 w-10 items-center justify-center rounded-full border border-border bg-card text-foreground transition hover:border-primary/40 hover:text-primary disabled:opacity-40 disabled:hover:border-border disabled:hover:text-foreground"
    >
      {children}
    </button>
  );
}
