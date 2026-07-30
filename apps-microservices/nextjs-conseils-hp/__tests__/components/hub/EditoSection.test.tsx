import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EditoSection } from '@/components/hub/EditoSection';

describe('EditoSection', () => {
  it('porte son id comme ancre et rend le titre en h2', () => {
    const { container } = render(
      <EditoSection data={{ id: 'edito-budget', title: 'Quel budget prévoir ?' }} />
    );
    expect(container.querySelector('section#edito-budget')).not.toBeNull();
    expect(screen.getByRole('heading', { level: 2 }).textContent).toBe('Quel budget prévoir ?');
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

  it('n’affiche rien de superflu quand seuls le titre et une liste vide existent', () => {
    const { container } = render(<EditoSection data={{ id: 'e', title: 'T', items: [] }} />);
    expect(container.querySelectorAll('li')).toHaveLength(0);
  });
});
