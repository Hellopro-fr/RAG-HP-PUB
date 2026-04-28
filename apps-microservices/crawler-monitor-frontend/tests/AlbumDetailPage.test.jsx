import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock du client API utilisé par les hooks React Query (useAlbumProductsQuery,
// useProductRedownloadMutation, useDeleteProductMutation). Doit être posé
// AVANT l'import du composant.
vi.mock('../src/lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
  setOnUnauthorized: vi.fn(),
}));

import { api } from '../src/lib/api';
import AlbumDetailPage from '../src/pages/AlbumDetailPage';

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/albums/alpha.com']}>
        <Routes>
          <Route path="/albums/:domain" element={<AlbumDetailPage token="t" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const makeProduct = (n, overrides = {}) => ({
  id_produit:  String(n),
  nom:         `prod-${n}`,
  sync_status: 'synced',
  error_count: 0,
  image_count: 1,
  last_update: null,
  images: [
    {
      filename:   `f${n}.jpg`,
      url_source: `http://example.com/img${n}.jpg`,
      main:       `produit-2/0/0/0/${n}.jpg`,
      thumb:      `produit-3/0/0/0/${n}.jpg`,
      status:     'ok',
    },
  ],
  ...overrides,
});

describe('AlbumDetailPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('rend la liste des produits du domaine', async () => {
    api.get.mockResolvedValueOnce({
      products: [makeProduct(1), makeProduct(2)],
      total: 2,
      page: 1,
      page_size: 100,
      next_page: null,
      domain: 'alpha.com',
    });

    renderPage();

    await waitFor(() => expect(screen.getByText('prod-1')).toBeInTheDocument());
    expect(screen.getByText('prod-2')).toBeInTheDocument();
    // Header reflète les compteurs (2 produits, 2 images, 0 erreurs)
    expect(screen.getByText(/2 produits · 2 images/)).toBeInTheDocument();
  });

  it("affiche l'empty state quand aucun produit n'est retourné", async () => {
    api.get.mockResolvedValueOnce({
      products: [],
      total: 0,
      page: 1,
      page_size: 100,
      next_page: null,
      domain: 'alpha.com',
    });

    renderPage();

    await waitFor(() => expect(screen.getByText(/Pas encore de produits/i)).toBeInTheDocument());
  });
});
