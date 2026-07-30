'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

/**
 * Carrousel de cartes — défilement natif en scroll-snap, commandes en JavaScript.
 *
 * POURQUOI PAS EMBLA
 * Le contenu doit rester intégralement dans le HTML initial pour être indexé. Ici
 * les cartes sont de vrais enfants rendus côté serveur (passés en `children`), le
 * défilement est assuré par CSS (`overflow-x` + `snap-x`), et le JavaScript
 * n'ajoute QUE les commandes. Sans JS : le carrousel reste utilisable au doigt,
 * au trackpad et au clavier. Une librairie de carrousel aurait monté les cartes
 * côté client, donc les aurait sorties du rendu utile.
 *
 * PAGINATION MESURÉE, PAS DÉDUITE
 * Le nombre de cartes par vue change selon le point de rupture (1 / 2 / 3). Plutôt
 * que de dupliquer ces seuils en JS — deux sources de vérité à garder synchrones —
 * on mesure `scrollWidth / clientWidth`. La pagination suit donc automatiquement
 * la mise en page, quel que soit le nombre de cartes.
 */
export function CardCarousel({
  children,
  label,
}: {
  children: React.ReactNode;
  /** Nom accessible de la région défilante. */
  label: string;
}) {
  const trackRef = useRef<HTMLUListElement>(null);
  const [pageCount, setPageCount] = useState(1);
  const [activePage, setActivePage] = useState(0);

  const measure = useCallback(() => {
    const track = trackRef.current;
    if (!track) return;
    const perPage = track.clientWidth;
    if (perPage === 0) return;
    // -1px de tolérance : les largeurs fractionnaires font sinon apparaître une
    // page fantôme de quelques pixels.
    setPageCount(Math.max(1, Math.ceil((track.scrollWidth - 1) / perPage)));
    setActivePage(Math.round(track.scrollLeft / perPage));
  }, []);

  useEffect(() => {
    measure();
    const track = trackRef.current;
    if (!track) return;

    track.addEventListener('scroll', measure, { passive: true });
    // ResizeObserver absent de jsdom : on dégrade sans casser le rendu.
    const observer =
      typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null;
    observer?.observe(track);

    return () => {
      track.removeEventListener('scroll', measure);
      observer?.disconnect();
    };
  }, [measure]);

  const scrollToPage = (page: number) => {
    const track = trackRef.current;
    if (!track) return;
    track.scrollTo({ left: page * track.clientWidth, behavior: 'smooth' });
  };

  const hasControls = pageCount > 1;

  return (
    <div className="relative">
      <ul
        ref={trackRef}
        aria-label={label}
        tabIndex={0}
        className="flex snap-x snap-mandatory gap-5 overflow-x-auto pb-1 [-ms-overflow-style:none] [scrollbar-width:none] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring [&::-webkit-scrollbar]:hidden"
      >
        {children}
      </ul>

      {hasControls && (
        // Flèches aux deux extrémités, pastilles centrées entre elles.
        <div className="mt-5 flex items-center gap-4">
          {/* Masquées sur mobile : le défilement au doigt s'y suffit, et deux
              flèches de 40 px mangeraient la largeur utile des pastilles. */}
          <div className="hidden sm:block">
            <ArrowButton
              label="Cartes précédentes"
              disabled={activePage === 0}
              onClick={() => scrollToPage(activePage - 1)}
            >
              <ChevronLeft className="h-5 w-5" />
            </ArrowButton>
          </div>

          <div className="flex flex-1 items-center justify-center gap-2">
            {Array.from({ length: pageCount }, (_, page) => (
              <button
                key={page}
                type="button"
                onClick={() => scrollToPage(page)}
                aria-label={`Aller à la page ${page + 1} sur ${pageCount}`}
                aria-current={page === activePage ? 'true' : undefined}
                className={`h-2 rounded-full transition-all ${
                  page === activePage ? 'w-6 bg-primary' : 'w-2 bg-border hover:bg-primary/40'
                }`}
              />
            ))}
          </div>

          <div className="hidden sm:block">
            <ArrowButton
              label="Cartes suivantes"
              disabled={activePage >= pageCount - 1}
              onClick={() => scrollToPage(activePage + 1)}
            >
              <ChevronRight className="h-5 w-5" />
            </ArrowButton>
          </div>
        </div>
      )}
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
