'use client';

import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { FaqBlockData } from '@/types/blocks/faq';

interface FaqBlockProps {
  data: FaqBlockData;
}

export function FaqBlock({ data }: FaqBlockProps) {
  const [openIndex, setOpenIndex] = useState<number>(0);
  return (
    <section id="faq" className="not-prose my-12 scroll-mt-32">
      <div className="mb-6">
        <span className="text-xs font-semibold uppercase tracking-wide text-cta">FAQ</span>
        <h2 className="mt-1 text-3xl font-extrabold text-foreground">
          Vos questions les plus fréquentes
        </h2>
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
              <span className="font-semibold text-foreground">{item.q}</span>
              <ChevronDown
                className={`h-5 w-5 shrink-0 text-primary transition-transform ${
                  openIndex === i ? 'rotate-180' : ''
                }`}
                aria-hidden="true"
              />
            </button>
            {openIndex === i && (
              <div className="border-t border-border px-5 py-4 text-sm text-foreground/90">
                {item.a}
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
