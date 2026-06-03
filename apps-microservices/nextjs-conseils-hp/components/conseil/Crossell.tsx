import Image from 'next/image';
import { ArrowRight, Lightbulb, BookOpen, Wallet, ShieldCheck } from 'lucide-react';
import type { LienInterne } from '@/types/conseils';

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
        <div>
          <h2 className="text-2xl font-extrabold text-foreground">
            Matériels &amp; bâtiments cités dans cet article
          </h2>
          <div className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {liensIntexts.map((lien) => (
              <a
                key={lien.id}
                href={lien.url}
                target="_blank"
                rel="noopener noreferrer"
                className="group flex flex-col rounded-xl border border-border bg-card shadow-sm transition hover:-translate-y-0.5 hover:border-primary hover:shadow-md"
              >
                {/* Image */}
                <div className="relative aspect-[4/3] w-full overflow-hidden rounded-t-xl bg-secondary">
                  {lien.photo ? (
                    <Image
                      src={lien.photo}
                      alt={lien.titre}
                      fill
                      sizes="(max-width: 640px) 50vw, (max-width: 1024px) 25vw, 20vw"
                      className="object-cover transition group-hover:scale-105"
                    />
                  ) : (
                    <div className="h-full w-full bg-gradient-to-br from-primary/10 to-secondary" />
                  )}
                </div>

                {/* Contenu */}
                <div className="flex flex-1 flex-col gap-1.5 p-3">
                  <p className="line-clamp-2 text-sm font-semibold leading-snug text-foreground group-hover:text-primary">
                    {lien.titre}
                  </p>
                  {lien.description && (
                    <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                      {lien.description}
                    </p>
                  )}
                </div>
              </a>
            ))}
          </div>
        </div>
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
                <ArrowRight className="mt-1 h-4 w-4 shrink-0 text-primary transition group-hover:translate-x-1" />
              </a>
            );
          })}
        </div>
      </div>
    </section>
  );
}
