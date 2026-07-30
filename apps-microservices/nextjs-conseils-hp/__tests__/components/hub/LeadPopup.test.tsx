import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { LeadPopup } from '@/components/hub/LeadPopup';
import { listHubPages } from '@/data/hub';
import type { HubLeadPopup } from '@/types/hub';

vi.mock('next/image', () => ({
  default: ({ src, alt, ...props }: { src: string; alt: string; [key: string]: unknown }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} {...props} />
  ),
}));

const data = listHubPages()[0].leadPopup;

const IMAGE = { src: '/images/hub/x/popup.png', alt: 'Guide' };

/**
 * Rend la pop-up et la force ouverte : le déclencheur réel est un dépassement de
 * scroll sur une section absente en test.
 */
function renderOpen(overrides: Partial<HubLeadPopup> = {}) {
  const section = document.createElement('section');
  section.id = data.triggerSectionId;
  // Section entièrement au-dessus du viewport → condition de déclenchement.
  section.getBoundingClientRect = () => ({ bottom: -10 }) as DOMRect;
  document.body.appendChild(section);

  const result = render(<LeadPopup data={{ ...data, ...overrides }} />);
  fireEvent.scroll(window);
  return result;
}

describe('LeadPopup', () => {
  it('reste fermée au montage', () => {
    render(<LeadPopup data={data} />);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('s’ouvre après avoir dépassé la section déclencheuse', async () => {
    renderOpen();
    await waitFor(() => expect(screen.getByRole('dialog')).toBeDefined());
    expect(screen.getByText(data.title)).toBeDefined();
  });

  /**
   * RÉGRESSION : la grille réservait toujours une colonne image de 140 px. Sans
   * visuel livré — le cas par défaut — le texte héritait de cette colonne et se
   * cassait en un mot par ligne.
   */
  it('ne réserve pas la colonne image quand aucun visuel n’est livré', async () => {
    const { container } = renderOpen({ image: undefined });
    await waitFor(() => expect(screen.getByRole('dialog')).toBeDefined());

    const grid = document.body.querySelector('[class*="sm:grid-cols-"]');
    expect(grid?.className).not.toContain('140px');
    expect(grid?.className).toContain('sm:grid-cols-1');
    expect(container).toBeDefined();
  });

  /** Élément de design du prototype, oublié au premier portage. */
  it('rend la pastille ronde, une ligne par entrée', async () => {
    renderOpen({ circleBadgeLines: ['100%', 'Gratuit'] });
    await waitFor(() => expect(screen.getByRole('dialog')).toBeDefined());
    expect(screen.getByText('100%')).toBeDefined();
    expect(screen.getByText('Gratuit')).toBeDefined();
  });

  it('n’affiche pas de pastille quand aucune ligne n’est déclarée', async () => {
    renderOpen({ circleBadgeLines: [] });
    await waitFor(() => expect(screen.getByRole('dialog')).toBeDefined());
    expect(screen.queryByText('Gratuit')).toBeNull();
  });

  it('rend le bandeau photo quand il est livré', async () => {
    renderOpen({
      bannerImage: { src: '/images/hub/x/banner.png', alt: 'Élevage de poules pondeuses' },
    });
    await waitFor(() => expect(screen.getByRole('dialog')).toBeDefined());
    expect(screen.getByAltText('Élevage de poules pondeuses')).toBeDefined();
  });

  it('n’affiche pas de bandeau quand il n’est pas livré', async () => {
    renderOpen({ bannerImage: undefined });
    await waitFor(() => expect(screen.getByRole('dialog')).toBeDefined());
    expect(screen.queryByAltText('Élevage de poules pondeuses')).toBeNull();
  });

  it('réserve la colonne image quand un visuel est livré', async () => {
    renderOpen({ image: IMAGE });
    await waitFor(() => expect(screen.getByRole('dialog')).toBeDefined());

    const grid = document.body.querySelector('[class*="sm:grid-cols-"]');
    expect(grid?.className).toContain('140px');
    expect(screen.getByAltText('Guide')).toBeDefined();
  });

  it('affiche la confirmation à la soumission, sans appel réseau', async () => {
    const calls: unknown[] = [];
    const originalFetch = globalThis.fetch;
    globalThis.fetch = ((...args: unknown[]) => {
      calls.push(args);
      return Promise.reject(new Error('aucun appel réseau attendu'));
    }) as typeof fetch;

    try {
      renderOpen();
      await waitFor(() => expect(screen.getByRole('dialog')).toBeDefined());

      fireEvent.change(screen.getByLabelText(data.emailPlaceholder), {
        target: { value: 'erick@hellopro.fr' },
      });
      fireEvent.click(screen.getByRole('button', { name: new RegExp(data.submitLabel, 'i') }));

      await waitFor(() => expect(screen.getByText(data.successMessage)).toBeDefined());
      expect(calls).toHaveLength(0);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
