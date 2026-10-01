import { describe, it, expect, vi } from 'vitest';
import type { ReactNode } from 'react';
import { render, screen } from '@testing-library/react';
import { ConseilTemplate, extractResumeTitle } from '@/components/conseil/ConseilTemplate';
import { mockPagePrix } from '@/data/mocks/page-prix';
import type { AoFormQuestion } from '@/types/conseils';

// Isolation des composants lourds (header/footer/hero/sidebar non testés ici)
vi.mock('@/components/conseil/SiteHeader', () => ({ SiteHeader: () => <header data-testid="site-header" /> }));
vi.mock('@/components/conseil/SiteFooter', () => ({ SiteFooter: () => <footer data-testid="site-footer" /> }));
/**
 * ⚠️ Le mock doit rendre les DEUX slots.
 *
 * `Hero` a scindé sa prop `slot` en `slotMobile` / `slotDesktop` (deux copies du
 * formulaire devis, une par largeur d'écran). Un mock qui ne rendait que `data`
 * avalait donc silencieusement le `HeroQuoteForm` : les deux tests ci-dessous ne
 * démontraient plus rien, ils échouaient sur un `hero-quote-form` introuvable
 * alors que `ConseilTemplate` le passait correctement.
 */
vi.mock('@/components/conseil/Hero', () => ({
  Hero: ({
    data,
    slotMobile,
    slotDesktop,
  }: {
    data: { title: string };
    slotMobile?: ReactNode;
    slotDesktop?: ReactNode;
  }) => (
    <div data-testid="hero">
      {data.title}
      {slotMobile}
      {slotDesktop}
    </div>
  ),
}));
vi.mock('@/components/conseil/Sidebar', () => ({ Sidebar: () => <nav data-testid="sidebar" /> }));
vi.mock('@/components/conseil/BlockRenderer', () => ({ BlockRenderer: () => <div data-testid="block" /> }));
vi.mock('@/components/conseil/AuthorBlock', () => ({ AuthorBlock: () => <div data-testid="author" /> }));
vi.mock('@/components/conseil/Crossell', () => ({ Crossell: () => <div data-testid="crossell" /> }));
vi.mock('@/components/conseil/Suppliers', () => ({ Suppliers: () => <div data-testid="suppliers" /> }));
vi.mock('@/components/conseil/HeroQuoteForm', () => ({
  HeroQuoteForm: ({ question }: { question?: AoFormQuestion | null }) => (
    <div data-testid="hero-quote-form" data-question={question?.question ?? 'none'} />
  ),
}));

describe('ConseilTemplate', () => {
  it('renders main structural elements', () => {
    render(<ConseilTemplate page={mockPagePrix} />);
    expect(screen.getByTestId('site-header')).toBeDefined();
    expect(screen.getByTestId('site-footer')).toBeDefined();
    expect(screen.getByTestId('hero')).toBeDefined();
  });

  it('passes formulaire_ao to HeroQuoteForm', () => {
    const question: AoFormQuestion = {
      id: 1,
      question: 'Quel est votre projet ?',
      avecImage: false,
      typeSelection: 1,
      obligatoire: 0,
      choix: [{ id: 1, label: 'Option A' }],
    };
    const page = { ...mockPagePrix, formulaire_ao: question };
    render(<ConseilTemplate page={page} />);
    // Deux copies (mobile + desktop), et c'est justement ce qu'il faut vérifier :
    // elles doivent être alimentées à l'identique. En nourrir une seule ne se
    // verrait qu'à une largeur d'écran donnée.
    const forms = screen.getAllByTestId('hero-quote-form');
    expect(forms).toHaveLength(2);
    for (const form of forms) {
      expect(form.getAttribute('data-question')).toBe('Quel est votre projet ?');
    }
  });

  it('passes null formulaire_ao when absent', () => {
    const page = { ...mockPagePrix, formulaire_ao: undefined };
    render(<ConseilTemplate page={page} />);
    const forms = screen.getAllByTestId('hero-quote-form');
    expect(forms).toHaveLength(2);
    for (const form of forms) {
      expect(form.getAttribute('data-question')).toBe('none');
    }
  });

  /**
   * Déplacé depuis `ProduitsBlock.test.tsx` (2026-09-07) : la collecte GTM a été
   * remontée ici, parce que la numérotation des `position` doit être CONTINUE
   * d'un bloc produits à l'autre — un bloc isolé ne peut pas savoir combien de
   * produits l'ont précédé sur la page. C'est précisément ce que vérifie le
   * second test ci-dessous, et c'est ce qu'on perdait à tester bloc par bloc.
   */
  it('injecte le script prod_intern_gtm avec les données GTM', () => {
    const page = {
      ...mockPagePrix,
      blocks: [
        {
          id: 'p1',
          type: 'produits' as const,
          order: 1,
          data: {
            productIds: [],
            produits: [
              { id: '11454124', name: 'Produit A', image: '/img/a.jpg', priceHt: null, url: '/a',
                brand: 'Marque A', category: '1002121', variant: 'cert' },
            ],
          },
        },
      ],
    };
    const { container } = render(<ConseilTemplate page={page} />);
    const script = container.querySelector('script');
    // JSON compact (`JSON.stringify`) : pas d'espace après les deux-points.
    expect(script?.innerHTML).toContain('prod_intern_gtm[1]');
    expect(script?.innerHTML).toContain('"id":"11454124"');
    expect(script?.innerHTML).toContain('"category":"1002121"');
    expect(script?.innerHTML).toContain('"variant":"cert"');
    expect(script?.innerHTML).toContain('"list":"lien interne"');
    expect(script?.innerHTML).toContain('"position":1');
  });

  it('numérote les positions GTM en continu sur plusieurs blocs produits', () => {
    const produit = (id: string) => ({
      id, name: `Produit ${id}`, image: '', priceHt: null, url: `/${id}`,
      brand: '', category: '', variant: '',
    });
    const page = {
      ...mockPagePrix,
      blocks: [
        { id: 'p1', type: 'produits' as const, order: 1, data: { productIds: [], produits: [produit('a'), produit('b')] } },
        { id: 'p2', type: 'produits' as const, order: 2, data: { productIds: [], produits: [produit('c')] } },
      ],
    };
    const { container } = render(<ConseilTemplate page={page} />);
    const html = container.querySelector('script')?.innerHTML ?? '';
    // Le produit du SECOND bloc doit être en position 3, pas repartir à 1.
    expect(html).toContain('prod_intern_gtm[3]');
    expect(html).toContain('"id":"c","brand":"","category":"","variant":"","list":"lien interne","position":3');
  });
});

