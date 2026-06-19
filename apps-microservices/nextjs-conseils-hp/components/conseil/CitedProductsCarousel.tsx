'use client';

import { useRef, useState, useEffect } from 'react';
import Image from 'next/image';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { LienInterne } from '@/types/conseils';

interface CitedProductsCarouselProps {
  items: LienInterne[];
}

export function CitedProductsCarousel({ items }: CitedProductsCarouselProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  // Dédup des liens (l'API peut renvoyer des doublons) — par URL, fallback id.
  const seen = new Set<string>();
  const uniqueItems = items.filter((lien) => {
    const key = lien.url || String(lien.id);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  const showArrows = uniqueItems.length > 4;

  const updateScrollState = () => {
    const el = scrollRef.current;
    if (!el) return;
    setCanScrollLeft(el.scrollLeft > 0);
    setCanScrollRight(el.scrollLeft < el.scrollWidth - el.clientWidth - 1);
  };

  useEffect(() => {
    if (showArrows) {
      updateScrollState();
    }
  }, [showArrows]);

  const scroll = (dir: 'left' | 'right') => {
    scrollRef.current?.scrollBy({ left: dir === 'left' ? -300 : 300, behavior: 'smooth' });
  };

  return (
    <div>
      <div className="flex items-center justify-between">
        <h3 className="text-2xl font-extrabold text-foreground">
          Nos solutions, matériels &amp; services cités dans cet article
        </h3>

        {showArrows && (
          <div className="flex shrink-0 gap-2">
            <button
              onClick={() => scroll('left')}
              disabled={!canScrollLeft}
              aria-label="Précédent"
              className="flex h-8 w-8 items-center justify-center rounded-full border border-border bg-card text-foreground transition hover:border-primary hover:text-primary disabled:opacity-30"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              onClick={() => scroll('right')}
              disabled={!canScrollRight}
              aria-label="Suivant"
              className="flex h-8 w-8 items-center justify-center rounded-full border border-border bg-card text-foreground transition hover:border-primary hover:text-primary disabled:opacity-30"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>

      <div
        ref={showArrows ? scrollRef : undefined}
        onScroll={showArrows ? updateScrollState : undefined}
        className={
          showArrows
            ? 'mt-5 flex gap-4 overflow-x-auto scroll-smooth pb-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden'
            : 'mt-5 grid grid-cols-2 gap-4 sm:grid-cols-2 lg:grid-cols-4'
        }
      >
        {uniqueItems.map((lien) => (
          <a
            key={lien.id}
            href={lien.url}
            target="_blank"
            rel="noopener noreferrer"
            className={`group flex flex-col rounded-2xl border border-border bg-card shadow-sm transition hover:-translate-y-0.5 hover:shadow-md${showArrows ? ' w-56 shrink-0' : ''}`}
          >
            <div className="px-3 pt-3">
              <div className="relative aspect-[4/3] w-full overflow-hidden rounded-xl bg-gradient-to-br from-blue-100 to-blue-200">
                {lien.photo ? (
                  <Image
                    src={lien.photo}
                    alt={lien.titre}
                    fill
                    sizes="(max-width: 640px) 50vw, (max-width: 1024px) 25vw, 20vw"
                    className="object-cover transition group-hover:scale-105"
                  />
                ) : (
                  <div className="h-full w-full bg-gradient-to-br from-blue-100 to-blue-200" />
                )}
              </div>
            </div>

            <div className="flex flex-1 flex-col gap-2 p-3">
              <span className="text-sm font-bold uppercase tracking-wide text-accent">
                {lien.titre}
              </span>
              <p className="line-clamp-2 text-base font-bold leading-snug text-foreground">
                {lien.description}
              </p>
              <span className="mt-auto text-base font-semibold text-primary">
                {lien.prix ?? 'Sur devis'}
              </span>
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}
