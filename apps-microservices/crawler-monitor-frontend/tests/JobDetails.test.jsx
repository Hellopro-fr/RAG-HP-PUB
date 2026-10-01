import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../src/hooks/queries', () => ({
  useJobPerformanceQuery: () => ({ data: null, isLoading: false, isError: false }),
}));

import JobDetails from '../src/components/JobDetails';

function renderJob(job) {
  return render(
    <MemoryRouter>
      <JobDetails job={job} token="t" inline />
    </MemoryRouter>,
  );
}

describe('JobDetails', () => {
  it("liste les erreurs du log quand l'API en renvoie", () => {
    renderJob({
      id: 'j1',
      domain: 'a.com',
      status: 'running',
      errors: ['ERR ECONNRESET sur /produits', 'ERR 503 sur /contact'],
      rawContent: 'ligne de log',
    });

    expect(screen.getByText('ERR ECONNRESET sur /produits')).toBeInTheDocument();
    expect(screen.getByText('ERR 503 sur /contact')).toBeInTheDocument();
    // L'ancien message trompeur ne doit plus apparaitre.
    expect(screen.queryByText(/statistiques ne sont pas encore disponibles/i)).toBeNull();
  });

  it('explique pourquoi le log manque sur un job archive', () => {
    renderJob({ id: 'j2', domain: 'a.com', status: 'archived' });

    expect(
      screen.getByText('Log du crawl indisponible (job archivé ou stockage purgé).'),
    ).toBeInTheDocument();
  });

  it("annonce un log en cours d'ecriture sur un job qui tourne", () => {
    renderJob({ id: 'j3', domain: 'a.com', status: 'running' });

    expect(screen.getByText(/Log en cours d’écriture/)).toBeInTheDocument();
  });

  it('remplit la carte Configuration depuis job.config', () => {
    renderJob({
      id: 'j4',
      domain: 'a.com',
      status: 'finished',
      config: {
        // `strategy` est le crawlMode remappé par le backend : les seules
        // valeurs réelles sont « update » et « standard », jamais « bfs ».
        strategy: 'update',
        depth: 3,
        concurrency: 5,
        method: 'GET',
        perminute: 120,
        previousCrawlId: 'crawl-42',
      },
    });

    expect(screen.getByText('Configuration')).toBeInTheDocument();
    expect(screen.getByText('Mode de crawl')).toBeInTheDocument();
    expect(screen.getByText('update')).toBeInTheDocument();
    // La ligne « Mode » doublonnait « Stratégie » (même valeur) : elle a sauté.
    expect(screen.queryByText('Stratégie')).toBeNull();
    expect(screen.queryByText('Mode')).toBeNull();
    expect(screen.getByText('5 en parallèle')).toBeInTheDocument();
    expect(screen.getByText('120/min')).toBeInTheDocument();
    expect(screen.getByText('crawl-42')).toBeInTheDocument();
    // La carte Pipeline (jamais alimentee par l'API) a disparu.
    expect(screen.queryByText('Pipeline')).toBeNull();
  });

  it('retombe sur une allowlist de job.params tant que job.config est absent', () => {
    renderJob({
      id: 'j5',
      domain: 'a.com',
      status: 'finished',
      params: {
        method: 'POST',
        typecrawling: 'full',
        storage_path: '/data/secret/should-not-render',
      },
    });

    expect(screen.getByText('POST')).toBeInTheDocument();
    expect(screen.getByText('full')).toBeInTheDocument();
    // Les champs hors allowlist ne doivent jamais fuiter dans l'UI.
    expect(screen.queryByText('/data/secret/should-not-render')).toBeNull();
  });

  it('ne propose plus que les onglets Logs et Métriques', () => {
    renderJob({ id: 'j6', domain: 'a.com', status: 'finished' });

    const tabs = screen.getAllByRole('tab').map(t => t.textContent.trim());
    expect(tabs).toEqual(['Logs', 'Métriques']);
    // Queue / Dataset / Replay sont devenus des liens vers de vraies routes.
    expect(screen.getByRole('link', { name: /Queue/ })).toHaveAttribute('href', '/jobs/j6/queue');
    expect(screen.getByRole('link', { name: /Dataset/ })).toHaveAttribute('href', '/jobs/j6/dataset');
    expect(screen.getByRole('link', { name: /Replay/ })).toHaveAttribute('href', '/jobs/j6/replay');
  });
});
