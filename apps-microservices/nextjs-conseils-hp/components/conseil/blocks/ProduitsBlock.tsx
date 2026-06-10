'use client';

import Image from 'next/image';
import { useRef, useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { ProduitsBlockData, ProductItem } from '@/types/blocks/produits';

const PAGE_SIZE = 6;

export function ProduitsBlock({ data }: { data: ProduitsBlockData }) {
  const { titre, produits = [] } = data;

  const items = produits.slice(0, PAGE_SIZE);

  const scrollRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const updateScrollState = () => {
    const el = scrollRef.current;
    if (!el) return;
    setCanScrollLeft(el.scrollLeft > 0);
    setCanScrollRight(el.scrollLeft < el.scrollWidth - el.clientWidth - 1);
  };

  useEffect(() => { updateScrollState(); }, [items.length]);

  const scroll = (dir: 'left' | 'right') => {
    scrollRef.current?.scrollBy({ left: dir === 'left' ? -256 : 256, behavior: 'smooth' });
  };

  if (items.length === 0) return null;

  return (
    <section className="my-8">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold leading-snug text-foreground">
            {titre ?? 'Les produits les plus populaires sur hellopro.fr'}
          </h2>
          <div className="mt-1 h-0.5 w-10 rounded-full bg-primary" />
        </div>

        <div className="flex shrink-0 gap-1 pt-0.5">
          <button
            type="button"
            onClick={() => scroll('left')}
            disabled={!canScrollLeft}
            aria-label="Produits précédents"
            className="flex h-7 w-7 items-center justify-center rounded border border-border text-muted-foreground transition-colors hover:border-primary hover:text-primary disabled:opacity-30"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => scroll('right')}
            disabled={!canScrollRight}
            aria-label="Produits suivants"
            className="flex h-7 w-7 items-center justify-center rounded border border-border text-muted-foreground transition-colors hover:border-primary hover:text-primary disabled:opacity-30"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div
        ref={scrollRef}
        onScroll={updateScrollState}
        className="flex gap-4 overflow-x-auto scroll-smooth pb-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {items.map((product) => (
          <ProductCard key={product.id} product={product} />
        ))}
      </div>
    </section>
  );
}

function ProductCard({ product }: { product: ProductItem }) {
  const priceLabel = product.priceHt
    ? `${product.priceHt.toLocaleString('fr-FR')} € HT`
    : 'Prix sur demande';

  return (
    <div className="flex w-60 shrink-0 flex-col rounded border border-border bg-background p-3">
      <a
        href={product.url}
        target="_blank"
        rel="noopener noreferrer"
        className={product.variant === 'cert' ? 'block tracking' : 'block'}
        aria-label={product.name}
      >
        <div className="relative mb-3 aspect-square w-full overflow-hidden rounded bg-muted">
          <Image
            src={product.image}
            alt=""
            fill
            className="object-contain p-2"
            sizes="240px"
          />
        </div>
        <p className="line-clamp-2 text-sm font-bold leading-tight text-foreground">
          {product.name}
        </p>
      </a>

      <p className={`mt-auto pt-2 text-sm ${product.priceHt ? 'font-semibold text-foreground' : 'text-muted-foreground'}`}>
        {priceLabel}
      </p>

      <a
        href={product.url}
        target="_blank"
        rel="noopener noreferrer"
        className={`mt-3 block rounded border border-primary px-3 py-1.5 text-center text-xs font-medium text-primary transition-colors hover:bg-primary hover:text-primary-foreground${product.variant === 'cert' ? ' tracking' : ''}`}
      >
        Envoyer un message
      </a>
    </div>
  );
}
