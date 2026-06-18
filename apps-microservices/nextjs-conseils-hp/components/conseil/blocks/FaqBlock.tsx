'use client';

import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { FaqBlockData } from '@/types/blocks/faq';

function sanitizeHtml(html: string): string {
  return html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/\s+on\w+="[^"]*"/gi, '');
}

interface FaqBlockProps {
  data: FaqBlockData;
}

export function FaqBlock({ data }: FaqBlockProps) {
  const [openIndex, setOpenIndex] = useState<number>(0);
  // Le kicker orange affiche déjà « FAQ » : on retire un éventuel préfixe « FAQ » du titre API
  // (suivi de : – -) pour éviter le doublon, et on retombe sur un titre descriptif si vide.
  const faqTitle =
    (data.title ?? '').replace(/^\s*FAQ\s*[:–-]?\s*/i, '').trim() ||
    'Vos questions les plus fréquentes';
  return (
    <section id="faq" className="not-prose my-12 scroll-mt-32">
      <div className="mb-6">
        <span className="text-xs font-semibold uppercase tracking-wide text-cta">FAQ</span>
        <h2 className="mt-1 text-3xl font-extrabold text-foreground">{faqTitle}</h2>
      </div>

      <div className="space-y-3">
        {data.items.map((item, i) => (
          <div
            key={item.q}
            className="rounded-xl border border-border bg-card shadow-sm transition hover:border-primary/40"
          >
            <button
              onClick={() => setOpenIndex(openIndex === i ? -1 : i)}
              className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left"
              aria-expanded={openIndex === i}
            >
              <span className="text-base font-semibold text-foreground">{item.q}</span>
              <ChevronDown
                className={`h-5 w-5 shrink-0 text-primary transition-transform ${
                  openIndex === i ? 'rotate-180' : ''
                }`}
                aria-hidden="true"
              />
            </button>
            {openIndex === i && (
              <div className="border-t border-border px-5 py-4 text-base text-foreground/90">
                <div
                  className="[&_p]:mb-2 [&_p:last-child]:mb-0 [&_ul]:list-disc [&_ul]:pl-4 [&_li]:mb-1 [&_strong]:font-semibold [&_a]:text-primary [&_a]:underline"
                  dangerouslySetInnerHTML={{ __html: sanitizeHtml(item.a) }}
                />
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
