import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock du client API utilisé par les hooks React Query (useAlbumsQuery,
// useDeleteAlbumMutation). Doit être posé AVANT l'import du composant.
vi.mock('../src/lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
  setOnUnauthorized: vi.fn(),
}));

import { api } from '../src/lib/api';
import AlbumsPage from '../src/pages/AlbumsPage';

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/albums']}>
        <Routes>
          <Route path="/albums" element={<AlbumsPage token="t" />} />
          <Route path="/albums/:domain" element={<div>DETAIL</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const baseAlbum = {
  product_count: 0,
  image_count: 0,
  error_count: 0,
  synced_count: 0,
  unsynced_count: 0,
  last_update: null,
  total_size_bytes: 0,
};

describe('AlbumsPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it("affiche l'empty state quand aucun album n'est retourné", async () => {
    api.get.mockResolvedValueOnce({ domains: [], total: 0 });
    renderPage();
    await waitFor(() => expect(screen.getByText(/Aucun album/i)).toBeInTheDocument());
  });

  it('rend les lignes et filtre par recherche', async () => {
    api.get.mockResolvedValueOnce({
      domains: [
        { ...baseAlbum, domain: 'alpha.com', product_count: 5, image_count: 12, synced_count: 5 },
        { ...baseAlbum, domain: 'beta.com',  product_count: 3, image_count: 4,  error_count: 1, synced_count: 2, unsynced_count: 1 },
      ],
      total: 2,
    });
    renderPage();

    await waitFor(() => expect(screen.getByText('alpha.com')).toBeInTheDocument());
    expect(screen.getByText('beta.com')).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText(/Rechercher un domaine/i), {
      target: { value: 'beta' },
    });

    await waitFor(() => expect(screen.queryByText('alpha.com')).not.toBeInTheDocument());
    expect(screen.getByText('beta.com')).toBeInTheDocument();
  });

  it('navigue vers /albums/:domain au clic sur une ligne', async () => {
    api.get.mockResolvedValueOnce({
      domains: [
        { ...baseAlbum, domain: 'alpha.com', product_count: 1, image_count: 1, synced_count: 1 },
      ],
      total: 1,
    });
    renderPage();

    await waitFor(() => expect(screen.getByText('alpha.com')).toBeInTheDocument());
    fireEvent.click(screen.getByText('alpha.com'));
    await waitFor(() => expect(screen.getByText('DETAIL')).toBeInTheDocument());
  });
});
