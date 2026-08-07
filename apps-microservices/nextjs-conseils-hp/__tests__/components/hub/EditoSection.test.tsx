import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EditoSection } from '@/components/hub/EditoSection';

describe('EditoSection', () => {
  it('porte son id comme ancre et rend le titre en h3', () => {
    const { container } = render(
      <EditoSection data={{ id: 'edito-budget', title: 'Quel budget prévoir ?' }} />
    );
    expect(container.querySelector('section#edito-budget')).not.toBeNull();
    // ⚠️ NIVEAU 3, pas 2 : les blocs éditoriaux développent les sections de
    // niveau 2 au lieu d'en constituer une de même rang (structure de référence
    // du 2026-08-07). Assertion sur le niveau et non sur l'apparence — la taille
    // reste celle d'un titre de section.
    expect(screen.getByRole('heading', { level: 3 }).textContent).toBe('Quel budget prévoir ?');
    expect(screen.queryByRole('heading', { level: 2 })).toBeNull();
  });

  it('rend intro, items et note ensemble', () => {
    render(
      <EditoSection
        data={{
          id: 'e',
          title: 'T',
          intro: 'Introduction.',
          items: ['Premier repère', 'Second repère'],
          note: 'À noter : une précision.',
        }}
      />
    );
    expect(screen.getByText('Introduction.')).toBeDefined();
    expect(screen.getByText('Premier repère')).toBeDefined();
    expect(screen.getByText('Second repère')).toBeDefined();
    expect(screen.getByText('À noter : une précision.')).toBeDefined();
  });

  /**
   * Le contenu SEO met en gras les chiffres clés et les intitulés de puce au
   * milieu des phrases : `intro`, `items` et `note` acceptent donc du HTML
   * restreint, comme `bodyHtml`.
   */
  it('rend le gras de intro, items et note', () => {
    render(
      <EditoSection
        data={{
          id: 'e',
          title: 'T',
          intro: 'Va de <strong>30 000 €</strong> à 1,5 million.',
          items: ['<strong>Production indicative :</strong> 250 à 320 œufs'],
          note: 'Le poulailler représente <strong>40 à 60 %</strong> du budget.',
        }}
      />
    );
    expect(screen.getByText('30 000 €').tagName).toBe('STRONG');
    expect(screen.getByText('Production indicative :').tagName).toBe('STRONG');
    expect(screen.getByText('40 à 60 %').tagName).toBe('STRONG');
  });

  it('assainit intro, items et note', () => {
    const { container } = render(
      <EditoSection
        data={{
          id: 'e',
          title: 'T',
          intro: 'a<script>alert(1)</script>',
          items: ['<a href="//evil">lien</a>'],
          note: '<img src=x onerror="alert(2)">',
        }}
      />
    );
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('a')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
    expect(container.innerHTML).not.toContain('onerror');
  });

  it('rend plusieurs paragraphes depuis bodyHtml', () => {
    const { container } = render(
      <EditoSection
        data={{ id: 'e', title: 'T', bodyHtml: '<p>Premier.</p><p>Second.</p>' }}
      />
    );
    expect(container.querySelectorAll('p')).toHaveLength(2);
  });

  it('rend bodyHtml en HTML, emphase comprise', () => {
    render(
      <EditoSection
        data={{ id: 'e', title: 'T', bodyHtml: 'Près de <strong>50 millions</strong> de poules.' }}
      />
    );
    expect(screen.getByText('50 millions').tagName).toBe('STRONG');
  });

  it('rend une liste HTML dans bodyHtml', () => {
    const { container } = render(
      <EditoSection
        data={{ id: 'e', title: 'T', bodyHtml: '<ul><li><strong>Intensif</strong> : dense.</li></ul>' }}
      />
    );
    expect(container.querySelectorAll('li')).toHaveLength(1);
    expect(screen.getByText('Intensif').tagName).toBe('STRONG');
  });

  /**
   * Le contenu vient de nos fichiers de données, pas d'un utilisateur — mais la
   * règle `.claude/rules/security.md` interdit tout dangerouslySetInnerHTML non
   * assaini sans exception : ces données pourraient venir d'un BO demain.
   */
  it('retire scripts, gestionnaires d’événements et liens de bodyHtml', () => {
    const { container } = render(
      <EditoSection
        data={{
          id: 'e',
          title: 'T',
          bodyHtml:
            'Texte <script>alert(1)</script><img src=x onerror="alert(2)"><a href="//evil">lien</a>',
        }}
      />
    );
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('a')).toBeNull();
    expect(container.innerHTML).not.toContain('onerror');
  });

  /**
   * RÉGRESSION : le bloc mélangeait trois typographies — paragraphes gris
   * `text-base`, puces noires `text-base`, encart gris `text-sm` — plus des
   * pastilles bleues. Une seule combinaison doit s'appliquer partout.
   */
  it('applique une typographie unique à intro, bodyHtml, items et note', () => {
    const { container } = render(
      <EditoSection
        data={{
          id: 'e',
          title: 'T',
          intro: 'Intro.',
          bodyHtml: '<p>Corps.</p>',
          items: ['Une puce'],
          note: 'À noter.',
        }}
      />
    );

    // `:not(h3)` depuis le passage du titre en niveau 3 : ce test contrôle la
    // typographie du CORPS, le titre en est exclu.
    const blocks = Array.from(
      container.querySelectorAll('section > div > *:not(h3):not(ul), li')
    );
    expect(blocks.length).toBeGreaterThan(0);
    for (const block of blocks) {
      expect(block.className, block.textContent ?? '').toContain('text-base');
      expect(block.className, block.textContent ?? '').toContain('text-foreground');
      expect(block.className, block.textContent ?? '').not.toContain('text-muted-foreground');
      expect(block.className, block.textContent ?? '').not.toContain('text-sm');
    }
  });

  it('rend les pastilles de puce en noir, pas en bleu', () => {
    const { container } = render(
      <EditoSection data={{ id: 'e', title: 'T', items: ['A', 'B'] }} />
    );
    const markers = container.querySelectorAll('li > [aria-hidden="true"]');
    expect(markers).toHaveLength(2);
    for (const marker of markers) {
      expect(marker.className).toContain('bg-foreground');
      expect(marker.className).not.toContain('bg-primary');
    }
  });

  it('n’affiche rien de superflu quand seuls le titre et une liste vide existent', () => {
    const { container } = render(<EditoSection data={{ id: 'e', title: 'T', items: [] }} />);
    expect(container.querySelectorAll('li')).toHaveLength(0);
  });
});
