import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

/*
 * Etat pilote par chaque test. `vi.hoisted` est obligatoire : les factories de
 * vi.mock sont hissees au-dessus des declarations du module de test.
 */
const state = vi.hoisted(() => ({ jobs: [], capacity: null, setWatchedJobId: vi.fn() }));

vi.mock('../src/hooks/queries', () => ({
  useJobsQuery: () => ({
    data: state.jobs,
    isLoading: false,
    isPending: false,
    dataUpdatedAt: 0,
    refetch: vi.fn(),
  }),
  useCapacityQuery: () => ({ data: state.capacity, isPending: false, isLoading: false }),
  useJobDetailsQuery: () => ({ data: null, isLoading: false, error: null }),
  useAlertsQuery: () => ({ data: { alerts: [] } }),
  useJobPerformanceQuery: () => ({ data: null, isLoading: false, isError: false }),
  useWsInvalidator: () => ({ handleJobUpdate: vi.fn(), setWatchedJobId: state.setWatchedJobId }),
}));

// Bandeau d'alertes et pastille de coherence : hors sujet ici, on les neutralise.
vi.mock('../src/components/AlertsBanner', () => ({ default: () => null }));
vi.mock('../src/coherence/components/CoherencePastille', () => ({
  CoherencePastille: () => null,
}));

import Overview from '../src/pages/Overview';

function renderOverview() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<Overview token="t" replicas={null} />} />
      </Routes>
    </MemoryRouter>,
  );
}

const job = (over) => ({ status: 'finished', domain: 'x.com', ...over });

describe('Overview', () => {
  beforeEach(() => {
    state.jobs = [];
    state.capacity = null;
  });

  it('trie par date decroissante et ne casse pas sur un start_time absent ou illisible', () => {
    state.jobs = [
      job({ id: 'a', domain: 'a.com', start_time: null }),
      // Format naif renvoye par le backend Python (pas de T, pas de Z).
      job({ id: 'b', domain: 'b.com', start_time: '2026-08-28 13:20:03.306901' }),
      job({ id: 'c', domain: 'c.com', start_time: 'pas-une-date' }),
      job({ id: 'd', domain: 'd.com', start_time: '2026-08-27T10:00:00Z' }),
    ];
    renderOverview();

    const domains = screen.getAllByText(/^[a-d]\.com$/).map(el => el.textContent);
    // Les deux dates lisibles passent devant, dans le bon ordre.
    expect(domains.slice(0, 2)).toEqual(['b.com', 'd.com']);
    // Aucun job n'est perdu : un start_time invalide ne doit pas evincer la ligne.
    expect(domains).toHaveLength(4);
  });

  it('borne la page courante quand la liste retrecit sous elle', () => {
    state.jobs = Array.from({ length: 45 }, (_, i) => job({
      id: `job-${i}`,
      domain: `dom-${i}.com`,
      start_time: `2026-08-28T10:${String(i % 60).padStart(2, '0')}:00Z`,
    }));
    const { rerender } = renderOverview();

    // On va page 3 (45 jobs / 20 par page).
    const next = screen.getByLabelText('Page suivante');
    fireEvent.click(next);
    fireEvent.click(next);
    expect(screen.getByLabelText('Numéro de page')).toHaveValue(3);

    // La liste retrecit a 5 jobs : la page 3 n'existe plus.
    state.jobs = state.jobs.slice(0, 5);
    rerender(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<Overview token="t" replicas={null} />} />
        </Routes>
      </MemoryRouter>,
    );

    // La tranche affichee doit repartir de la page 1, pas rester vide.
    expect(screen.queryByText('Aucun job à afficher.')).toBeNull();
    expect(screen.getByText('dom-0.com')).toBeInTheDocument();
  });

  it('annonce « jobs au total » et n\'expose plus les boutons factices', () => {
    state.jobs = [job({ id: 'a', domain: 'a.com', start_time: '2026-08-28T10:00:00Z' })];
    renderOverview();

    expect(screen.getByText(/1 jobs au total/)).toBeInTheDocument();
    expect(screen.queryByText(/jobs sur 24h/)).toBeNull();
    expect(screen.queryByRole('button', { name: /Exporter/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Nouveau job/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Rafraîchir/i })).toBeNull();
  });

  it('affiche le compteur serveur de jobs en cours plutot que le comptage local', () => {
    state.jobs = [
      job({ id: 'a', domain: 'a.com', status: 'running', start_time: '2026-08-28T10:00:00Z' }),
      job({ id: 'b', domain: 'b.com', status: 'running', start_time: '2026-08-28T09:00:00Z' }),
      job({ id: 'c', domain: 'c.com', status: 'running', start_time: '2026-08-28T08:00:00Z' }),
    ];
    state.capacity = { running_jobs: 1, max_global_jobs: 4, is_full: false };
    renderOverview();

    // 3 documents `running` cote /api/jobs, 1 seul reellement en vol.
    // '/ 4 slots' apparait aussi dans l'anneau de capacite : on accepte les deux.
    expect(screen.getAllByText('/ 4 slots').length).toBeGreaterThan(0);
    expect(screen.getByText(/\+2 présumés bloqués/)).toBeInTheDocument();
  });
});
