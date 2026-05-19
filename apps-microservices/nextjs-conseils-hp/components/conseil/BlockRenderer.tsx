import { ConseilBlock } from '@/types/conseils';

/**
 * BlockRenderer — switch central qui mappe un bloc BO vers son composant.
 * Voir CLAUDE.md §2.3 et §4 (pattern d'ajout de bloc).
 *
 * Couverture exhaustive garantie par le `never` dans le default.
 */
export function BlockRenderer({ block }: { block: ConseilBlock }) {
  switch (block.type) {
    // Phase 4 — Blocs textuels (Erick)
    case 'h2':
    case 'h3':
    case 'texte':
    case 'resume':
    case 'pros-cons':
    case 'cta':
    case 'faq':
      return (
        <div className="my-4 rounded border border-dashed border-border p-4 text-sm text-muted-foreground">
          [BlockRenderer] Type <code>{block.type}</code> à implémenter
        </div>
      );

    // Phase 5 — Blocs media + données (Partenaire)
    case 'image':
    case 'texte-image':
    case 'image-texte':
    case 'image-image':
    case 'video':
    case 'produits':
    case 'tableau-html':
    case 'tableau-prix':
      return (
        <div className="my-4 rounded border border-dashed border-border p-4 text-sm text-muted-foreground">
          [BlockRenderer] Type <code>{block.type}</code> à implémenter
        </div>
      );

    default: {
      const exhaustive: never = block.type;
      console.warn(`[BlockRenderer] Type non géré: ${String(exhaustive)}`);
      return null;
    }
  }
}
