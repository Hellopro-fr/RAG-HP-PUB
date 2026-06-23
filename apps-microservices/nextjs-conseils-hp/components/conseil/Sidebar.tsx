'use client';

import { useEffect, useState } from 'react';

export interface TocItem {
  id: string;
  label: string;
}

interface SidebarProps {
  items: TocItem[];
}

/**
 * Sidebar TOC auto-générée depuis les blocs H2.
 * Composant client : suit la progression de lecture (scroll) et remplit, trait par
 * trait, le rail strié à gauche de chaque item. Le remplissage de chaque segment est
 * proportionnel à l'avancée dans la section correspondante ; le texte des sections
 * déjà atteintes passe en couleur primaire.
 * Voir lib/blocks/extractTOC.ts pour la génération des items.
 */
export function Sidebar({ items }: SidebarProps) {
  const [fills, setFills] = useState<number[]>(() => items.map(() => 0));

  useEffect(() => {
    if (items.length === 0) return;

    let raf = 0;
    const compute = () => {
      raf = 0;
      // Ligne de lecture virtuelle à 30 % du haut du viewport.
      const readingLine = window.scrollY + window.innerHeight * 0.3;
      const tops = items.map((it) => {
        const el = document.getElementById(it.id);
        return el ? el.getBoundingClientRect().top + window.scrollY : Number.POSITIVE_INFINITY;
      });
      const docEnd = document.documentElement.scrollHeight;

      setFills(
        items.map((_, i) => {
          const top = tops[i];
          if (!Number.isFinite(top)) return 0;
          // Fin de la section = début de la suivante, sinon fin du document.
          const end =
            i + 1 < tops.length && Number.isFinite(tops[i + 1]) ? tops[i + 1] : docEnd;
          if (end <= top) return readingLine >= top ? 1 : 0;
          return Math.max(0, Math.min(1, (readingLine - top) / (end - top)));
        }),
      );
    };

    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(compute);
    };

    compute();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [items]);

  if (items.length === 0) return null;

  return (
    <aside className="lg:sticky lg:top-32 lg:self-start">
      <nav aria-label="Sommaire" className="rounded-xl border border-border bg-card p-5 shadow-sm">
        <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-muted-foreground">
          Sommaire
        </h2>
        <ul className="space-y-2 text-base">
          {items.map((item, i) => {
            const fill = fills[i] ?? 0;
            const reached = fill > 0;
            return (
              <li key={item.id}>
                <a
                  href={`#${item.id}`}
                  className={`group flex items-stretch gap-2 py-1 transition-colors ${
                    reached ? 'text-primary' : 'text-foreground hover:text-primary'
                  }`}
                >
                  {/* Rail strié : trait gris + remplissage bleu proportionnel à la lecture */}
                  <span
                    className="relative w-0.5 shrink-0 rounded-full bg-border"
                    aria-hidden="true"
                  >
                    <span
                      className="absolute inset-x-0 top-0 rounded-full bg-primary transition-[height] duration-200 ease-out"
                      style={{ height: `${Math.round(fill * 100)}%` }}
                    />
                  </span>
                  <span
                    className={`pl-1 text-xs font-bold ${
                      reached ? 'text-primary' : 'text-muted-foreground'
                    }`}
                  >
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <span>{item.label}</span>
                </a>
              </li>
            );
          })}
        </ul>
      </nav>
    </aside>
  );
}
