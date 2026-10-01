import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock du client API utilisé par useImageRedownloadMutation/useDeleteImageMutation.
// Doit être posé AVANT l'import du composant (sinon les hooks capturent
// l'instance non-mockée).
vi.mock('../src/lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
  setOnUnauthorized: vi.fn(),
}));

import { api } from '../src/lib/api';
import { ImageDetailSheet } from '../src/components/albums/ImageDetailSheet';

function wrap(ui) {
  const qc = new QueryClient({
    defaultOptions: {
      queries:   { retry: false, staleTime: Infinity },
      mutations: { retry: false },
    },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const PRODUCT = { id_produit: '60001', nom: 'perceuse-bosch' };
const IMAGE = {
  filename:   'a.jpg',
  url_source: 'https://x/y.jpg',
  main:       'produit-2/0/0/0/a.jpg',
  thumb:      'produit-3/0/0/0/a.jpg',
  status:     'ok',
};

describe('ImageDetailSheet', () => {
  beforeEach(() => vi.clearAllMocks());

  it('affiche les métadonnées image quand le drawer est ouvert', () => {
    wrap(
      <ImageDetailSheet
        open
        image={IMAGE}
        product={PRODUCT}
        domain="alpha.com"
        onClose={() => {}}
        token="t"
      />,
    );

    expect(screen.getByText('a.jpg')).toBeInTheDocument();
    expect(screen.getByText(/perceuse-bosch/)).toBeInTheDocument();
    // URL source affichée comme lien externe
    const link = screen.getByRole('link', { name: /https:\/\/x\/y\.jpg/ });
    expect(link).toHaveAttribute('href', 'https://x/y.jpg');
    expect(link).toHaveAttribute('target', '_blank');
    // Status badge "OK"
    expect(screen.getByText('OK')).toBeInTheDocument();
  });

  it('clique "Re-télécharger" → appelle la mutation avec le bon path', async () => {
    api.post.mockResolvedValueOnce({ downloaded: 1, failed: 0 });

    wrap(
      <ImageDetailSheet
        open
        image={IMAGE}
        product={PRODUCT}
        domain="alpha.com"
        onClose={() => {}}
        token="t"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Re-télécharger/i }));
    await waitFor(() => expect(api.post).toHaveBeenCalled());

    const callPath = api.post.mock.calls[0][0];
    expect(callPath).toMatch(
      /\/albums\/alpha\.com\/products\/60001\/images\/a\.jpg\/redownload$/,
    );
  });

  it('clique "Supprimer" → ouvre le dialog de confirmation puis appelle delete', async () => {
    api.delete.mockResolvedValueOnce({ ok: true });
    const onClose = vi.fn();

    wrap(
      <ImageDetailSheet
        open
        image={IMAGE}
        product={PRODUCT}
        domain="alpha.com"
        onClose={onClose}
        token="t"
      />,
    );

    // Bouton "Supprimer" du drawer → ouvre la dialog confirm
    fireEvent.click(screen.getByRole('button', { name: /^Supprimer$/i }));

    // La dialog confirm affiche un titre dédié
    await screen.findByText(/Supprimer l'image/i);

    // Confirmation finale → appelle DELETE puis ferme le drawer
    const confirmButtons = screen.getAllByRole('button', { name: /^Supprimer$/i });
    // Le bouton dans la dialog est le dernier rendu (overlay au-dessus du sheet)
    fireEvent.click(confirmButtons[confirmButtons.length - 1]);

    await waitFor(() => expect(api.delete).toHaveBeenCalled());
    const callPath = api.delete.mock.calls[0][0];
    expect(callPath).toMatch(
      /\/albums\/alpha\.com\/products\/60001\/images\/a\.jpg$/,
    );
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });
});
