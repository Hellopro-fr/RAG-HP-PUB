import { describe, it, expect, vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TooltipProvider } from '../../components/ui/tooltip';
import { CoherenceProvider } from '../CoherenceProvider';
import CoherenceHealthPage from './CoherenceHealthPage';
import { mkReplica } from '../__fixtures__/mocks';

// Constants mirrored from CoherenceProvider to compute timing expectations
const EVAL_INTERVAL_MS = 5000;
const HYSTERESIS_MS = 4000;

const renderPage = ({ replicas = {}, capacity = null } = {}) => {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  if (capacity) qc.setQueryData(['capacity'], capacity);
  return render(
    <MemoryRouter initialEntries={['/health']}>
      <QueryClientProvider client={qc}>
        <TooltipProvider>
          <CoherenceProvider token="tok" replicas={replicas}>
            <CoherenceHealthPage />
          </CoherenceProvider>
        </TooltipProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
};

describe('CoherenceHealthPage', () => {
  it('renders header and KPI row', () => {
    renderPage();
    // h1 — use heading role to disambiguate from the subtitle paragraph
    expect(screen.getByRole('heading', { name: /Cohérence des données/i })).toBeInTheDocument();
    expect(screen.getByText(/règles ·/i)).toBeInTheDocument();
  });

  it('lists violating rule with its label and message', async () => {
    vi.useFakeTimers();
    renderPage({
      replicas: { r1: mkReplica('r1') },
      capacity: { max_global_jobs: 3, running_jobs: 0 },
    });
    // Advance past first eval tick + hysteresis before the violation is listed
    await act(async () => {
      vi.advanceTimersByTime(EVAL_INTERVAL_MS + HYSTERESIS_MS + 100);
    });
    expect(screen.getByText(/Replicas vs slots/i)).toBeInTheDocument();
    expect(screen.getByText(/3 slots configurés mais 1 replicas/)).toBeInTheDocument();
    vi.useRealTimers();
  });
});
