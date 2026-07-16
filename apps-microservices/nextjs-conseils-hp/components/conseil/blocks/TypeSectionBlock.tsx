'use client';

import Image from 'next/image';
import { ArrowRight } from 'lucide-react';
import type { TypeSectionBlockData } from '@/types/blocks/type-section';

interface TypeSectionBlockProps {
  data: TypeSectionBlockData;
}

export function TypeSectionBlock({ data }: TypeSectionBlockProps) {
  const {
    id,
    title,
    estimate,
    imageUrl,
    imageAlt,
    descriptionHtml,
    bullets,
    ctaLabel = 'Demander un devis',
    ctaUrl = '#',
  } = data;

  return (
    <section id={id} className="not-prose my-10 scroll-mt-32">
      <h3 className="mb-4 text-2xl font-extrabold text-foreground">{title}</h3>
      <div className="grid gap-6 lg:grid-cols-[1.1fr_1fr] lg:items-stretch">
        {/* Colonne texte */}
        <div>
          <div className="mb-4 inline-flex items-baseline gap-2 rounded-md bg-primary-soft px-3 py-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-primary">
              Estimation
            </span>
            <span className="text-lg font-extrabold text-primary">{estimate}</span>
          </div>

          <div
            className="space-y-3 text-sm leading-relaxed text-foreground/90"
            dangerouslySetInnerHTML={{ __html: descriptionHtml }}
          />

          <ul className="mt-4 space-y-1.5 text-sm">
            {bullets.map((b) => (
              <li key={b} className="flex gap-2">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-cta" />
                <span>{b}</span>
              </li>
            ))}
          </ul>

          <a
            href={ctaUrl}
            className="mt-5 inline-flex items-center gap-2 rounded-md bg-cta px-5 py-2.5 text-sm font-bold uppercase tracking-wide text-cta-foreground hover:bg-cta-hover"
          >
            {ctaLabel} <ArrowRight className="h-4 w-4" />
          </a>
        </div>

        {/* Colonne image */}
        <div className="relative overflow-hidden rounded-xl border border-border shadow-sm">
          <Image
            src={imageUrl}
            alt={imageAlt ?? title}
            fill
            className="object-cover"
            sizes="(max-width: 1024px) 100vw, 50vw"
            loading="lazy"
          />
        </div>
      </div>
    </section>
  );
}
