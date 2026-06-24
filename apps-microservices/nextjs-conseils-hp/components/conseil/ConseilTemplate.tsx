import { Home } from 'lucide-react';
import { SiteHeader } from './SiteHeader';
import { SiteFooter } from './SiteFooter';
import { GtmFooterScripts } from './GtmFooterScripts';
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
import { StickyCtaBar } from './StickyCtaBar';
import type { ResumeBlockData } from '@/types/blocks/resume';
import type { ProduitsBlockData } from '@/types/blocks/produits';

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

  const breadcrumb = page.breadcrumb ?? [
    { label: 'Accueil', href: 'https://conseils.hellopro.fr/' },
    { label: 'Conseils', href: '/' },
    { label: page.hero.title },
  ];

  // Steps 5 & 6 — collecte globale des produits pour GTM (positions continues sur tous les blocs)
  const gtmEntries: string[] = [];
  let gtmPos = 0;
  for (const block of page.blocks) {
    if (block.type === 'produits') {
      const data = block.data as unknown as ProduitsBlockData;
      for (const p of (data.produits ?? []).slice(0, 6)) {
        gtmPos++;
        gtmEntries.push(
          `prod_intern_gtm[${gtmPos}]={"name":"","id":${JSON.stringify(p.id)},"brand":${JSON.stringify(p.brand ?? '')},"category":${JSON.stringify(p.category ?? '')},"variant":${JSON.stringify(p.variant ?? '')},"list":"lien interne","position":${gtmPos}};`
        );
      }
    }
  }
  const gtmProductsScript = `var prod_intern_gtm={};\n${gtmEntries.join('\n')}`;

  // Extraire le bloc resume pour l'afficher dans le Hero
  const resumeBlock = page.blocks.find((b) => b.type === 'resume');
  const resumeData = resumeBlock ? (resumeBlock.data as unknown as ResumeBlockData) : null;
  const resumeItems = resumeData?.items ?? [];
  // HTML brut du bloc type 15 — affiché tel quel en un seul bloc (titre compris)
  const resumeHtml = resumeData?.html ? sanitizeResumeHtml(resumeData.html) : undefined;
  // Titre renvoyé par l'API, emoji de tête retiré — undefined si absent (pas de fallback)
  const resumeTitle = resumeData?.title
    ?.replace(/^[\p{Emoji_Presentation}\p{Extended_Pictographic}\s]+/u, '')
    .trim() || undefined;

  // Blocs à rendre (exclure le resume qui est intégré dans le Hero)
  const contentBlocks = page.blocks
    .filter((b) => b.type !== 'resume')
    .sort((a, b) => a.order - b.order);

  // Ancre vers le premier bloc texte — cible du lien "Lire la suite" dans le Hero
  const FIRST_BLOCK_ANCHOR = 'premier-bloc-texte';
  const firstTextBlockId = contentBlocks.find((b) => b.type === 'texte')?.id ?? null;

  const hasBrochure = contentBlocks.some((b) => b.type === 'brochure');
  const faqIndex = contentBlocks.findIndex((b) => b.type === 'faq');

  // Le H2 immédiatement avant le FAQ devient le titre de la section FAQ.
  // Il est retiré du rendu normal pour éviter la duplication.
  const h2BeforeFaq =
    faqIndex > 0 && contentBlocks[faqIndex - 1]?.type === 'h2'
      ? (contentBlocks[faqIndex - 1].data as { title: string }).title
      : undefined;

  // Id du H2 repris pour la section FAQ → cohérence avec le sommaire (ancre + scroll-spy).
  // Le sommaire (extractTOC) indexe ce H2 par son id ; la section FAQ doit donc porter cet id,
  // sinon getElementById échoue et la progression du sommaire est faussée.
  const h2BeforeFaqId =
    faqIndex > 0 && contentBlocks[faqIndex - 1]?.type === 'h2'
      ? (contentBlocks[faqIndex - 1].data as { id?: string }).id
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

  // Mid-point insertion: place just before the first h2 at or after the mid-point.
  // If no h2 exists after mid-point, fall back to skipping heading-preceded / image-starting positions.
  const IMAGE_TYPES = ['image', 'texte-image', 'image-texte', 'image-image'];
  let quoteFormAt = Math.floor(blocksBeforeBrochure.length / 2);
  const nextH2FromMid = blocksBeforeBrochure.findIndex((b, i) => i >= quoteFormAt && b.type === 'h2');
  if (nextH2FromMid !== -1) {
    quoteFormAt = nextH2FromMid;
  } else {
    while (
      quoteFormAt < blocksBeforeBrochure.length &&
      (
        ['h2', 'h3'].includes(blocksBeforeBrochure[quoteFormAt - 1]?.type ?? '') ||
        IMAGE_TYPES.includes(blocksBeforeBrochure[quoteFormAt]?.type ?? '')
      )
    ) {
      quoteFormAt++;
    }
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
        author={page.author}
        publishedAt={page.updatedAt}
        readTime={page.tempsLecture !== undefined ? `${page.tempsLecture} min de lecture` : undefined}
        resume={resumeItems}
        resumeTitle={resumeTitle}
        resumeHtml={resumeHtml}
        breadcrumb={breadcrumb}
        slotMobile={page.pageType !== 'top' ? (
          <HeroQuoteForm
            question={page.formulaire_ao ?? null}
            infoRubrique={page.infoRubrique ?? null}
            labelAs="h2"
          />
        ) : undefined}
        slotDesktop={page.pageType !== 'top' ? (
          <HeroQuoteForm
            question={page.formulaire_ao ?? null}
            infoRubrique={page.infoRubrique ?? null}
            labelAs="p"
          />
        ) : undefined}
      />

      <main className="mx-auto max-w-[1400px] grid lg:grid-cols-[280px_1fr] gap-10 px-4 py-10 lg:px-6">
        <Sidebar items={tocItems} />

        <article className="min-w-0">
          {/* Step 5 & 6 — initialisation prod_intern_gtm + entrées produits (positions globales) */}
          <script dangerouslySetInnerHTML={{ __html: gtmProductsScript }} />
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
          {blocksBeforeQuoteForm.map((block) =>
            block.id === firstTextBlockId ? (
              <div key={block.id} id={FIRST_BLOCK_ANCHOR} className="scroll-mt-28">
                <BlockRenderer block={block} formulaire_ao={page.formulaire_ao} infoRubrique={page.infoRubrique} />
              </div>
            ) : (
              <BlockRenderer key={block.id} block={block} formulaire_ao={page.formulaire_ao} infoRubrique={page.infoRubrique} />
            )
          )}

          {/* Formulaire devis injecté au milieu du contenu */}
          {showQuoteForm && (
            <QuoteFormBlock
              data={{}}
              formulaire_ao={page.formulaire_ao ?? null}
              infoRubrique={page.infoRubrique ?? null}
            />
          )}

          {/* Seconde moitié des blocs */}
          {blocksAfterQuoteForm.map((block) =>
            block.id === firstTextBlockId ? (
              <div key={block.id} id={FIRST_BLOCK_ANCHOR} className="scroll-mt-28">
                <BlockRenderer block={block} formulaire_ao={page.formulaire_ao} infoRubrique={page.infoRubrique} />
              </div>
            ) : (
              <BlockRenderer key={block.id} block={block} formulaire_ao={page.formulaire_ao} infoRubrique={page.infoRubrique} />
            )
          )}

          {/* Brochure statique — temporairement désactivée (à réactiver)
          {!hasBrochure && <BrochureBlock data={STATIC_BROCHURE} />}
          */}

          {/* FAQ (avec titre du H2 précédent) + blocs suivants */}
          {blocksFromFaq.map((block) =>
            block.type === 'faq' && h2BeforeFaq ? (
              <FaqBlock
                key={block.id}
                data={{ ...(block.data as unknown as FaqBlockData), title: h2BeforeFaq }}
                sectionId={h2BeforeFaqId}
              />
            ) : block.id === firstTextBlockId ? (
              <div key={block.id} id={FIRST_BLOCK_ANCHOR} className="scroll-mt-28">
                <BlockRenderer block={block} formulaire_ao={page.formulaire_ao} infoRubrique={page.infoRubrique} />
              </div>
            ) : (
              <BlockRenderer key={block.id} block={block} formulaire_ao={page.formulaire_ao} infoRubrique={page.infoRubrique} />
            )
          )}

          {/* Blocs de pied communs aux 3 types */}
          {!!page.suppliers?.length && (
            <Suppliers
              suppliers={page.suppliers}
              infoRubriqueId={page.infoRubrique?.id}
              categoryLabel={page.infoRubrique?.libelle}
            />
          )}
          <Crossell liensIntexts={page.liensIntexts} conseilsAssocies={page.conseilsAssocies} />
          {page.author && <AuthorBlock author={page.author} />}
        </article>
      </main>

      {/* Steps 6-10 — scripts GTM footer (page_template → user+cats → GTM → GA4 → impressions) */}
      <GtmFooterScripts breadcrumb={breadcrumb} />

      {/* Fil d'ariane mobile — masqué sur desktop (le Hero l'affiche en md+) */}
      {breadcrumb.length > 0 && (
        <nav
          aria-label="Fil d'Ariane"
          className="min-[769px]:hidden flex flex-wrap items-center gap-1 border-t border-border bg-background px-4 py-3 text-xs text-muted-foreground"
        >
          {breadcrumb.map((item, i) => (
            <span key={i} className="flex items-center gap-1">
              {i > 0 && <span aria-hidden="true">›</span>}
              {item.href ? (
                <a
                  href={item.href}
                  className="hover:underline hover:text-foreground"
                  aria-label={i === 0 ? item.label : undefined}
                >
                  {i === 0 ? <Home className="h-3.5 w-3.5" /> : item.label}
                </a>
              ) : (
                <span className="text-foreground">
                  {i === 0 ? <Home className="h-3.5 w-3.5" /> : item.label}
                </span>
              )}
            </span>
          ))}
        </nav>
      )}

      <SiteFooter />

      {page.ctaSticky && <StickyCtaBar ctaSticky={page.ctaSticky} />}
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
