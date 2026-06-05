import { SiteHeader } from './SiteHeader';
import { SiteFooter } from './SiteFooter';
import { Hero } from './Hero';
import { HeroQuoteForm } from './HeroQuoteForm';
import { Sidebar } from './Sidebar';
import { AuthorBlock } from './AuthorBlock';
import { Crossell } from './Crossell';
import { Suppliers } from './Suppliers';
import { BlockRenderer } from './BlockRenderer';
import { BrochureBlock } from './blocks/BrochureBlock';
import { FaqBlock } from './blocks/FaqBlock';
import { QuoteFormBlock } from './blocks/QuoteFormBlock';
import type { FaqBlockData } from '@/types/blocks/faq';
import { extractTOC } from '@/lib/blocks/extractTOC';
import type { ConseilPage } from '@/types/conseils';
import type { ResumeBlockData } from '@/types/blocks/resume';

const STATIC_BROCHURE = {
  title: "Le guide complet pour bien choisir votre bâtiment d'élevage",
  description: "Toutes les clés pour cadrer votre projet, comparer les solutions et négocier les meilleurs devis — rédigé par nos experts achats pros.",
  bullets: [
    'Méthode pour estimer votre budget au juste prix',
    'Comparatifs matériaux, équipements & constructeurs',
    'Aides, financement et démarches administratives',
    'Check-lists prêtes à l\'emploi avant signature',
  ],
  ctaLabel: 'Recevoir le guide gratuit',
};

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
  // HTML brut du bloc type 15 — assaini côté serveur, titre extrait du premier élément
  const { title: extractedTitle, bodyHtml: resumeHtml } = resumeData?.html
    ? extractResumeTitle(sanitizeResumeHtml(resumeData.html))
    : { title: undefined, bodyHtml: undefined };
  // data.title (items mode) prime sur le titre extrait du HTML
  const resumeTitle = resumeData?.title ?? extractedTitle;

  // Blocs à rendre (exclure le resume qui est intégré dans le Hero)
  const contentBlocks = page.blocks
    .filter((b) => b.type !== 'resume')
    .sort((a, b) => a.order - b.order);

  const hasBrochure = contentBlocks.some((b) => b.type === 'brochure');
  const faqIndex = contentBlocks.findIndex((b) => b.type === 'faq');

  // Le H2 immédiatement avant le FAQ devient le titre de la section FAQ.
  // Il est retiré du rendu normal pour éviter la duplication.
  const h2BeforeFaq =
    faqIndex > 0 && contentBlocks[faqIndex - 1]?.type === 'h2'
      ? (contentBlocks[faqIndex - 1].data as { title: string }).title
      : undefined;

  const renderBlocks = h2BeforeFaq
    ? contentBlocks.filter((_, i) => i !== faqIndex - 1)
    : contentBlocks;

  // Index du FAQ dans renderBlocks (décalé de -1 si le H2 a été retiré)
  const renderFaqIndex = faqIndex !== -1 ? (h2BeforeFaq ? faqIndex - 1 : faqIndex) : -1;

  // Point de coupure pour la brochure statique :
  //   - avant le FAQ s'il existe
  //   - en fin de liste sinon (brochure affichée après tous les blocs)
  const brochureSplitAt = !hasBrochure
    ? (renderFaqIndex !== -1 ? renderFaqIndex : renderBlocks.length)
    : renderBlocks.length;

  const blocksBeforeBrochure = renderBlocks.slice(0, brochureSplitAt);
  const blocksFromFaq = renderBlocks.slice(brochureSplitAt);

  const hasQuoteForm = contentBlocks.some((b) => b.type === 'quote-form');
  const showQuoteForm = !hasQuoteForm && !!page.formulaire_ao && page.pageType !== 'top';

  // Mid-point insertion: advance past any title block so we never cut after an H2/H3
  let quoteFormAt = Math.floor(blocksBeforeBrochure.length / 2);
  while (
    quoteFormAt < blocksBeforeBrochure.length &&
    ['h2', 'h3'].includes(blocksBeforeBrochure[quoteFormAt - 1]?.type ?? '')
  ) {
    quoteFormAt++;
  }
  const blocksBeforeQuoteForm = showQuoteForm
    ? blocksBeforeBrochure.slice(0, quoteFormAt)
    : blocksBeforeBrochure;
  const blocksAfterQuoteForm = showQuoteForm
    ? blocksBeforeBrochure.slice(quoteFormAt)
    : [];

  return (
    <>
      <SiteHeader categories={page.headerCategories ?? []} />

      <Hero
        data={page.hero}
        pageType={page.pageType}
        resume={resumeItems}
        resumeTitle={resumeTitle}
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

          {/* Première moitié des blocs */}
          {blocksBeforeQuoteForm.map((block) => (
            <BlockRenderer key={block.id} block={block} formulaire_ao={page.formulaire_ao} infoRubrique={page.infoRubrique} />
          ))}

          {/* Formulaire devis injecté au milieu du contenu */}
          {showQuoteForm && (
            <QuoteFormBlock
              data={{}}
              formulaire_ao={page.formulaire_ao ?? null}
              infoRubrique={page.infoRubrique ?? null}
            />
          )}

          {/* Seconde moitié des blocs */}
          {blocksAfterQuoteForm.map((block) => (
            <BlockRenderer key={block.id} block={block} formulaire_ao={page.formulaire_ao} infoRubrique={page.infoRubrique} />
          ))}

          {/* Brochure statique — avant le FAQ s'il existe, sinon après tous les blocs */}
          {!hasBrochure && <BrochureBlock data={STATIC_BROCHURE} />}

          {/* FAQ (avec titre du H2 précédent) + blocs suivants */}
          {blocksFromFaq.map((block) =>
            block.type === 'faq' && h2BeforeFaq ? (
              <FaqBlock
                key={block.id}
                data={{ ...(block.data as unknown as FaqBlockData), title: h2BeforeFaq }}
              />
            ) : (
              <BlockRenderer key={block.id} block={block} formulaire_ao={page.formulaire_ao} infoRubrique={page.infoRubrique} />
            )
          )}

          {/* Blocs de pied communs aux 3 types */}
          <Suppliers />
          <Crossell liensIntexts={page.liensIntexts} conseilsAssocies={page.conseilsAssocies} />
          {page.author && <AuthorBlock author={page.author} />}
        </article>
      </main>

      <SiteFooter />
    </>
  );
}

