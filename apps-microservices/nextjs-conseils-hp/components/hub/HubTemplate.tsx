import { SiteHeader } from '@/components/conseil/SiteHeader';
import { SiteFooter } from '@/components/conseil/SiteFooter';
import { GtmFooterScripts } from '@/components/conseil/GtmFooterScripts';
import { FaqBlock } from '@/components/conseil/blocks/FaqBlock';
import { HUB_SECTION_IDS } from '@/lib/hub/anchors';
import type { HeaderCategory } from '@/data/site/header-categories';
import { guideIdPageHub } from '@/data/hub';
import { HubHero } from './HubHero';
import { HubTrackingContext } from './HubTrackingContext';
import { HubArticleClickTracker } from './HubArticleClickTracker';
import { AssistantForm } from './AssistantForm';
import { HubSectionNav } from './HubSectionNav';
import { HubOverlays } from './HubOverlays';
import { StickyCta } from './StickyCta';
import { ValueProps } from './ValueProps';
import { ThematiqueBloc } from './ThematiqueBloc';
import { AccompagnementBanner, GuideCta } from './Banners';
import { RessourcesGrid } from './RessourcesGrid';
import { GrandesEtapes } from './GrandesEtapes';
import { EditoSection } from './EditoSection';
import { HowItWorks } from './HowItWorks';
import { AccompagnementSplit } from './AccompagnementSplit';
import { FinalCta } from './FinalCta';
import { hubCanonicalPath, type HubPage } from '@/types/hub';

interface HubTemplateProps {
  page: HubPage;
  /**
   * Rubriques du méga-menu, récupérées par la route (`fetchHeaderCategories`).
   * Passées en prop plutôt que lues ici : le template reste synchrone, donc
   * testable avec React Testing Library sans mocker le réseau.
   */
  headerCategories?: HeaderCategory[];
}

/**
 * Orchestrateur des pages HUB « projet ».
 *
 * Server Component : aucune section de contenu n'a besoin de JavaScript. Seuls
 * `FaqBlock` (accordéon) et les transverses interactifs sont marqués
 * 'use client' individuellement. C'est ce qui garde le payload RSC léger et le
 * contenu intégralement présent dans le HTML initial.
 *
 * Transverses HelloPro réutilisés tels quels — on ne reprend NI le header NI le
 * footer du prototype Lovable (liens factices, méga-menu catégories absent) :
 *  - SiteHeader        : logo, recherche, méga-menu catégories rendu en SSR
 *  - SiteFooter        : footer global — rend AUSSI `ScrollToTopButton`
 *  - GtmFooterScripts  : page_template + user + category1..5 + GTM + GA4.
 *                        OBLIGATOIRE — sans lui, aucun tracking sur la page.
 * CookieConsent / PageViewTracker / GtmUserEnricher sont déjà montés par le
 * root layout : ne pas les dupliquer ici.
 *
 * L'ORDRE des sections reproduit celui du prototype (`ProjectHub`), y compris
 * ses deux entrelacements : la bannière d'accompagnement s'insère au milieu des
 * blocs thématiques, et « Comment ça marche » au milieu des editos.
 *
 * Ces deux points d'insertion sont pilotés par les DONNÉES
 * (`accompagnementBanner.afterThematiqueId`, `howItWorks.afterEditoId`) et non
 * par des index codés en dur : une page avec un nombre de blocs différent
 * continue de fonctionner, et l'ordre reste lisible dans le fichier de contenu.
 * Un id inconnu → la section est rendue en fin de liste plutôt que perdue.
 *
 * Frontières client (tout le reste est rendu côté serveur) :
 *  - `AssistantForm`       questionnaire du hero + son dialog
 *  - `HubSectionNav`       suivi de la section active (IntersectionObserver)
 *  - `ValueProps`          rotation décorative des cartes
 *  - `FaqBlock`            accordéon
 *  - `GuideDownloadDialog` / `LeadPopup` / `StickyCta` — surcouches
 *  - `GuideButton` / `AssistantButton` (dans `triggers.tsx`) — les sections
 *    restent serveur, seul le bouton est hydraté.
 *
 * ⚠️ POC : les trois formulaires n'envoient RIEN. Cf. CLAUDE.md §11bis.4.
 */
