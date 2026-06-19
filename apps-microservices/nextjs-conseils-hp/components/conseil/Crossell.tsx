import { Lightbulb, Wallet, BookOpen, ArrowRight } from 'lucide-react';
import type { LienInterne, ConseilAssocie } from '@/types/conseils';
import { CitedProductsCarousel } from './CitedProductsCarousel';

interface CrossellProps {
  liensIntexts?: LienInterne[];
  conseilsAssocies?: ConseilAssocie[];
}

const TAG_CONFIG: Record<number, { label: string; style: string; icon: typeof Lightbulb }> = {
  0: { label: 'Conseil',    style: 'bg-cta/15 text-cta',         icon: Lightbulb },
  1: { label: 'Guide',      style: 'bg-primary/10 text-primary',  icon: BookOpen },
  2: { label: 'Comparatif', style: 'bg-success/15 text-success',  icon: Wallet },
};
const DEFAULT_TAG = TAG_CONFIG[0];

export function Crossell({ liensIntexts, conseilsAssocies }: CrossellProps) {
  return (
    <section className="not-prose my-12 space-y-10">
      {liensIntexts && liensIntexts.length > 0 && (
        <CitedProductsCarousel items={liensIntexts} />
      )}

      {conseilsAssocies && conseilsAssocies.length > 0 && (
        <div>
          <h3 className="text-2xl font-extrabold text-foreground">Pour aller plus loin</h3>
          <div className="mt-5 grid gap-3 md:grid-cols-2">
            {conseilsAssocies.map((a) => {
              const { label, style, icon: Icon } = TAG_CONFIG[a.idTag] ?? DEFAULT_TAG;
              return (
                <a
                  key={a.id}
                  href={a.url}
                  className="group flex items-start justify-between gap-3 rounded-md border border-border bg-card p-4 transition hover:border-primary hover:shadow-sm"
                >
                  <div className="flex items-start gap-3">
                    <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md ${style}`}>
                      <Icon className="h-4 w-4" />
                    </span>
                    <div>
                      <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-bold uppercase tracking-wide ${style}`}>
                        {label}
                      </span>
                      <p className="mt-1 text-base font-semibold text-foreground group-hover:text-primary">
                        {a.titre}
                      </p>
                    </div>
                  </div>
                  <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition group-hover:text-primary" />
                </a>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
