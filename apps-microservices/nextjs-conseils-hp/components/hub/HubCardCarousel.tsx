'use client';

import { Children, useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

/**
 * Carrousel STANDARD du HUB (convention projet, cf. mémoire hub-carousel-convention) :
 *  - design ET tailles des cartes intacts, AUCUN aperçu de la carte suivante
 *    (une « page » = largeur pleine du track → une carte par vue en mobile) ;
 *  - deux flèches cliquables EN HAUT, points (dots) EN BAS ;
 *  - défilement scroll-snap natif ; les cartes sont rendues côté serveur et
 *    passées en `children` → présentes dans le HTML initial (SEO intact) ;
 *  - `trackClass` : classes du track, y compris le repassage en GRILLE au-delà
 *    d'un breakpoint desktop (ex. `md:grid md:grid-cols-2 md:overflow-visible`) ;
 *  - `controlsHiddenClass` : masque flèches + points à ce même breakpoint.
 *
 * Pagination = NOMBRE DE CARTES (une carte par vue). On NE la déduit PAS de
 * `ceil(scrollWidth / clientWidth)` : les gaps entre cartes gonflent `scrollWidth`
 * et créaient une page fantôme en trop (flèche « suivant » jamais grisée).
 */
export function HubCardCarousel({
  children,
  label,
  className = '',
  trackClass = '',
  controlsHiddenClass = '',
}: {
  children: React.ReactNode;
  /** Nom accessible de la région défilante. */
  label: string;
  /** Classe du conteneur externe (ex. marge haute). */
  className?: string;
  /** Classes du track (gap + bascule grille desktop). */
  trackClass?: string;
  /** Classe qui masque flèches + points (au breakpoint desktop grille). */
  controlsHiddenClass?: string;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  // Une carte par vue → autant de pages que de cartes (pas de page fantôme).
  const pageCount = Math.max(1, Children.count(children));
  const [active, setActive] = useState(0);

  useEffect(() => {
    const track = trackRef.current;
    if (!track) return;
    const measure = () => {
      const step = track.scrollWidth / pageCount; // largeur d'une carte + son gap
      if (step === 0) return;
      setActive(Math.min(pageCount - 1, Math.max(0, Math.round(track.scrollLeft / step))));
    };
    measure();
    track.addEventListener('scroll', measure, { passive: true });
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null;
    observer?.observe(track);
    return () => {
      track.removeEventListener('scroll', measure);
      observer?.disconnect();
    };
  }, [pageCount]);

  const scrollToPage = (page: number) => {
    const track = trackRef.current;
    if (!track) return;
    // On vise le début de la carte `page` (largeur d'une carte + gap) ; le
    // scroll-snap ajuste au pixel près.
    track.scrollTo({ left: page * (track.scrollWidth / pageCount), behavior: 'smooth' });
  };

  return (
    <div className={className}>
      <div
        ref={trackRef}
        aria-label={label}
        tabIndex={0}
        className={`flex snap-x snap-mandatory overflow-x-auto pb-1 [-ms-overflow-style:none] [scrollbar-width:none] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring [&::-webkit-scrollbar]:hidden ${trackClass}`}
      >
        {children}
      </div>

      {/* Contrôles EN BAS : flèche gauche · points au centre · flèche droite. */}
      <div className={`mt-5 flex items-center gap-4 ${controlsHiddenClass}`}>
        <ArrowButton
          label="Cartes précédentes"
          disabled={active === 0}
          onClick={() => scrollToPage(active - 1)}
        >
          <ChevronLeft className="h-5 w-5" />
        </ArrowButton>

        <div className="flex flex-1 items-center justify-center gap-2">
          {Array.from({ length: pageCount }, (_, page) => (
            <button
              key={page}
              type="button"
              onClick={() => scrollToPage(page)}
              aria-label={`Aller à la page ${page + 1} sur ${pageCount}`}
              aria-current={page === active ? 'true' : undefined}
              className={`h-2 rounded-full transition-all ${
                page === active ? 'w-6 bg-primary' : 'w-2 bg-border hover:bg-primary/40'
              }`}
            />
          ))}
        </div>

        <ArrowButton
          label="Cartes suivantes"
          disabled={active >= pageCount - 1}
          onClick={() => scrollToPage(active + 1)}
        >
          <ChevronRight className="h-5 w-5" />
        </ArrowButton>
      </div>
    </div>
  );
}

function ArrowButton({
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
