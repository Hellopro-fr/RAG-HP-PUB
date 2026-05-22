import { SiteHeader } from './SiteHeader';
import { SiteFooter } from './SiteFooter';
import { Hero } from './Hero';
import { Sidebar } from './Sidebar';
import { AuthorBlock } from './AuthorBlock';
import { BlockRenderer } from './BlockRenderer';
import { extractTOC } from '@/lib/blocks/extractTOC';
import type { ConseilPage } from '@/types/conseils';
import type { ResumeBlockData } from '@/types/blocks/resume';

interface ConseilTemplateProps {
  page: ConseilPage;
}

/**
 * Orchestrateur principal des pages conseils.
 * Composant serveur — les sous-composants interactifs (Hero, FaqBlock…)
 * sont marqués 'use client' individuellement.
 *
 * Voir CLAUDE.md §2.2.
 */
export function ConseilTemplate({ page }: ConseilTemplateProps) {
  const tocItems = extractTOC(page.blocks);

  // Extraire le bloc resume pour l'afficher dans le Hero
  const resumeBlock = page.blocks.find((b) => b.type === 'resume');
  const resumeItems = resumeBlock
    ? (resumeBlock.data as unknown as ResumeBlockData).items
    : [];

  // Blocs à rendre (exclure le resume qui est intégré dans le Hero)
  const contentBlocks = page.blocks
    .filter((b) => b.type !== 'resume')
    .sort((a, b) => a.order - b.order);

  return (
    <>
      <SiteHeader />

      <Hero
        data={page.hero}
        pageType={page.pageType}
        resume={resumeItems}
        breadcrumb={[
          { label: 'Accueil', href: 'https://www.hellopro.fr' },
          { label: 'Conseils', href: '/' },
          { label: page.hero.title },
        ]}
      />

      <main className="mx-auto max-w-[1400px] grid lg:grid-cols-[280px_1fr] gap-10 px-4 py-10 lg:px-6">
        <Sidebar items={tocItems} />

        <article className="min-w-0">
          {/* Blocs spécifiques au pageType — insérés à position fixe avant les blocs BO */}
          {page.pageType === 'prix' && page.priceData !== undefined && (
            <div className="my-4 rounded border border-dashed border-border p-4 text-sm text-muted-foreground">
              [PriceSimulator] À implémenter (Phase 8)
            </div>
          )}
          {page.pageType === 'top' && page.topFabricants !== undefined && (
            <div className="my-4 rounded border border-dashed border-border p-4 text-sm text-muted-foreground">
              [TopFabricantsCards] À implémenter (Lot B)
            </div>
          )}

          {/* Rendu dynamique des blocs BO */}
          {contentBlocks.map((block) => (
            <BlockRenderer key={block.id} block={block} />
          ))}

          {/* Blocs de pied communs aux 3 types */}
          {page.author && <AuthorBlock author={page.author} />}
        </article>
      </main>

      <SiteFooter />
    </>
  );
}
