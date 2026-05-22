'use client';

import Image from 'next/image';
import { useState } from 'react';
import { Calendar, Clock, ChevronDown, Lightbulb } from 'lucide-react';
import type { HeroData, ConseilPageType } from '@/types/conseils';
import type { ResumeItem } from '@/types/blocks/resume';

interface HeroProps {
  data: HeroData;
  pageType: ConseilPageType;
  author?: {
    name: string;
    photo?: string;
    role?: string;
  };
  publishedAt?: string;
  readTime?: string;
  breadcrumb?: Array<{ label: string; href?: string }>;
  /** Résumé "L'essentiel à retenir" (depuis bloc BO de type resume) */
  resume?: ResumeItem[];
  /** Slot droit : QuoteForm (prix/autre) ou SuppliersCarousel (top) */
  slot?: React.ReactNode;
}

export function Hero({
  data,
  pageType,
  author,
  publishedAt,
  readTime = '7 min de lecture',
  breadcrumb = [],
  resume = [],
  slot,
}: HeroProps) {
  return (
    <section className="relative overflow-hidden bg-primary text-primary-foreground">
      {data.image && (
        <div
          className="absolute inset-0 opacity-25"
          style={{
            backgroundImage: `linear-gradient(135deg, oklch(0.36 0.18 265 / 0.85), oklch(0.2 0.1 270 / 0.95)), url(${data.image})`,
            backgroundSize: 'cover',
            backgroundPosition: 'center',
          }}
          aria-hidden="true"
        />
      )}

      <div className="relative mx-auto max-w-[1400px] px-4 py-4 lg:px-6 lg:py-5">
        {/* Breadcrumb */}
        {breadcrumb.length > 0 && (
          <nav
            aria-label="Fil d'Ariane"
            className="mb-3 flex flex-wrap items-center gap-1 text-xs text-primary-foreground/80"
          >
            {breadcrumb.map((item, i) => (
              <span key={i} className="flex items-center gap-1">
                {i > 0 && <span aria-hidden="true">›</span>}
                {item.href ? (
                  <a href={item.href} className="hover:underline">
                    {item.label}
                  </a>
                ) : (
                  <span className="text-primary-foreground">{item.label}</span>
                )}
              </span>
            ))}
          </nav>
        )}

        <div className="grid gap-5 lg:grid-cols-[1.1fr_1fr] lg:items-start">
          <div>
            <span className="mb-2 inline-flex items-center rounded-full bg-cta px-3 py-1 text-xs font-bold uppercase tracking-wide text-cta-foreground">
              Conseil d&apos;expert
            </span>

            <h1 className="text-2xl font-extrabold leading-[1.1] tracking-tight sm:text-3xl lg:text-[2rem]">
              {data.title}
            </h1>

            {data.subtitle && (
              <p className="mt-2 max-w-xl text-sm text-primary-foreground/90">
                {data.subtitle}
              </p>
            )}

            {resume.length > 0 && <KeyTakeaways items={resume} />}

            {/* Meta auteur / date */}
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-primary-foreground/80">
              {author && (
                <a href="#author" className="flex items-center gap-2 hover:text-primary-foreground">
                  {author.photo && (
                    <Image
                      src={author.photo}
                      alt={author.name}
                      width={24}
                      height={24}
                      className="h-6 w-6 rounded-full border border-primary-foreground/30 object-cover"
                    />
                  )}
                  <span>
                    Par <strong>{author.name}</strong>
                  </span>
                </a>
              )}
              {publishedAt && (
                <span className="flex items-center gap-1.5">
                  <Calendar className="h-3.5 w-3.5" /> {publishedAt}
                </span>
              )}
              <span className="flex items-center gap-1.5">
                <Clock className="h-3.5 w-3.5" /> {readTime}
              </span>
            </div>

            {/* Estimation de prix (pageType = prix) */}
            {data.estimation && (
              <PriceRangeVisual estimation={data.estimation} />
            )}
          </div>

          {/* Slot droit (QuoteForm ou SuppliersCarousel) */}
          {slot && <div>{slot}</div>}
        </div>
      </div>
    </section>
  );
}

/* ─── Sous-composants internes ───────────────────────────────────────────── */

function KeyTakeaways({ items }: { items: ResumeItem[] }) {
  const [open, setOpen] = useState(false);
  const visible = open ? items.length : 2;

  return (
    <aside className="mt-3 max-w-xl rounded-xl border border-primary-foreground/20 bg-primary-foreground/10 p-3 backdrop-blur-sm">
      <div className="mb-1.5 flex items-center gap-2">
        <Lightbulb className="h-3.5 w-3.5 text-cta" />
        <span className="text-xs font-bold uppercase tracking-wide text-primary-foreground">
          L&apos;essentiel à retenir
        </span>
      </div>
      <ul className="space-y-1 text-xs leading-snug text-primary-foreground/90">
        {items.slice(0, visible).map((it) => (
          <li key={it.label} className="flex gap-2">
            <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-cta" aria-hidden="true" />
            <span>
              <strong className="text-primary-foreground">{it.label} :</strong> {it.text}
            </span>
          </li>
        ))}
      </ul>
      {items.length > 2 && (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-cta hover:underline"
        >
          {open ? 'Voir moins' : `Voir plus (+${items.length - 2})`}
          <ChevronDown
            className={`h-3.5 w-3.5 transition-transform ${open ? 'rotate-180' : ''}`}
          />
        </button>
      )}
    </aside>
  );
}

function PriceRangeVisual({
  estimation,
}: {
  estimation: NonNullable<HeroData['estimation']>;
}) {
  const mid = Math.round((estimation.min + estimation.max) / 2).toLocaleString('fr-FR');
  const min = estimation.min.toLocaleString('fr-FR');
  const max = estimation.max.toLocaleString('fr-FR');

  return (
    <div className="relative mt-3 max-w-xl overflow-hidden rounded-xl bg-primary-foreground/[0.06] px-4 pb-3 pt-3 ring-1 ring-primary-foreground/10 backdrop-blur-sm">
      <div className="relative mb-2 text-[11px] font-bold uppercase tracking-[0.2em] text-primary-foreground">
        Estimation de prix
      </div>
      <div className="relative grid grid-cols-3 gap-1">
        <div className="rounded-lg px-3 py-2 text-left">
          <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-primary-foreground/85">
            Bas
          </div>
          <div className="mt-1 text-xl font-extrabold text-primary-foreground">
            {min} {estimation.unit}
          </div>
        </div>
        <div className="rounded-lg bg-primary-foreground/[0.09] px-3 py-2 text-left ring-1 ring-primary-foreground/10">
          <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-cta">
            Moyen
          </div>
          <div className="mt-1 text-2xl font-extrabold text-primary-foreground">
            {mid} {estimation.unit}
          </div>
          <div className="mt-2 h-[3px] w-12 rounded-full bg-cta" />
        </div>
        <div className="rounded-lg px-3 py-2 text-left">
          <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-primary-foreground/85">
            Haut
          </div>
          <div className="mt-1 text-xl font-extrabold text-primary-foreground">
            {max} {estimation.unit}
          </div>
        </div>
      </div>
    </div>
  );
}
