'use client';

import { useState } from 'react';
import { ChevronDown, Lightbulb } from 'lucide-react';
import type { ResumeItem } from '@/types/blocks/resume';

/**
 * Bloc « L'essentiel à retenir » du Hero — extrait en composant client dédié :
 * c'est la SEULE partie interactive du Hero (toggle « Voir plus » via useState).
 * Le reste du Hero est un Server Component (moins de JS + pas d'hydratation inutile).
 */
export function KeyTakeaways({ items, html, title: _title }: { items: ResumeItem[]; html?: string; title?: string }) {
  const [open, setOpen] = useState(false);
  const visible = open ? items.length : 2;

  return (
    <aside className="mt-3 max-w-xl rounded-xl border border-primary-foreground/20 bg-primary-foreground/10 p-3">
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
