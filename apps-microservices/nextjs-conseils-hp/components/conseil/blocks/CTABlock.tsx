import { ArrowRight } from 'lucide-react';
import type { CTABlockData } from '@/types/blocks/cta';

interface CTABlockProps {
  data: CTABlockData;
}

export function CTABlock({ data }: CTABlockProps) {
  return (
    <div className="my-8 flex flex-col gap-4 rounded-xl border border-cta/30 bg-gradient-to-br from-cta/10 via-card to-card p-5 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center gap-4">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-cta/15 text-cta">
          <ArrowRight className="h-6 w-6" aria-hidden="true" />
        </div>
        <div>
          <p className="font-bold text-foreground">{data.title}</p>
          {data.subtitle && (
            <p className="text-sm text-muted-foreground">{data.subtitle}</p>
          )}
        </div>
      </div>
      {data.ctaUrl ? (
        <a
          href={data.ctaUrl}
          className="shrink-0 rounded-md bg-cta px-5 py-3 text-sm font-bold uppercase tracking-wide text-cta-foreground shadow-md hover:bg-cta-hover"
        >
          {data.ctaLabel}
        </a>
      ) : (
        <button className="shrink-0 rounded-md bg-cta px-5 py-3 text-sm font-bold uppercase tracking-wide text-cta-foreground shadow-md hover:bg-cta-hover">
          {data.ctaLabel}
        </button>
      )}
    </div>
  );
}
