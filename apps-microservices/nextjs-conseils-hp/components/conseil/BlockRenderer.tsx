import type { ConseilBlock } from '@/types/conseils';
import { H2Block } from './blocks/H2Block';
import { H3Block } from './blocks/H3Block';
import { TextBlock } from './blocks/TextBlock';
import { ProsConsBlock } from './blocks/ProsConsBlock';
import { CTABlock } from './blocks/CTABlock';
import { FaqBlock } from './blocks/FaqBlock';
import { TableauPrixBlock } from './blocks/TableauPrixBlock';
import { TypeSectionBlock } from './blocks/TypeSectionBlock';
import { BrochureBlock } from './blocks/BrochureBlock';
import { QuoteFormBlock } from './blocks/QuoteFormBlock';

import type { H2BlockData } from '@/types/blocks/h2';
import type { H3BlockData } from '@/types/blocks/h3';
import type { TextBlockData } from '@/types/blocks/text';
import type { ProsConsBlockData } from '@/types/blocks/pros-cons';
import type { CTABlockData } from '@/types/blocks/cta';
import type { FaqBlockData } from '@/types/blocks/faq';
import type { TableauPrixBlockData } from '@/types/blocks/tableau-prix';
import type { TypeSectionBlockData } from '@/types/blocks/type-section';
import type { BrochureBlockData } from '@/types/blocks/brochure';
import type { QuoteFormBlockData } from '@/types/blocks/quote-form';

/**
 * BlockRenderer — switch central qui mappe un bloc BO vers son composant.
 * Voir CLAUDE.md §2.3 et §4 (pattern d'ajout de bloc).
 *
 * Couverture exhaustive garantie par le `never` dans le default.
 * Blocs Lot B (partenaire) restent en placeholder jusqu'à leur portage.
 */
export function BlockRenderer({ block }: { block: ConseilBlock }) {
  switch (block.type) {
    // ── Lot A — Erick ──────────────────────────────────────────────────────
    case 'h2':
      return <H2Block data={block.data as unknown as H2BlockData} />;
    case 'h3':
      return <H3Block data={block.data as unknown as H3BlockData} />;
    case 'texte':
      return <TextBlock data={block.data as unknown as TextBlockData} />;
    case 'pros-cons':
      return <ProsConsBlock data={block.data as unknown as ProsConsBlockData} />;
    case 'cta':
      return <CTABlock data={block.data as unknown as CTABlockData} />;
    case 'faq':
      return <FaqBlock data={block.data as unknown as FaqBlockData} />;
    case 'tableau-prix':
      return <TableauPrixBlock data={block.data as unknown as TableauPrixBlockData} />;

    // ── Lot A — blocs à porter (resume) ────────────────────────────────────
    case 'resume':
      return (
        <div className="my-4 rounded border border-dashed border-border p-4 text-sm text-muted-foreground">
          [BlockRenderer] Type <code>resume</code> — à implémenter (Lot A)
        </div>
      );

    case 'type-section':
      return <TypeSectionBlock data={block.data as unknown as TypeSectionBlockData} />;
    case 'brochure':
      return <BrochureBlock data={block.data as unknown as BrochureBlockData} />;
    case 'quote-form':
      return <QuoteFormBlock data={block.data as unknown as QuoteFormBlockData} />;

    // ── Lot B — Partenaire (placeholders) ──────────────────────────────────
    case 'image':
    case 'texte-image':
    case 'image-texte':
    case 'image-image':
    case 'video':
    case 'produits':
    case 'tableau-html':
      return (
        <div className="my-4 rounded border border-dashed border-border p-4 text-sm text-muted-foreground">
          [BlockRenderer] Type <code>{block.type}</code> — à implémenter (Lot B)
        </div>
      );

    default: {
      const exhaustive: never = block.type;
      console.warn(`[BlockRenderer] Type non géré: ${String(exhaustive)}`);
      return null;
    }
  }
}
