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
  // Titre tel quel (le préfixe « FAQ : » de l'API est conservé).
  // Cas où le BO ne renvoie qu'un « FAQ » générique (ou vide) → titre par défaut complet.
  const rawTitle = (data.title ?? '').trim();
  const isGeneric = rawTitle === '' || /^faq\s*:?\s*$/i.test(rawTitle);
  const faqTitle = isGeneric ? 'FAQ : Vos questions les plus fréquentes' : rawTitle;
  return (
    <section id="faq" className="not-prose my-12 scroll-mt-32">
      <div className="mb-6">
        <h2 className="text-3xl font-extrabold text-foreground">{faqTitle}</h2>
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
