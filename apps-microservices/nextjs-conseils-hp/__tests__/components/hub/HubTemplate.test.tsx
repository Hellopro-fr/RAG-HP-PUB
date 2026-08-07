import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { HubTemplate } from '@/components/hub/HubTemplate';
import { listHubPages } from '@/data/hub';

// Convention du projet : next/image est mocké par fichier de test.
vi.mock('next/image', () => ({
  default: ({ src, alt, ...props }: { src: string; alt: string; [key: string]: unknown }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} {...props} />
  ),
}));

// Isolation des transverses lourds — testés par leurs propres suites.
vi.mock('@/components/conseil/SiteHeader', () => ({
  SiteHeader: () => <header data-testid="site-header" />,
}));
vi.mock('@/components/conseil/SiteFooter', () => ({
  SiteFooter: () => <footer data-testid="site-footer" />,
}));
// `ScrollToTopButton` est rendu par SiteFooter, pas par HubTemplate — on le mocke
// tout de même pour couper la dépendance si SiteFooter était démockré un jour.
vi.mock('@/components/conseil/ScrollToTopButton', () => ({
  ScrollToTopButton: () => <div data-testid="scroll-top" />,
}));
// Surcouches et sections interactives : testées séparément, isolées ici pour que
// ce test reste un test de COMPOSITION (ordre et présence des sections).
vi.mock('@/components/hub/AssistantForm', () => ({
  AssistantForm: () => <div data-testid="assistant-form" />,
  openAssistantDialog: () => {},
}));
vi.mock('@/components/hub/HubSectionNav', () => ({
  HubSectionNav: () => <nav data-testid="section-nav" />,
}));
// `GuideDownloadDialog` n'est plus monté directement (il passe par `HubOverlays`,
// mocké ci-dessous) et `triggers.tsx` importe l'opener depuis le module léger
// `guideDialogEvent`. Ce mock reste par PRÉCAUTION : si un import résiduel pointait
// encore vers le vrai module, il ne chargerait pas ses dépendances lourdes en jsdom.
vi.mock('@/components/hub/GuideDownloadDialog', () => ({
  GuideDownloadDialog: () => <div data-testid="guide-dialog" />,
  openGuideDialog: () => {},
}));
// Les surcouches guide + pop-up sont désormais montées PARESSEUSEMENT par
// `HubOverlays` (armées au clic/scroll, donc absentes d'un rendu de test statique).
// On le mocke par les deux marqueurs pour que ce test reste un test de COMPOSITION.
vi.mock('@/components/hub/HubOverlays', () => ({
  HubOverlays: () => (
    <>
      <div data-testid="guide-dialog" />
      <div data-testid="lead-popup" />
    </>
  ),
}));
vi.mock('@/components/hub/StickyCta', () => ({
  StickyCta: () => <div data-testid="sticky-cta" />,
}));

vi.mock('@/components/conseil/GtmFooterScripts', () => ({
  GtmFooterScripts: ({
    breadcrumb,
    pageTemplate,
  }: {
    breadcrumb: { label: string }[];
    pageTemplate?: string;
  }) => (
    <div
      data-testid="gtm"
      data-page-template={pageTemplate ?? 'conseils'}
      data-breadcrumb-length={breadcrumb.length}
    />
  ),
}));

const page = listHubPages()[0];

