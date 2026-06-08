'use client';

import Image from 'next/image';
import { useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { ProduitsBlockData, ProductItem } from '@/types/blocks/produits';

const PAGE_SIZE = 4;

export function ProduitsBlock({ data }: { data: ProduitsBlockData }) {
  const { titre, produits = [] } = data;

  // Dédoublonnage par nom (première occurrence conservée)
  const unique = produits.filter(
    (p, i, arr) => arr.findIndex((q) => q.name === p.name) === i,
  );

  const [page, setPage] = useState(0);
  const totalPages = Math.ceil(unique.length / PAGE_SIZE);
  const visible = unique.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  if (unique.length === 0) return null;

  return (
    <section className="my-8">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold leading-snug text-foreground">
            {titre ?? 'Les produits les plus populaires sur hellopro.fr'}
          </h2>
          <div className="mt-1 h-0.5 w-10 rounded-full bg-primary" />
        </div>

        {totalPages > 1 && (
          <div className="flex shrink-0 gap-1 pt-0.5">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              aria-label="Produits précédents"
              className="flex h-7 w-7 items-center justify-center rounded border border-border text-muted-foreground transition-colors hover:border-primary hover:text-primary disabled:opacity-30"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page === totalPages - 1}
              aria-label="Produits suivants"
              className="flex h-7 w-7 items-center justify-center rounded border border-border text-muted-foreground transition-colors hover:border-primary hover:text-primary disabled:opacity-30"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        {visible.map((product) => (
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
    <div className="flex flex-col rounded border border-border bg-background p-3">
      <a
        href={product.url}
        target="_blank"
        rel="noopener noreferrer"
        className="block"
        aria-label={product.name}
      >
        <div className="relative mb-3 aspect-square w-full overflow-hidden rounded bg-muted">
          <Image
            src={product.image}
            alt=""
            fill
            className="object-contain p-2"
            sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 25vw"
          />
        </div>
        <p className="line-clamp-2 text-sm font-bold leading-tight text-foreground">
          {product.name}
        </p>
      </a>

      <p className={`mt-1 text-sm ${product.priceHt ? 'font-semibold text-foreground' : 'text-muted-foreground'}`}>
        {priceLabel}
      </p>

      <a
        href={product.url}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-3 block rounded border border-primary px-3 py-1.5 text-center text-xs font-medium text-primary transition-colors hover:bg-primary hover:text-primary-foreground"
      >
        Envoyer un message
      </a>
    </div>
  );
}
