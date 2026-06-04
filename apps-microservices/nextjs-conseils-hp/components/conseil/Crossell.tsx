import { Lightbulb, BookOpen, Wallet, ShieldCheck } from 'lucide-react';
import type { LienInterne } from '@/types/conseils';
import { CitedProductsCarousel } from './CitedProductsCarousel';

interface CrossellProps {
  liensIntexts?: LienInterne[];
}

// TODO Phase 8 : remplacer par données API (articles liés)
type ArticleType = 'Conseil' | 'Guide' | 'Financement' | 'Réglementation';
const ARTICLES: { type: ArticleType; title: string; icon: typeof Lightbulb }[] = [
  { type: 'Conseil', title: 'Tout savoir sur l\'installation de panneaux photovoltaïques sur des bâtiments agricoles', icon: Lightbulb },
  { type: 'Guide', title: 'Comparatif structure bois vs acier pour bâtiments d\'élevage', icon: BookOpen },
  { type: 'Financement', title: 'Comment financer la construction d\'un bâtiment agricole en 2026 ?', icon: Wallet },
  { type: 'Réglementation', title: 'Les normes environnementales applicables aux bâtiments d\'élevage', icon: ShieldCheck },
];

const TYPE_STYLES: Record<ArticleType, string> = {
  Conseil: 'bg-cta/15 text-cta',
  Guide: 'bg-primary/10 text-primary',
  Financement: 'bg-success/15 text-success',
  Réglementation: 'bg-foreground/10 text-foreground',
};

export function Crossell({ liensIntexts }: CrossellProps) {
  return (
    <section className="not-prose my-12 space-y-10">
      {/* Produits cités — dynamique depuis liens_intexts */}
      {liensIntexts && liensIntexts.length > 0 && (
        <CitedProductsCarousel items={liensIntexts} />
      )}

      {/* Pour aller plus loin */}
      <div>
        <h2 className="text-2xl font-extrabold text-foreground">Pour aller plus loin</h2>
        <div className="mt-5 grid gap-3 md:grid-cols-2">
          {ARTICLES.map((a) => {
            const Icon = a.icon;
            return (
              <a
                key={a.title}
                href="#"
                className="group flex items-start justify-between gap-3 rounded-md border border-border bg-card p-4 transition hover:border-primary hover:shadow-sm"
              >
                <div className="flex items-start gap-3">
                  <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md ${TYPE_STYLES[a.type]}`}>
                    <Icon className="h-4 w-4" />
                  </span>
                  <div>
                    <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${TYPE_STYLES[a.type]}`}>
                      {a.type}
                    </span>
                    <p className="mt-1 text-sm font-semibold text-foreground group-hover:text-primary">
                      {a.title}
                    </p>
                  </div>
                </div>
              </a>
            );
          })}
        </div>
      </div>
    </section>
  );
}
