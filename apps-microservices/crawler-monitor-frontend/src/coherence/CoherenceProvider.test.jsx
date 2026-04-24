import { describe, it, expect } from 'vitest';
import { render, renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CoherenceProvider } from './CoherenceProvider';
import { useCoherenceVerdict, useCoherenceSummary } from './hooks';
import { mkReplica } from './__fixtures__/mocks';

const mkWrapper = ({ token = 'tok', replicas = {}, seed } = {}) => {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  if (seed?.capacity) qc.setQueryData(['capacity'], seed.capacity);
  if (seed?.jobs) qc.setQueryData(['jobs'], seed.jobs);
  if (seed?.capacityPlanning)
    qc.setQueryData(['capacity-planning', 'ram', '1h'], seed.capacityPlanning);

  return function Wrapper({ children }) {
    return (
      <QueryClientProvider client={qc}>
        <CoherenceProvider token={token} replicas={replicas}>
          {children}
        </CoherenceProvider>
      </QueryClientProvider>
    );
  };
};

describe('CoherenceProvider', () => {
  it('runs replicas_vs_max_slots and exposes the violation', () => {
    const wrapper = mkWrapper({
      replicas: { r1: mkReplica('r1') },
      seed: { capacity: { max_global_jobs: 3, running_jobs: 0 } },
    });
    const { result } = renderHook(() => useCoherenceVerdict('replicas_vs_max_slots'), { wrapper });
    expect(result.current).toHaveLength(1);
    expect(result.current[0].data.phantom).toBe(2);
  });

  it('returns [] when sources have no issues', () => {
    const wrapper = mkWrapper({
      replicas: { r1: mkReplica('r1'), r2: mkReplica('r2') },
      seed: { capacity: { max_global_jobs: 2, running_jobs: 0 } },
    });
    const { result } = renderHook(() => useCoherenceVerdict('replicas_vs_max_slots'), { wrapper });
    expect(result.current).toEqual([]);
  });

  it('ignored rule returns [] even if violated', () => {
    const wrapper = mkWrapper({
      replicas: { r1: mkReplica('r1') },
      seed: { capacity: { max_global_jobs: 3, running_jobs: 0 } },
    });
    const { result } = renderHook(
      () => {
        const verdict = useCoherenceVerdict('replicas_vs_max_slots');
        const summary = useCoherenceSummary();
        return { verdict, summary };
      },
      { wrapper },
    );
    // Initially violated
    expect(result.current.verdict).toHaveLength(1);
    // Ignore it
    act(() => result.current.summary.setIgnored('replicas_vs_max_slots', true));
    expect(result.current.verdict).toEqual([]);
    // Un-ignore
    act(() => result.current.summary.setIgnored('replicas_vs_max_slots', false));
    expect(result.current.verdict).toHaveLength(1);
  });

  it('renders children without crashing', () => {
    const wrapper = mkWrapper();
    const { container } = render(<div data-testid="child">hello</div>, { wrapper });
    expect(container.textContent).toContain('hello');
  });

  it('summary counts violations by severity excluding ignored', () => {
    const wrapper = mkWrapper({
      replicas: { r1: mkReplica('r1') },
      seed: { capacity: { max_global_jobs: 3, running_jobs: 0 } },
    });
    const { result } = renderHook(() => useCoherenceSummary(), { wrapper });
    expect(result.current.byStatus.warning).toBe(1);
    act(() => result.current.setIgnored('replicas_vs_max_slots', true));
    expect(result.current.byStatus.warning).toBe(0);
  });
});
