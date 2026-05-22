import { Building2 } from 'lucide-react';

// TODO Phase 8 : liste dynamique depuis l'API produits HelloPro
const SUPPLIERS = [
  {
    name: 'Triangle Élevage',
    desc: 'Bâtiments sur mesure pour bovin viande, vaches laitières, porcin, caprin et ovin avec modélisation 3D.',
    pts: ['Modélisation 3D dès l\'étude', 'Charpente & bardage dimensionnés', 'Optimisation circulation animaux'],
  },
  {
    name: 'Séré Fabricant',
    desc: 'Construction de bâtiments agricoles avec structure acier ou bois, fondations adaptées au sol.',
    pts: ['Structures acier & bois', 'Maçonnerie & longrines', 'Équipements intérieurs complets'],
  },
  {
    name: 'Groupe JLC',
    desc: 'Spécialiste de l\'élevage bovin, caprin et porcin. Étude, fabrication et installation clé en main.',
    pts: ['Toitures isolées', 'Bardage & ventilation', 'Logettes et bloc traite'],
  },
];

export function Suppliers() {
  return (
    <section id="constructeurs" className="not-prose my-12 scroll-mt-32">
      <h2 className="text-3xl font-extrabold text-foreground">
        Nos fournisseurs de bâtiments d&apos;élevage
      </h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Sélection de constructeurs de bâtiments d&apos;élevage référencés sur HelloPro.
      </p>
      <div className="mt-6 grid gap-5 md:grid-cols-3">
        {SUPPLIERS.map((s) => (
          <article
            key={s.name}
            className="rounded-xl border border-border bg-card p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
          >
            <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-lg bg-primary-soft text-primary">
              <Building2 className="h-7 w-7" />
            </div>
            <h3 className="text-lg font-extrabold text-foreground">{s.name}</h3>
            <p className="mt-3 text-sm text-foreground/90">{s.desc}</p>
            <ul className="mt-3 space-y-1 text-xs">
              {s.pts.map((p) => (
                <li key={p} className="flex gap-1.5 text-muted-foreground">
                  <span className="text-cta">›</span> {p}
                </li>
              ))}
            </ul>
            <button className="mt-4 w-full rounded-md border border-primary bg-primary/5 py-2 text-sm font-bold text-primary hover:bg-primary hover:text-primary-foreground transition">
              Demander un devis
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}
