import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { StickyCta } from '@/components/hub/StickyCta';
import { ASSISTANT_DIALOG_EVENT } from '@/components/hub/AssistantForm';

describe('StickyCta', () => {
  it('rend le libellé fourni', () => {
    render(<StickyCta label="Obtenir mon kit projet" />);
    expect(screen.getByRole('button', { name: /Obtenir mon kit projet/i })).toBeDefined();
  });

  it('émet l’événement d’ouverture du questionnaire au clic', () => {
    let fired = 0;
    const handler = () => {
      fired += 1;
    };
    window.addEventListener(ASSISTANT_DIALOG_EVENT, handler);
    try {
      render(<StickyCta label="Obtenir mon kit projet" />);
      fireEvent.click(screen.getByRole('button'));
      expect(fired).toBe(1);
    } finally {
      window.removeEventListener(ASSISTANT_DIALOG_EVENT, handler);
    }
  });

  /**
   * RÉGRESSION : le réservataire d'espace était un `pb-20 lg:pb-0` posé sur le
   * conteneur de page, ce qui laissait une bande de fond visible sous le footer.
   * Il doit vivre DANS ce composant, masqué par la même condition que la barre —
   * sinon on peut retirer la barre en laissant l'espace, ou l'inverse.
   */
  it('rend un réservataire d’espace masqué au-delà du breakpoint lg', () => {
    const { container } = render(<StickyCta label="X" />);
    const spacer = container.querySelector('[aria-hidden="true"]');
    expect(spacer).not.toBeNull();
    expect(spacer?.className).toContain('lg:hidden');
    expect(spacer?.className).toContain('h-20');
  });

  it('masque la barre fixe avec la même condition que le réservataire', () => {
    const { container } = render(<StickyCta label="X" />);
    const bar = container.querySelector('.fixed');
    expect(bar?.className).toContain('lg:hidden');
  });
});
