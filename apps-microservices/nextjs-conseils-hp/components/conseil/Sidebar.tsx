export interface TocItem {
  id: string;
  label: string;
}

interface SidebarProps {
  items: TocItem[];
}

/**
 * Sidebar TOC auto-générée depuis les blocs H2.
 * Composant serveur (pas de scroll-spy pour l'instant).
 * Voir lib/blocks/extractTOC.ts pour la génération des items.
 */
export function Sidebar({ items }: SidebarProps) {
  if (items.length === 0) return null;

  return (
    <aside className="lg:sticky lg:top-32 lg:self-start">
      <nav aria-label="Sommaire" className="rounded-xl border border-border bg-card p-5 shadow-sm">
        <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-muted-foreground">
          Sommaire
        </h2>
        <ul className="space-y-2 text-base">
          {items.map((item, i) => (
            <li key={item.id}>
              <a
                href={`#${item.id}`}
                className="flex gap-2 border-l-2 border-border py-1 pl-3 text-foreground transition hover:border-primary hover:text-primary"
              >
                <span className="text-xs font-bold text-muted-foreground">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span>{item.label}</span>
              </a>
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  );
}