describe('extractResumeTitle', () => {
  it('extrait le titre depuis un <h2>', () => {
    const { title, bodyHtml } = extractResumeTitle('<h2>L\'essentiel à retenir</h2><ul><li>Point 1</li></ul>');
    expect(title).toBe("L'essentiel à retenir");
    expect(bodyHtml).toBe('<ul><li>Point 1</li></ul>');
  });

  it('extrait le titre depuis un <p> court', () => {
    const { title, bodyHtml } = extractResumeTitle('<p>L\'essentiel à retenir :</p><table><tr><td>contenu</td></tr></table>');
    expect(title).toBe("L'essentiel à retenir");
    expect(bodyHtml).toContain('<table>');
  });

  it('supprime le ":" de fin dans le titre extrait', () => {
    const { title } = extractResumeTitle('<p>Points clés :</p><ul><li>item</li></ul>');
    expect(title).toBe('Points clés');
  });

  it('extrait le titre depuis un <li> entièrement en <strong>', () => {
    const { title, bodyHtml } = extractResumeTitle('<ul><li><strong>L\'essentiel :</strong></li><li>Coût : 200€</li></ul>');
    expect(title).toBe("L'essentiel");
    expect(bodyHtml).toContain('Coût : 200€');
  });

  it('retourne undefined et le HTML intact quand pas de titre détectable', () => {
    const html = '<ul><li>Coût : 200€</li><li>Durée : 3 jours</li></ul>';
    const { title, bodyHtml } = extractResumeTitle(html);
    expect(title).toBeUndefined();
    expect(bodyHtml).toBe(html);
  });

  it('extrait le titre depuis un <li> se terminant par ":" avec icône', () => {
    const html = '<ul><li>🕯 L\'essentiel à retenir :</li><li>Coût : entre 200 et 500 €</li></ul>';
    const { title, bodyHtml } = extractResumeTitle(html);
    expect(title).toBe("L'essentiel à retenir");
    expect(bodyHtml).toContain('Coût');
    expect(bodyHtml).not.toContain('essentiel');
  });

  it('ignore un <p> long (> 120 chars) — contenu, pas un titre', () => {
    const long = '<p>' + 'a'.repeat(121) + '</p><ul><li>item</li></ul>';
    const { title } = extractResumeTitle(long);
    expect(title).toBeUndefined();
  });

  it('extrait un titre sans emoji mais avec ":" final dans un <li>', () => {
    const html = '<ul><li>Ce qu\'il faut retenir:</li><li>Point A</li><li>Point B</li></ul>';
    const { title, bodyHtml } = extractResumeTitle(html);
    expect(title).toBe("Ce qu'il faut retenir");
    expect(bodyHtml).toContain('Point A');
    expect(bodyHtml).not.toContain('faut retenir');
  });

  it('extrait un titre avec emoji mais SANS ":" final (cas fréquent de l\'API)', () => {
    const html = '<ul><li>💡 L\'essentiel à retenir</li><li>Coût : 200€</li><li>Durée : 3 j</li></ul>';
    const { title, bodyHtml } = extractResumeTitle(html);
    expect(title).toBe("L'essentiel à retenir");
    expect(bodyHtml).toContain('Coût');
    expect(bodyHtml).not.toContain('essentiel');
  });

  it('ne détecte pas un <li> avec emoji comme titre quand il est seul (pas de frères)', () => {
    const html = '<ul><li>💡 Un seul élément</li></ul>';
    const { title } = extractResumeTitle(html);
    expect(title).toBeUndefined();
  });

  it('extrait un titre avec espace avant ":" (ex: "Ce qu\'il faut retenir :")', () => {
    const html = '<ul><li>Ce qu\'il faut retenir :</li><li>Point A</li></ul>';
    const { title } = extractResumeTitle(html);
    expect(title).toBe("Ce qu'il faut retenir");
  });
});
