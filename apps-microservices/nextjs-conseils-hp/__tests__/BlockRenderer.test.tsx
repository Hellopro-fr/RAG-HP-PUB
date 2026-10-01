import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { BlockRenderer } from '@/components/conseil/BlockRenderer';
import type { ConseilBlock } from '@/types/conseils';

describe('BlockRenderer', () => {
  /**
   * Le placeholder « à implémenter » de la Phase 4 n'existe plus : `h2` est rendu
   * par un vrai `H2Block`. Le test décrivait un état de chantier dépassé — et son
   * fixture ne compilait plus vraiment non plus, `H2BlockData` attendant
   * `title`/`id` là où il passait `text`.
   *
   * L'ancre `id` est vérifiée ici parce que c'est elle qui porte les liens
   * profonds indexés par Google (cf. le transformer, qui la dérive de l'ordre du
   * bloc et non d'un slug).
   */
  it('rend un vrai titre de section pour un bloc h2', () => {
    const block: ConseilBlock = {
      id: 'block-1',
      type: 'h2',
      order: 1,
      data: { id: '1', title: 'Mon titre' },
    };
    const { container } = render(<BlockRenderer block={block} />);
    expect(screen.getByRole('heading', { level: 2, name: 'Mon titre' })).toBeInTheDocument();
    // `querySelector('#1')` demanderait d'échapper un id commençant par un
    // chiffre — on lit l'attribut, c'est la même vérification en lisible.
    expect(container.querySelector('section')?.id).toBe('1');
  });

  it('rend l’intro du bloc h2 quand elle est fournie', () => {
    const block: ConseilBlock = {
      id: 'block-1',
      type: 'h2',
      order: 1,
      data: { id: '1', title: 'Mon titre', intro: 'Une introduction.' },
    };
    render(<BlockRenderer block={block} />);
    expect(screen.getByText('Une introduction.')).toBeInTheDocument();
  });
});
