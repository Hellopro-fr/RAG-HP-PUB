import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CardCarousel } from '@/components/hub/CardCarousel';

/**
 * La pagination est MESURÉE (`scrollWidth / clientWidth`) et non déduite des
 * points de rupture Tailwind — ça évite de dupliquer les seuils en JS. jsdom ne
 * calculant aucune mise en page, on simule ces deux mesures.
 */
function stubTrackMetrics({ scrollWidth, clientWidth }: { scrollWidth: number; clientWidth: number }) {
  Object.defineProperty(HTMLUListElement.prototype, 'scrollWidth', {
    configurable: true,
    get: () => scrollWidth,
  });
  Object.defineProperty(HTMLUListElement.prototype, 'clientWidth', {
    configurable: true,
    get: () => clientWidth,
  });
}

const scrollToSpy = vi.fn();

beforeEach(() => {
  scrollToSpy.mockClear();
  HTMLUListElement.prototype.scrollTo = scrollToSpy as unknown as typeof window.scrollTo;
});

afterEach(() => {
  vi.restoreAllMocks();
});

function cards(count: number) {
  return Array.from({ length: count }, (_, i) => <li key={i}>Carte {i + 1}</li>);
}

describe('CardCarousel', () => {
  /**
   * Invariant SEO : les cartes sont de vrais enfants rendus côté serveur. Toutes
   * doivent être dans le DOM, y compris celles hors écran — c'est la raison
   * d'avoir écarté une librairie de carrousel.
   */
  it('rend toutes les cartes, même hors écran', () => {
    stubTrackMetrics({ scrollWidth: 3000, clientWidth: 1000 });
    render(<CardCarousel label="Test">{cards(7)}</CardCarousel>);
    for (let i = 1; i <= 7; i += 1) {
      expect(screen.getByText(`Carte ${i}`)).toBeDefined();
    }
  });

  it('expose la piste comme région nommée et focusable au clavier', () => {
    stubTrackMetrics({ scrollWidth: 3000, clientWidth: 1000 });
    render(<CardCarousel label="Carrousel — Équipements">{cards(7)}</CardCarousel>);
    const track = screen.getByLabelText('Carrousel — Équipements');
    expect(track.tagName).toBe('UL');
    expect(track).toHaveAttribute('tabindex', '0');
  });

  it('calcule le nombre de pages depuis les mesures de la piste', async () => {
    stubTrackMetrics({ scrollWidth: 3000, clientWidth: 1000 });
    render(<CardCarousel label="Test">{cards(9)}</CardCarousel>);
    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: /Aller à la page/ })).toHaveLength(3);
    });
  });

  it('n’affiche aucune commande quand tout tient sur une page', async () => {
    stubTrackMetrics({ scrollWidth: 900, clientWidth: 1000 });
    render(<CardCarousel label="Test">{cards(2)}</CardCarousel>);
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /Aller à la page/ })).toBeNull();
    });
    expect(screen.queryByLabelText('Cartes suivantes')).toBeNull();
  });

  it('marque la première page comme active au montage', async () => {
    stubTrackMetrics({ scrollWidth: 3000, clientWidth: 1000 });
    render(<CardCarousel label="Test">{cards(9)}</CardCarousel>);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /page 1 sur 3/ })).toHaveAttribute(
        'aria-current',
        'true'
      );
    });
  });

  it('désactive la flèche précédente sur la première page', async () => {
    stubTrackMetrics({ scrollWidth: 3000, clientWidth: 1000 });
    render(<CardCarousel label="Test">{cards(9)}</CardCarousel>);
    await waitFor(() => expect(screen.getByLabelText('Cartes précédentes')).toBeDisabled());
    expect(screen.getByLabelText('Cartes suivantes')).not.toBeDisabled();
  });

  it('défile d’une largeur de piste au clic sur la flèche suivante', async () => {
    stubTrackMetrics({ scrollWidth: 3000, clientWidth: 1000 });
    render(<CardCarousel label="Test">{cards(9)}</CardCarousel>);
    await waitFor(() => expect(screen.getByLabelText('Cartes suivantes')).toBeDefined());

    fireEvent.click(screen.getByLabelText('Cartes suivantes'));
    expect(scrollToSpy).toHaveBeenCalledWith({ left: 1000, behavior: 'smooth' });
  });

  it('saute à la page demandée au clic sur une pastille', async () => {
    stubTrackMetrics({ scrollWidth: 3000, clientWidth: 1000 });
    render(<CardCarousel label="Test">{cards(9)}</CardCarousel>);
    await waitFor(() => expect(screen.getByRole('button', { name: /page 3 sur 3/ })).toBeDefined());

    fireEvent.click(screen.getByRole('button', { name: /page 3 sur 3/ }));
    expect(scrollToSpy).toHaveBeenCalledWith({ left: 2000, behavior: 'smooth' });
  });

  /** Largeurs fractionnaires : sans tolérance, une page fantôme apparaissait. */
  it('n’invente pas de page pour quelques pixels de débordement', async () => {
    stubTrackMetrics({ scrollWidth: 1000.5, clientWidth: 1000 });
    render(<CardCarousel label="Test">{cards(3)}</CardCarousel>);
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /Aller à la page/ })).toBeNull();
    });
  });
});
