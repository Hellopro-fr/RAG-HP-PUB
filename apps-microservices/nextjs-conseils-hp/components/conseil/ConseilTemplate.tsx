import { SiteHeader } from './SiteHeader';
import { SiteFooter } from './SiteFooter';
import { Hero } from './Hero';
import { HeroQuoteForm } from './HeroQuoteForm';
import { Sidebar } from './Sidebar';
import { AuthorBlock } from './AuthorBlock';
import { Crossell } from './Crossell';
import { Suppliers } from './Suppliers';
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
  const resumeData = resumeBlock ? (resumeBlock.data as unknown as ResumeBlockData) : null;
  const resumeItems = resumeData?.items ?? [];
  // HTML brut du bloc type 15 — assaini côté serveur avant passage au client
  const resumeHtml = resumeData?.html ? sanitizeResumeHtml(resumeData.html) : undefined;

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
        resumeHtml={resumeHtml}
        breadcrumb={page.breadcrumb ?? [
          { label: 'Accueil', href: 'https://www.hellopro.fr' },
          { label: 'Conseils', href: '/' },
          { label: page.hero.title },
        ]}
        slot={page.pageType !== 'top' ? (
          <HeroQuoteForm
            question={page.formulaire_ao ?? null}
            infoRubrique={page.infoRubrique ?? null}
          />
        ) : undefined}
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
          <Suppliers />
          <Crossell />
          {page.author && <AuthorBlock author={page.author} />}
        </article>
      </main>

      <SiteFooter />
    </>
  );
}

/** Supprime les balises script et les handlers inline pour sécuriser le HTML du BO. */
function sanitizeResumeHtml(html: string): string {
  return html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/\s+on\w+="[^"]*"/gi, '')
    .replace(/\s+on\w+='[^']*'/gi, '');
}
