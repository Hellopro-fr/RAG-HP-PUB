import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ValueProps } from '@/components/hub/ValueProps';
import { listHubPages } from '@/data/hub';
import { HUB_SECTION_IDS } from '@/lib/hub/anchors';

const data = listHubPages()[0].valueProps;

/** Le conteneur repliable d'une carte (celui qui porte la transition). */
function collapsibleOf(container: HTMLElement, index: number) {
  return container.querySelectorAll('article')[index].querySelector('div.overflow-hidden');
}

describe('ValueProps', () => {
  it('porte l’ancre du sommaire et rend titre, sous-titre et phrase de clôture', () => {
    const { container } = render(<ValueProps data={data} />);
    // Ancre lue depuis la constante et non écrite en dur : elle s'appelait
    // `intro-hub`, renommée quand les préfixes d'implémentation ont été bannis
    // des ancres publiques. Le test était resté sur l'ancien nom.
    expect(container.querySelector(`section#${HUB_SECTION_IDS.valueProps}`)).not.toBeNull();
    expect(screen.getByText(data.title)).toBeDefined();
    expect(screen.getByText(data.subtitle)).toBeDefined();
    expect(screen.getByText(data.closing)).toBeDefined();
  });

  it('rend une carte par item, avec son tag et son titre', () => {
    const { container } = render(<ValueProps data={data} />);
    expect(container.querySelectorAll('article')).toHaveLength(data.items.length);
    for (const item of data.items) {
      expect(screen.getByText(item.title)).toBeDefined();
      expect(screen.getByText(item.tag)).toBeDefined();
    }
  });

  /**
   * INVARIANT SEO — le plus important de ce composant. Les 4 descriptions sont du
   * contenu rédactionnel : elles doivent être dans le HTML initial, quel que soit
   * l'état de survol. Le repli est purement CSS.
   */
  it('rend les 4 descriptions dans le DOM sans aucune interaction', () => {
    render(<ValueProps data={data} />);
    for (const item of data.items) {
      expect(screen.getByText(item.desc)).toBeDefined();
    }
  });

  /**
   * RÉGRESSION : une première version faisait grossir la carte survolée
   * (`flex-grow: 1.6`), ce qui réorganisait toute la rangée au moindre passage de
   * souris. Sur Asana les cartes sont strictement de même largeur — seul le
   * contenu change. Aucune transition de largeur, de flex-grow ni de transform.
   */
  it('n’applique aucune transition de largeur, de flex-grow ou de transform', () => {
    const { container } = render(<ValueProps data={data} />);
    for (const card of container.querySelectorAll('article')) {
      expect(card.className, card.textContent ?? '').not.toMatch(/grow/);
      expect(card.className).not.toMatch(/basis-/);
      expect(card.className).not.toMatch(/scale-/);
      expect(card.className).not.toMatch(/translate-/);
      // Seules les couleurs sont animées sur la carte.
      expect(card.className).toContain('transition-colors');
    }
  });

  it('dispose les cartes en grille de largeurs égales', () => {
    const { container } = render(<ValueProps data={data} />);
    const grid = container.querySelector('article')?.parentElement;
    expect(grid?.className).toContain('grid');
    expect(grid?.className).toContain('lg:grid-cols-4');
  });

  /**
   * Le cœur du mécanisme : hauteur fixe + `overflow-hidden`. Sans ça, déplier la
   * description agrandirait la carte et décalerait tout ce qui suit sur la page.
   */
  it('fixe la hauteur des cartes et clippe le débordement', () => {
    const { container } = render(<ValueProps data={data} />);
    for (const card of container.querySelectorAll('article')) {
      expect(card.className).toContain('overflow-hidden');
      expect(card.className).toContain('min-h-[19rem]');
      expect(card.className).toContain('h-full');
    }
  });

  /**
   * La zone d'icône absorbe l'espace au repos et se comprime au dépliage : c'est
   * elle qui fait remonter l'icône et le titre au lieu d'agrandir la carte.
   */
  /**
   * L'icône est grande au repos pour occuper le vide entre le haut de la carte et
   * le titre (critique de l'équipe), et se réduit au survol pour libérer la place
   * de la description. La BOÎTE est animée, pas un `scale` : un `scale` laisserait
   * la boîte réserver 96px et l'icône serait clippée au dépliage.
   */
  it('réduit la boîte de l’icône au survol, sans recourir à scale', () => {
    const { container } = render(<ValueProps data={data} />);
    const iconBox = container.querySelector('div.flex-1 > span');
    expect(iconBox?.className).toContain('h-24');
    expect(iconBox?.className).toContain('lg:group-hover:h-16');
    expect(iconBox?.className).not.toMatch(/scale-/);
  });

  it('centre l’icône dans la zone tampon au repos', () => {
    const { container } = render(<ValueProps data={data} />);
    const buffer = container.querySelector('div.flex-1');
    // Alignée en haut, l'icône laissait un vide sous elle.
    expect(buffer?.className).toContain('items-center');
    expect(buffer?.className).not.toContain('items-start');
  });

  /** Le glissement par le bas est ce qui distingue l'effet Asana d'un simple dépliage. */
  it('fait monter la description en apparaissant', () => {
    const { container } = render(<ValueProps data={data} />);
    const collapsible = collapsibleOf(container, 1)?.className ?? '';
    expect(collapsible).toContain('lg:translate-y-3');
    expect(collapsible).toContain('lg:group-hover:translate-y-0');
    // Pas de décalage résiduel quand tout est déplié d'office.
    expect(collapsible).toContain('lg:motion-reduce:translate-y-0');
  });

  it('intercale une zone tampon flexible au-dessus du bloc de texte', () => {
    const { container } = render(<ValueProps data={data} />);
    const card = container.querySelector('article');
    const buffer = card?.querySelector('div.flex-1');
    expect(buffer).not.toBeNull();
    // Le bloc de texte, lui, ne doit pas se comprimer.
    expect(card?.querySelector('div.shrink-0')).not.toBeNull();
  });

  /**
   * RÉGRESSION : plus de rotation automatique. Elle détournait l'attention et
   * imposait un composant client. Le survol suffit, et le composant redevient un
   * Server Component — d'où l'absence de directive 'use client'.
   */
  it('révèle la description au survol via group-hover, sans état React', () => {
    const { container } = render(<ValueProps data={data} />);
    const collapsible = collapsibleOf(container, 1)?.className ?? '';
    expect(collapsible).toContain('lg:group-hover:max-h-40');
    expect(collapsible).toContain('lg:group-hover:opacity-100');
    // Le repli n'est appliqué qu'à partir de lg.
    expect(collapsible).toContain('lg:max-h-0');
    expect(collapsible).toContain('lg:opacity-0');
  });

  it('marque chaque carte comme groupe de survol', () => {
    const { container } = render(<ValueProps data={data} />);
    for (const card of container.querySelectorAll('article')) {
      expect(card.className).toContain('group');
    }
  });

  it('garde les descriptions dépliées sous le breakpoint lg (pas de survol au doigt)', () => {
    const { container } = render(<ValueProps data={data} />);
    const collapsible = collapsibleOf(container, 1)?.className ?? '';
    // Classes non préfixées = état mobile.
    expect(collapsible).toContain('max-h-40');
    expect(collapsible).toContain('opacity-100');
  });

  /**
   * Ces cartes n'ont aucun lien à focaliser (pas de CTA dans les données). Sans
   * souris et sans rotation, `motion-reduce` est le seul moyen d'atteindre les
   * descriptions : le repli doit y être annulé.
   */
  it('annule le repli sous prefers-reduced-motion', () => {
    const { container } = render(<ValueProps data={data} />);
    const collapsible = collapsibleOf(container, 1)?.className ?? '';
    expect(collapsible).toContain('lg:motion-reduce:max-h-40');
    expect(collapsible).toContain('lg:motion-reduce:opacity-100');
  });

  it('rend un état identique pour toutes les cartes (aucune active au repos)', () => {
    const { container } = render(<ValueProps data={data} />);
    const collapsibles = Array.from({ length: data.items.length }, (_, i) =>
      collapsibleOf(container, i)?.className
    );
    // Toutes les cartes partagent exactement les mêmes classes de repli : aucune
    // n'est mise en avant au chargement, contrairement à la version rotative.
    expect(new Set(collapsibles).size).toBe(1);
  });
});
