import { ArrowRight, Lightbulb, BookOpen, Wallet, ShieldCheck } from 'lucide-react';

// TODO Phase 8 : ces données viendront de l'API (produits cités + articles liés)
const PRODUCTS = [
  { cat: 'Bâtiment modulaire', name: 'Bâtiment acier galvanisé adapté à l\'élevage avec toiture PV', price: 'Sur devis' },
  { cat: 'Stabulation', name: 'Barrière de stabulation agricole pour bovins', price: 'Dès 280 €' },
  { cat: 'Pailleuse', name: 'Pailleuse-distributrice tractée 12 m³', price: 'Dès 14 900 €' },
  { cat: 'Photovoltaïque', name: 'Hangar photovoltaïque clé en main 1 000 m²', price: 'Sur étude' },
];

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

export function Crossell() {
  return (
    <section className="not-prose my-12 space-y-10">
      {/* Produits cités */}
      <div>
        <h2 className="text-2xl font-extrabold text-foreground">
          Matériels &amp; bâtiments cités dans cet article
        </h2>
        <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PRODUCTS.map((p) => (
            <a
              key={p.name}
              href="#"
              className="group rounded-xl border border-border bg-card p-4 shadow-sm transition hover:-translate-y-0.5 hover:border-primary hover:shadow-md"
            >
              <div className="mb-3 aspect-[4/3] w-full overflow-hidden rounded-md bg-secondary">
                <div className="h-full w-full bg-gradient-to-br from-primary-soft to-secondary" />
              </div>
              <div className="text-[10px] font-bold uppercase tracking-wide text-cta">{p.cat}</div>
              <div className="mt-1 line-clamp-2 text-sm font-semibold text-foreground">{p.name}</div>
              <div className="mt-2 text-sm font-bold text-primary">{p.price}</div>
            </a>
          ))}
        </div>
      </div>

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