/** Supprime les icônes/emojis en début et le ":" en fin d'un titre extrait du HTML. */
function cleanTitle(raw: string): string {
  return raw
    .replace(/<[^>]+>/g, '')          // supprimer les balises HTML
    .replace(/^[^a-zA-ZÀ-ÿ]+/, '')   // supprimer icônes/emojis/symboles en début
    .replace(/\s*:\s*$/, '')          // supprimer ":" en fin
    .trim();
}

/** Supprime les balises script et les handlers inline pour sécuriser le HTML du BO. */
function sanitizeResumeHtml(html: string): string {
  return html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/\s+on\w+="[^"]*"/gi, '')
    .replace(/\s+on\w+='[^']*'/gi, '');
}

/**
 * Extrait le titre du bloc type 15 depuis le premier élément textuel du HTML.
 * Supporte h1-h6, <p>, <div> courts, ou un premier <li> dont le contenu est
 * entièrement en gras (pattern "titre : …" ou "titre" seul).
 * Le titre est retiré du corps pour éviter la duplication dans le rendu.
 */
export function extractResumeTitle(html: string): { title: string | undefined; bodyHtml: string } {
  const trimmed = html.trim();

  // 1. Titres h1-h6
  const hMatch = trimmed.match(/^<h[1-6][^>]*>([\s\S]*?)<\/h[1-6]>/i);
  if (hMatch) {
    const title = cleanTitle(hMatch[1]);
    return { title: title || undefined, bodyHtml: trimmed.slice(hMatch[0].length).trim() };
  }

  // 2. Premier <p> court (moins de 120 caractères de texte — clairement un titre)
  const pMatch = trimmed.match(/^<p[^>]*>([\s\S]*?)<\/p>/i);
  if (pMatch) {
    const title = cleanTitle(pMatch[1]);
    if (title && title.length < 120) {
      return { title, bodyHtml: trimmed.slice(pMatch[0].length).trim() };
    }
  }

  // 3. Premier <li> dont TOUT le contenu est en <strong> (li utilisé comme titre)
  const liStrongMatch = trimmed.match(/^<ul[^>]*>\s*<li[^>]*>\s*<strong[^>]*>([\s\S]*?)<\/strong>\s*<\/li>([\s\S]*)$/i);
  if (liStrongMatch) {
    const title = cleanTitle(liStrongMatch[1]);
    if (title) {
      const rest = liStrongMatch[2].trimStart();
      const bodyHtml = rest.startsWith('</ul>') ? rest.slice(5).trim() : `<ul>${rest}`;
      return { title, bodyHtml };
    }
  }

  // 4. Premier <li> détecté comme titre :
  //    — se termine par ":" (avec ou sans espace avant, ex: "Ce qu'il faut retenir:")
  //    — OU commence par un emoji/symbole (caractère non lettre, ex: "💡 L'essentiel à retenir")
  //      avec au moins un autre <li> après lui (sinon c'est du contenu)
  const firstLiMatch = trimmed.match(/^<ul[^>]*>\s*<li[^>]*>([\s\S]{1,200}?)<\/li>([\s\S]*)$/i);
  if (firstLiMatch) {
    const rawText = firstLiMatch[1].replace(/<[^>]+>/g, '').trim();
    const rest = firstLiMatch[2];
    const endsWithColon = /\s*:\s*$/.test(rawText);
    const startsWithNonLetter = rawText.length > 0 && !/^[a-zA-ZÀ-ÿ"'«0-9]/.test(rawText);
    const hasMoreItems = /<li/i.test(rest);
    if (
      rawText.length > 0 &&
      rawText.length < 100 &&
      (endsWithColon || (startsWithNonLetter && hasMoreItems))
    ) {
      const title = cleanTitle(firstLiMatch[1]);
      if (title) {
        const restTrimmed = rest.trimStart();
        const bodyHtml = restTrimmed.startsWith('</ul>') ? restTrimmed.slice(5).trim() : `<ul>${restTrimmed}`;
        return { title, bodyHtml };
      }
    }
  }

  return { title: undefined, bodyHtml: trimmed };
}
