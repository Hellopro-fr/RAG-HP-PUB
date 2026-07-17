import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TooltipProvider } from '../../components/ui/tooltip';
import { CoherenceProvider } from '../CoherenceProvider';
import { CoherencePastille } from './CoherencePastille';
import { mkReplica } from '../__fixtures__/mocks';

const renderWith = (ui, { replicas = {}, capacity = null } = {}) => {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  if (capacity) qc.setQueryData(['capacity'], capacity);
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <TooltipProvider>
          <CoherenceProvider token="tok" replicas={replicas}>
            {ui}
          </CoherenceProvider>
        </TooltipProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
};

describe('CoherencePastille', () => {
  it('renders nothing when no violation', () => {
    const { container } = renderWith(
      <CoherencePastille ruleId="replicas_vs_max_slots" />,
      {
        replicas: { r1: mkReplica('r1'), r2: mkReplica('r2') },
        capacity: { max_global_jobs: 2, running_jobs: 0 },
      },
    );
    expect(container.innerHTML).toBe('');
  });

  it('renders an icon + link when violated', () => {
    renderWith(<CoherencePastille ruleId="replicas_vs_max_slots" />, {
      replicas: { r1: mkReplica('r1') },
      capacity: { max_global_jobs: 3, running_jobs: 0 },
    });
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', '/health#rule-replicas_vs_max_slots');
    expect(link).toHaveAttribute(
      'aria-label',
      expect.stringMatching(/Incohérence/),
    );
  });

  it('renders nothing for unknown rule id', () => {
    const { container } = renderWith(<CoherencePastille ruleId="nope_not_a_rule" />);
    expect(container.innerHTML).toBe('');
  });

  it('filters by itemKey (per-item rule)', () => {
    const { container } = renderWith(
      <CoherencePastille ruleId="replicas_vs_max_slots" itemKey="whatever" />,
      {
        replicas: { r1: mkReplica('r1') },
        capacity: { max_global_jobs: 3, running_jobs: 0 },
      },
    );
    // replicas_vs_max_slots is global (no itemKey in violation) → filter yields [] → null
    expect(container.innerHTML).toBe('');
  });
});
