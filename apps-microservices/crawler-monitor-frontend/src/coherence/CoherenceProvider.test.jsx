import { describe, it, expect, vi } from 'vitest';
import { render, renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CoherenceProvider } from './CoherenceProvider';
import { useCoherenceVerdict, useCoherenceSummary } from './hooks';
import { mkReplica } from './__fixtures__/mocks';

// Constants mirrored from CoherenceProvider to compute timing expectations
const EVAL_INTERVAL_MS = 5000;
const HYSTERESIS_MS = 4000;

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
  it('runs replicas_vs_max_slots and exposes the violation', async () => {
    vi.useFakeTimers();
    const wrapper = mkWrapper({
      replicas: { r1: mkReplica('r1') },
      seed: { capacity: { max_global_jobs: 3, running_jobs: 0 } },
    });
    const { result } = renderHook(() => useCoherenceVerdict('replicas_vs_max_slots'), { wrapper });
    // Violation not shown yet (hysteresis not met at mount)
    expect(result.current).toEqual([]);
    // Advance past first eval tick + hysteresis
    await act(async () => {
      vi.advanceTimersByTime(EVAL_INTERVAL_MS + HYSTERESIS_MS + 100);
    });
    expect(result.current).toHaveLength(1);
    expect(result.current[0].data.phantom).toBe(2);
    vi.useRealTimers();
  });

  it('returns [] when sources have no issues', () => {
    const wrapper = mkWrapper({
      replicas: { r1: mkReplica('r1'), r2: mkReplica('r2') },
      seed: { capacity: { max_global_jobs: 2, running_jobs: 0 } },
    });
    const { result } = renderHook(() => useCoherenceVerdict('replicas_vs_max_slots'), { wrapper });
    expect(result.current).toEqual([]);
  });

  it('ignored rule returns [] even if violated', async () => {
    vi.useFakeTimers();
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
    // Advance past hysteresis so violation is exposed
    await act(async () => {
      vi.advanceTimersByTime(EVAL_INTERVAL_MS + HYSTERESIS_MS + 100);
    });
    expect(result.current.verdict).toHaveLength(1);
    // Ignore it
    act(() => result.current.summary.setIgnored('replicas_vs_max_slots', true));
    expect(result.current.verdict).toEqual([]);
    // Un-ignore
    act(() => result.current.summary.setIgnored('replicas_vs_max_slots', false));
    expect(result.current.verdict).toHaveLength(1);
    vi.useRealTimers();
  });

  it('renders children without crashing', () => {
    const wrapper = mkWrapper();
    const { container } = render(<div data-testid="child">hello</div>, { wrapper });
    expect(container.textContent).toContain('hello');
  });

  it('summary counts violations by severity excluding ignored', async () => {
    vi.useFakeTimers();
    const wrapper = mkWrapper({
      replicas: { r1: mkReplica('r1') },
      seed: { capacity: { max_global_jobs: 3, running_jobs: 0 } },
    });
    const { result } = renderHook(() => useCoherenceSummary(), { wrapper });
    // Advance past hysteresis
    await act(async () => {
      vi.advanceTimersByTime(EVAL_INTERVAL_MS + HYSTERESIS_MS + 100);
    });
    expect(result.current.byStatus.warning).toBe(1);
    act(() => result.current.setIgnored('replicas_vs_max_slots', true));
    expect(result.current.byStatus.warning).toBe(0);
    vi.useRealTimers();
  });

  it('ne fait pas remonter une violation transitoire (< hysteresis)', async () => {
    vi.useFakeTimers();
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    // running_count_parity: capacity.running_jobs=5 vs 2 jobs => diff=3 > 1 => violation
    qc.setQueryData(['capacity'], { running_jobs: 5 });
    qc.setQueryData(['jobs'], [
      { id: 'a', status: 'running' },
      { id: 'b', status: 'running' },
    ]);

    const Wrapper = ({ children }) => (
      <QueryClientProvider client={qc}>
        <CoherenceProvider token="tok" replicas={{}}>
          {children}
        </CoherenceProvider>
      </QueryClientProvider>
    );

    const { result } = renderHook(() => useCoherenceVerdict('running_count_parity'), { wrapper: Wrapper });

    // At mount: violation not shown yet (hysteresis not met)
    expect(result.current).toEqual([]);

    // Advance past first eval + hysteresis => violation now persisted
    await act(async () => {
      vi.advanceTimersByTime(EVAL_INTERVAL_MS + HYSTERESIS_MS + 100);
    });
    expect(result.current).toHaveLength(1);

    vi.useRealTimers();
  });
});

describe('CoherenceProvider autoRetry', () => {
  it('schedules invalidate after delayMs on violation', async () => {
    vi.useFakeTimers();
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    const spy = vi.spyOn(qc, 'invalidateQueries');
    qc.setQueryData(['capacity'], { running_jobs: 5 });
    qc.setQueryData(['jobs'], [
      { id: 'a', status: 'running' },
      { id: 'b', status: 'running' },
    ]);
    // 5 vs 2 => running_count_parity violates (diff=3 > 1 tolerance)

    const Wrapper = ({ children }) => (
      <QueryClientProvider client={qc}>
        <CoherenceProvider token="tok" replicas={{}}>
          {children}
        </CoherenceProvider>
      </QueryClientProvider>
    );

    const { result } = renderHook(() => useCoherenceSummary(), { wrapper: Wrapper });

    // At mount: no invalidate yet
    expect(spy).not.toHaveBeenCalled();

    // First: advance past hysteresis so violation becomes visible (triggers auto-retry scheduling)
    await act(async () => {
      vi.advanceTimersByTime(EVAL_INTERVAL_MS + HYSTERESIS_MS + 100);
    });

    // Then advance delayMs (3000ms) for the retry timer to fire
    await act(async () => {
      vi.advanceTimersByTime(3000);
    });

    // Should have called invalidate for capacity AND jobs
    const calledKeys = spy.mock.calls.map((c) => c[0].queryKey);
    expect(calledKeys).toContainEqual(['capacity']);
    expect(calledKeys).toContainEqual(['jobs']);
    expect(result.current.retryState.running_count_parity?.attempts).toBe(1);
    vi.useRealTimers();
  });

  it('stops retrying after maxAttempts', async () => {
    vi.useFakeTimers();
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    qc.setQueryData(['capacity'], { running_jobs: 5 });
    qc.setQueryData(['jobs'], [{ id: 'a', status: 'running' }]);

    const Wrapper = ({ children }) => (
      <QueryClientProvider client={qc}>
        <CoherenceProvider token="tok" replicas={{}}>
          {children}
        </CoherenceProvider>
      </QueryClientProvider>
    );
    const { result } = renderHook(() => useCoherenceSummary(), { wrapper: Wrapper });

    // Advance past hysteresis first
    await act(async () => { vi.advanceTimersByTime(EVAL_INTERVAL_MS + HYSTERESIS_MS + 100); });
    // Now advance enough for 3 retry cycles (only 2 should run, maxAttempts=2)
    await act(async () => { vi.advanceTimersByTime(3000); });
    await act(async () => { vi.advanceTimersByTime(3000); });
    await act(async () => { vi.advanceTimersByTime(3000); });

    expect(result.current.retryState.running_count_parity?.exhausted).toBe(true);
    expect(result.current.retryState.running_count_parity?.attempts).toBe(2);
    vi.useRealTimers();
  });
});
