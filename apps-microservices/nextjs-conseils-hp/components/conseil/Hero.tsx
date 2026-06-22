'use client';

import Image from 'next/image';
import { useState } from 'react';
import { Calendar, Clock, ChevronDown, Lightbulb, Home } from 'lucide-react';
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
  /** Résumé "L'essentiel à retenir" (items structurés — fallback mock) */
  resume?: ResumeItem[];
  /** Titre extrait du bloc type 15 — remplace le label hardcodé si présent */
  resumeTitle?: string;
  /** HTML brut du bloc type 15 de l'API — prioritaire sur resume si présent */
  resumeHtml?: string;
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
  resumeTitle,
  resumeHtml,
  slot,
}: HeroProps) {
  return (
    <section id="hero-trigger" className="relative overflow-hidden bg-primary text-primary-foreground">
      <div className="relative mx-auto max-w-[1400px] px-4 py-4 lg:px-6 lg:py-5">
        {/* Breadcrumb */}
        {breadcrumb.length > 0 && (
          <nav
            aria-label="Fil d'Ariane"
            className="mb-3 hidden min-[769px]:flex flex-wrap items-center gap-1 text-xs text-primary-foreground/80"
          >
            {breadcrumb.map((item, i) => (
              <span key={i} className="flex items-center gap-1">
                {i > 0 && <span aria-hidden="true">›</span>}
                {item.href ? (
                  <a href={item.href} className="hover:underline" aria-label={i === 0 ? item.label : undefined}>
                    {i === 0 ? <Home className="h-3.5 w-3.5" /> : item.label}
                  </a>
                ) : (
                  <span className="text-primary-foreground">{i === 0 ? <Home className="h-3.5 w-3.5" /> : item.label}</span>
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

            <h1 className="text-3xl font-extrabold leading-[1.1] tracking-tight sm:text-4xl lg:text-[2.75rem]">
              {data.title}
            </h1>

            {(resumeHtml || resume.length > 0) && (
              <KeyTakeaways items={resume} html={resumeHtml} title={resumeTitle} />
            )}

            {/* Slot mobile — juste avant les métas auteur */}
            {slot && <div className="mt-4 lg:hidden">{slot}</div>}

            {/* Meta auteur / date */}
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-base text-primary-foreground/80">
              {author && (
                <a href="#author" className="flex items-center gap-2 hover:text-primary-foreground">
                  {author.photo ? (
                    <Image
                      src={author.photo}
                      alt={author.name}
                      width={24}
                      height={24}
                      className="h-6 w-6 rounded-full border border-primary-foreground/30 object-cover"
                    />
                  ) : (
                    <span
                      aria-hidden="true"
                      className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-primary-foreground/30 bg-primary-foreground/15 text-[10px] font-bold uppercase text-primary-foreground"
                    >
                      {author.name
                        .split(' ')
                        .slice(0, 2)
                        .map((w) => w[0])
                        .join('')}
                    </span>
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

            {/* Estimation de prix — uniquement sur les pages de type prix */}
            {pageType === 'prix' && data.estimation && (
              <PriceRangeVisual estimation={data.estimation} />
            )}
          </div>

          {/* Slot desktop — colonne droite */}
          {slot && <div className="hidden lg:block">{slot}</div>}
        </div>
      </div>
    </section>
  );
}

/* ─── Sous-composants internes ───────────────────────────────────────────── */

function KeyTakeaways({ items, html, title: _title }: { items: ResumeItem[]; html?: string; title?: string }) {
  const [open, setOpen] = useState(false);
  const visible = open ? items.length : 2;

  return (
    <aside className="mt-3 max-w-xl rounded-xl border border-primary-foreground/20 bg-primary-foreground/10 p-3 backdrop-blur-sm">
      <div className="flex gap-2">
        <Lightbulb className="mt-0.5 h-5 w-5 shrink-0 text-cta" />
        <div
          className="min-w-0 flex-1 text-base leading-snug text-primary-foreground/90
            [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-4
            [&_ol]:list-decimal [&_ol]:space-y-1 [&_ol]:pl-4
            [&_li]:mb-0.5
            [&_strong]:font-semibold [&_strong]:text-primary-foreground"
        >
          {html ? (() => {
            const cleaned = html.replace(/^(\s*(?:<[^>]*>\s*)*)💡\s*/, '$1');
            const allLis = [...cleaned.matchAll(/<li[^>]*>[\s\S]*?<\/li>/gi)].map(m => m[0]);
            const hasMore = allLis.length > 2;
            const ulStart = cleaned.indexOf('<ul');
            const prefix = ulStart > 0 ? cleaned.slice(0, ulStart) : '';
            const visibleHtml = allLis.length > 0
              ? `${prefix}<ul>${(open ? allLis : allLis.slice(0, 2)).join('')}</ul>`
              : cleaned;
            return (
              <>
                <div dangerouslySetInnerHTML={{ __html: visibleHtml }} />
                {hasMore && (
                  <button
                    type="button"
                    onClick={() => setOpen(v => !v)}
                    className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-cta hover:underline"
                  >
                    {open ? 'Voir moins' : `Voir plus (+${allLis.length - 2})`}
                    <ChevronDown className={`h-3.5 w-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
                  </button>
                )}
              </>
            );
          })() : (
            <>
              <ul className="space-y-1">
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
            </>
          )}
        </div>
      </div>
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
      {/* Courbe décorative en fond */}
      <svg
        viewBox="0 0 400 100"
        preserveAspectRatio="none"
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 bottom-0 h-full w-full"
      >
        <defs>
          <linearGradient id="priceCurveStroke" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor="white" stopOpacity="0" />
            <stop offset="50%" stopColor="hsl(27 90% 60%)" stopOpacity="0.9" />
            <stop offset="100%" stopColor="white" stopOpacity="0" />
          </linearGradient>
          <radialGradient id="priceCurveGlow" cx="0.5" cy="1" r="0.6">
            <stop offset="0%" stopColor="hsl(27 90% 60%)" stopOpacity="0.18" />
            <stop offset="100%" stopColor="hsl(27 90% 60%)" stopOpacity="0" />
          </radialGradient>
        </defs>
        <ellipse cx="200" cy="100" rx="140" ry="70" fill="url(#priceCurveGlow)" />
        <path
          d="M 0 95 C 90 95, 140 30, 200 30 C 260 30, 310 95, 400 95"
          fill="none"
          stroke="url(#priceCurveStroke)"
          strokeWidth="1.25"
          strokeLinecap="round"
        />
      </svg>
      <div className="relative mb-2 text-sm font-bold uppercase tracking-[0.2em] text-primary-foreground">
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
          <div className="mt-2 h-[3px] w-8 rounded-full bg-primary-foreground/30" />
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
          <div className="mt-2 h-[3px] w-8 rounded-full bg-primary-foreground/30" />
        </div>
      </div>
    </div>
  );
}
