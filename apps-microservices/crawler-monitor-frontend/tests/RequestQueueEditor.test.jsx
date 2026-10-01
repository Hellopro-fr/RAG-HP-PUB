import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../src/lib/api', () => ({
  api: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
  setOnUnauthorized: vi.fn(),
}));

import { api } from '../src/lib/api';
import RequestQueueEditor from '../src/components/RequestQueueEditor';

// Nom de fichier realiste : il vient de l'URL crawlee, donc avec des caracteres
// reserves (espace, ?, &) qui doivent etre encodes dans le chemin appele.
const FILE = {
  path: 'exemple.fr/a b?c&d.json',
  domain: 'exemple.fr',
  name: 'a b?c&d.json',
  url: 'https://exemple.fr/a b?c&d',
  method: 'GET',
  isHandled: false,
  retryCount: 0,
};

const LIST_RESPONSE = {
  items: [FILE],
  total: 1,
  page: 1,
  limit: 50,
  totalPages: 1,
  counts: { total: 1, handled: 0, pending: 1 },
};

/** Ouvre l'editeur, selectionne le fichier et lance l'analyse de la queue. */
async function openAndAnalyze() {
  render(<RequestQueueEditor jobId="J1" token="t" />);
  fireEvent.click(await screen.findByTitle(FILE.url));
  fireEvent.click(await screen.findByRole('button', { name: /Analyser/ }));
  fireEvent.click(await screen.findByRole('button', { name: /Nettoyer \(3\)/ }));
}

describe('RequestQueueEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    api.get.mockImplementation((path) => {
      if (path.includes('/analyze')) {
        return Promise.resolve({
          total: 10, blocked: 3, valid: 7, blockedPercent: 30, validPercent: 70,
        });
      }
      if (path.endsWith('/request-queues')) return Promise.resolve(LIST_RESPONSE);
      return Promise.resolve({ url: FILE.url });
    });
  });

  it('encode le domaine et le nom de fichier dans le chemin appele', async () => {
    render(<RequestQueueEditor jobId="J1" token="t" />);
    fireEvent.click(await screen.findByTitle(FILE.url));

    await waitFor(() => {
      const paths = api.get.mock.calls.map(c => c[0]);
      expect(paths).toContain('/jobs/J1/request-queues/exemple.fr/a%20b%3Fc%26d.json');
    });
  });

  it('omet le compteur scanned quand le backend ne le renvoie pas', async () => {
    api.post.mockResolvedValue({ deleted: 3 });
    await openAndAnalyze();

    const msg = await screen.findByText(/Nettoyage patterns terminé/);
    expect(msg.textContent).toContain('3 supprimés');
    expect(msg.textContent).not.toContain('undefined');
  });

  it('affiche le compteur scanned quand le backend le renvoie', async () => {
    api.post.mockResolvedValue({ deleted: 3, scanned: 120 });
    await openAndAnalyze();

    const msg = await screen.findByText(/Nettoyage patterns terminé/);
    expect(msg.textContent).toContain('3 supprimés sur 120 scannés');
  });
});