export function HubTemplate({ page, headerCategories = [] }: HubTemplateProps) {
  const { afterThematiqueId } = page.accompagnementBanner;
  const { afterEditoId } = page.howItWorks;

  // Un id d'ancrage inconnu (ou absent) place la section en fin de liste plutôt
  // que de la faire disparaître silencieusement.
  const bannerAfter = page.thematiques.some((t) => t.id === afterThematiqueId)
    ? afterThematiqueId
    : page.thematiques[page.thematiques.length - 1]?.id;
  const howItWorksAfter = page.editos.some((e) => e.id === afterEditoId)
    ? afterEditoId
    : page.editos[page.editos.length - 1]?.id;

  return (
    // Pas de padding bas ici : c'est `StickyCta` qui rend son propre réservataire
    // d'espace, masqué avec la même condition que la barre (voir son commentaire).
    <div className="min-h-screen bg-background">
      {/* Rubriques récupérées en direct depuis mega-menu.php par la route — même
          source que www.hellopro.fr, donc pas de dérive. */}
      <SiteHeader categories={headerCategories} />

      <main>
        {/* ⚠️ EN TÊTE de <main>, avant tout composant client émetteur : c'est un
            <script> serveur, exécuté au parsing, donc `hub_page_id` est dans le
            dataLayer avant qu'un événement puisse partir. Le déplacer plus bas
            n'aurait pas d'effet visible mais rendrait l'ordre dépendant de
            l'hydratation — un manque de dimension intermittent. */}
        {/* `hubCanonicalPath` et non `page.slug` : c'est l'URI PUBLIQUE
            (`/<slug>-<id>-projet.html`), la seule qui recoupe `page_location`, la
            Search Console et les logs. La route interne `/hub/<slug>-<id>` servie
            par le rewrite ne veut rien dire pour un lecteur de rapport. */}
        <HubTrackingContext pageId={page.id} uri={hubCanonicalPath(page)} />
        <HubArticleClickTracker />

        <HubHero data={page.hero} formSlot={<AssistantForm data={page.assistant} idPageHub={page.id} />} />
        <HubSectionNav items={page.nav} />
        <ValueProps data={page.valueProps} />

        {page.thematiques.map((thematique, index) => (
          <div key={thematique.id}>
            <ThematiqueBloc
              data={thematique}
              // Fond alterné : sépare visuellement deux blocs consécutifs.
              alternate={index % 2 === 1}
            />
            {thematique.id === bannerAfter && (
              <AccompagnementBanner data={page.accompagnementBanner} />
            )}
          </div>
        ))}

        <GuideCta data={page.guideCta} />
        <RessourcesGrid data={page.ressources} />
        <GrandesEtapes data={page.grandesEtapes} />

        {page.editos.map((edito) => (
          <div key={edito.id}>
            <EditoSection data={edito} />
            {edito.id === howItWorksAfter && <HowItWorks data={page.howItWorks} />}
          </div>
        ))}

        <AccompagnementSplit data={page.accompagnement} />
        <FinalCta data={page.finalCta} />

        <div className="mx-auto max-w-3xl px-4">
          <FaqBlock
            data={{ items: page.faq.items, title: page.faq.title }}
            sectionId={HUB_SECTION_IDS.faq}
          />
        </div>
      </main>

      {/* `page_hub` isole les pages projet des pages conseils dans GA4.
          ⚠️ Valeur arbitrée le 2026-08-05 : elle sert de filtre dans les rapports
          GA4 et les segments déjà construits. La changer casse ces rapports
          silencieusement — aucune erreur, juste des chiffres à zéro. */}
      <GtmFooterScripts breadcrumb={page.breadcrumb} pageTemplate="page_hub" />

      {/* ⚠️ NE PAS ajouter <ScrollToTopButton /> ici : SiteFooter le rend déjà,
          positionné dans sa propre grille. Le bouton n'est pas `fixed` — le
          monter en frère du footer ajoutait une bande vide de 48 px en fin de page. */}
      <SiteFooter />

      {/* Surcouches : montées une seule fois, pilotées par événement window.
          `HubOverlays` charge les dialogs guide + pop-up PARESSEUSEMENT (armés au
          1er clic guide / 1er scroll) → hors du bundle initial, sans fenêtre morte. */}
      <StickyCta label={page.stickyCtaLabel} />
      <HubOverlays
        guide={page.guideDialog}
        leadPopup={page.leadPopup}
        guideIdPageHub={guideIdPageHub(page.id)}
        pageId={page.id}
      />
    </div>
  );
}
