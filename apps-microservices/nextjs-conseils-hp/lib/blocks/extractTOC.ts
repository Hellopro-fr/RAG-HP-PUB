import type { ConseilBlock } from '@/types/conseils';
import type { H2BlockData } from '@/types/blocks/h2';
import type { TocItem } from '@/components/conseil/Sidebar';

/**
 * Génère la liste des entrées du sommaire depuis les blocs BO.
 * Seuls les blocs de type 'h2' sont indexés dans le TOC.
 */
export function extractTOC(blocks: ConseilBlock[]): TocItem[] {
  return blocks
    .filter((b) => b.type === 'h2')
    .sort((a, b) => a.order - b.order)
    .map((b) => {
      const data = b.data as unknown as H2BlockData;
      return { id: data.id, label: data.title };
    });
}