describe('HubTemplate', () => {
  it('monte les transverses HelloPro', () => {
    render(<HubTemplate page={page} />);
    expect(screen.getByTestId('site-header')).toBeDefined();
    expect(screen.getByTestId('site-footer')).toBeDefined();
    expect(screen.getByTestId('gtm')).toBeDefined();
  });

  /**
   * RÉGRESSION : `SiteFooter` rend déjà `ScrollToTopButton`. Le monter aussi ici
   * en créait un second, non `fixed`, donc une bande vide de 48 px sous le footer.
   */
  it('ne rend pas son propre bouton « remonter en haut »', () => {
    render(<HubTemplate page={page} />);
    expect(screen.queryByTestId('scroll-top')).toBeNull();
  });

  it('monte le questionnaire, le sommaire et les trois surcouches', () => {
    render(<HubTemplate page={page} />);
    expect(screen.getByTestId('assistant-form')).toBeDefined();
    expect(screen.getByTestId('section-nav')).toBeDefined();
    expect(screen.getByTestId('sticky-cta')).toBeDefined();
    expect(screen.getByTestId('guide-dialog')).toBeDefined();
    expect(screen.getByTestId('lead-popup')).toBeDefined();
  });

  /** Chaque surcouche est pilotée par événement window : une seule instance. */
  it('ne monte chaque surcouche qu’une seule fois', () => {
    render(<HubTemplate page={page} />);
    expect(screen.getAllByTestId('guide-dialog')).toHaveLength(1);
    expect(screen.getAllByTestId('lead-popup')).toHaveLength(1);
    expect(screen.getAllByTestId('assistant-form')).toHaveLength(1);
  });

  /**
   * Sans GtmFooterScripts, les pages HUB ne remontent AUCUN événement.
   * Et `pageTemplate="page_hub"` est ce qui permet de les isoler des pages
   * conseils dans les rapports GA4 : une régression ici mélangerait les deux
   * périmètres.
   *
   * ⚠️ La valeur exacte est un CONTRAT avec GA4 (filtres et segments déjà
   * construits dessus), pas un détail d'implémentation : la modifier sans
   * reprendre les rapports les met à zéro sans lever d'erreur. D'où l'assertion
   * sur la chaîne littérale et non sur une constante importée du composant, qui
   * suivrait le changement en silence.
   */
  it('déclare page_template = "page_hub" et transmet le fil d’ariane', () => {
    render(<HubTemplate page={page} />);
    const gtm = screen.getByTestId('gtm');
    expect(gtm.getAttribute('data-page-template')).toBe('page_hub');
    expect(gtm.getAttribute('data-breadcrumb-length')).toBe(String(page.breadcrumb.length));
  });

  it('rend un seul h1, reconstitué depuis titleParts', () => {
    render(<HubTemplate page={page} />);
    const headings = screen.getAllByRole('heading', { level: 1 });
    expect(headings).toHaveLength(1);
    expect(headings[0].textContent).toBe(page.hero.titleParts.map((p) => p.text).join(''));
  });

  /**
   * Prominence SEO : le h1 doit précéder tout widget dans le DOM source.
   * C'est la régression déjà constatée sur les pages conseils.
   */
  it('place le h1 avant le footer et les scripts GTM dans le DOM', () => {
    const { container } = render(<HubTemplate page={page} />);
    const html = container.innerHTML;
    expect(html.indexOf('<h1')).toBeGreaterThan(-1);
    expect(html.indexOf('<h1')).toBeLessThan(html.indexOf('data-testid="gtm"'));
    expect(html.indexOf('<h1')).toBeLessThan(html.indexOf('data-testid="site-footer"'));
  });

  it('affiche le badge et le sous-titre du hero', () => {
    render(<HubTemplate page={page} />);
    expect(screen.getByText(page.hero.badge)).toBeDefined();
    expect(screen.getByText(page.hero.subtitle)).toBeDefined();
  });

  it('rend le h1 dans un <main>', () => {
    const { container } = render(<HubTemplate page={page} />);
    expect(container.querySelector('main h1')).not.toBeNull();
  });

  it('rend tous les blocs thématiques et tous les editos', () => {
    const { container } = render(<HubTemplate page={page} />);
    for (const thematique of page.thematiques) {
      expect(container.querySelector(`section#${thematique.id}`), thematique.id).not.toBeNull();
    }
    for (const edito of page.editos) {
      expect(container.querySelector(`section#${edito.id}`), edito.id).not.toBeNull();
    }
  });

  /**
   * Le prototype intercale la bannière d'accompagnement au milieu des blocs
   * thématiques et « Comment ça marche » au milieu des editos. Regrouper les
   * sections par type change l'ordre de lecture de la page — régression déjà
   * commise une fois.
   */
  it('insère la bannière d’accompagnement à la position déclarée', () => {
    const { container } = render(<HubTemplate page={page} />);
    const html = container.innerHTML;
    const afterId = page.accompagnementBanner.afterThematiqueId;
    const nextThematique = page.thematiques[
      page.thematiques.findIndex((t) => t.id === afterId) + 1
    ];

    const bannerPos = html.indexOf(page.accompagnementBanner.title);
    expect(bannerPos).toBeGreaterThan(html.indexOf(`id="${afterId}"`));
    if (nextThematique) {
      expect(bannerPos).toBeLessThan(html.indexOf(`id="${nextThematique.id}"`));
    }
  });

  it('insère « Comment ça marche » à la position déclarée', () => {
    const { container } = render(<HubTemplate page={page} />);
    const html = container.innerHTML;
    const afterId = page.howItWorks.afterEditoId;
    const nextEdito = page.editos[page.editos.findIndex((e) => e.id === afterId) + 1];

    const howItWorksPos = html.indexOf('id="comment-ca-marche"');
    expect(howItWorksPos).toBeGreaterThan(html.indexOf(`id="${afterId}"`));
    if (nextEdito) {
      expect(howItWorksPos).toBeLessThan(html.indexOf(`id="${nextEdito.id}"`));
    }
  });

  it('place la FAQ et le CTA final en fin de page', () => {
    const { container } = render(<HubTemplate page={page} />);
    const html = container.innerHTML;
    expect(html.indexOf('id="cta-final"')).toBeGreaterThan(html.indexOf('id="nos-ressources"'));
    expect(html.indexOf('id="faq"')).toBeGreaterThan(html.indexOf('id="cta-final"'));
  });
});
