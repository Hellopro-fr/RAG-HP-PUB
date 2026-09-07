import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import {
  useWsInvalidator,
  WS_COALESCE_MS,
  queryKeys,
  __resetWatchedJobIdForTests,
} from '../src/hooks/queries';

const mkClient = () =>
  new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });

const mkWrapper = (qc) =>
  function Wrapper({ children }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };

const invalidatedKeys = (spy) => spy.mock.calls.map((c) => c[0].queryKey);

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  // `watchedJobId` vit au niveau module : sans reset, un test contamine le suivant.
  __resetWatchedJobIdForTests();
});

describe('useWsInvalidator — vague coalescée', () => {
  it("n'invalide pas les détails/perf/replay d'un job qui n'est pas affiché", () => {
    vi.useFakeTimers();
    const qc = mkClient();
    // Données encore en cache (job consulté puis quitté) mais AUCUN observer.
    qc.setQueryData(queryKeys.jobDetails('j1'), { id: 'j1' });
    qc.setQueryData(queryKeys.jobPerformance('j1'), { job_id: 'j1', points: [] });
    qc.setQueryData(queryKeys.jobReplay('j1'), { job_id: 'j1' });
    const spy = vi.spyOn(qc, 'invalidateQueries');

    const { result } = renderHook(() => useWsInvalidator(), { wrapper: mkWrapper(qc) });
    act(() => result.current.handleJobUpdate('j1'));
    act(() => { vi.advanceTimersByTime(WS_COALESCE_MS + 10); });

    const keys = invalidatedKeys(spy);
    expect(keys).toEqual([['jobs'], ['capacity'], ['callbacks'], ['alerts'], ['domains']]);
    expect(keys).not.toContainEqual(['job-details', 'j1']);
    expect(keys).not.toContainEqual(['job-perf', 'j1']);
    expect(keys).not.toContainEqual(['job-replay', 'j1']);
  });

  it("invalide job-details/job-perf quand la query est réellement observée", () => {
    vi.useFakeTimers();
    const qc = mkClient();
    qc.setQueryData(queryKeys.jobDetails('j1'), { id: 'j1' });
    qc.setQueryData(queryKeys.jobPerformance('j1'), { job_id: 'j1' });
    const spy = vi.spyOn(qc, 'invalidateQueries');

    // Un composant monté observe les deux clés (comme Overview + JobDetails).
    const { result } = renderHook(
      () => {
        useQuery({ queryKey: queryKeys.jobDetails('j1'), queryFn: () => ({ id: 'j1' }) });
        useQuery({ queryKey: queryKeys.jobPerformance('j1'), queryFn: () => ({ job_id: 'j1' }) });
        return useWsInvalidator();
      },
      { wrapper: mkWrapper(qc) },
    );

    act(() => result.current.handleJobUpdate('j1'));
    act(() => { vi.advanceTimersByTime(WS_COALESCE_MS + 10); });

    const keys = invalidatedKeys(spy);
    expect(keys).toContainEqual(['job-details', 'j1']);
    expect(keys).toContainEqual(['job-perf', 'j1']);
    // job-replay n'est pas observé → toujours pas invalidé
    expect(keys).not.toContainEqual(['job-replay', 'j1']);
  });

  it('setWatchedJobId force le rafraîchissement du job affiché', () => {
    vi.useFakeTimers();
    const qc = mkClient();
    const spy = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(() => useWsInvalidator(), { wrapper: mkWrapper(qc) });

    act(() => result.current.setWatchedJobId('j9'));
    act(() => result.current.handleJobUpdate('j9'));
    act(() => { vi.advanceTimersByTime(WS_COALESCE_MS + 10); });

    const keys = invalidatedKeys(spy);
    expect(keys).toContainEqual(['job-details', 'j9']);
    expect(keys).toContainEqual(['job-perf', 'j9']);
  });

  it('setWatchedJobId est partagé entre deux instances du hook', () => {
    vi.useFakeTimers();
    const qc = mkClient();
    const spy = vi.spyOn(qc, 'invalidateQueries');
    const wrapper = mkWrapper(qc);

    // Deux consommateurs distincts, comme App (WS) et Overview (job affiché).
    const a = renderHook(() => useWsInvalidator(), { wrapper });
    const b = renderHook(() => useWsInvalidator(), { wrapper });

    act(() => a.result.current.setWatchedJobId('j1'));
    act(() => b.result.current.handleJobUpdate('j1'));
    act(() => { vi.advanceTimersByTime(WS_COALESCE_MS + 10); });

    const keys = invalidatedKeys(spy);
    expect(keys).toContainEqual(['job-details', 'j1']);
    expect(keys).toContainEqual(['job-perf', 'j1']);
  });

  it('coalesce 5 job_update en 1s en UNE seule vague (5 invalidations)', () => {
    vi.useFakeTimers();
    const qc = mkClient();
    const spy = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(() => useWsInvalidator(), { wrapper: mkWrapper(qc) });

    act(() => {
      for (let i = 0; i < 5; i++) {
        result.current.handleJobUpdate(`j${i}`);
        vi.advanceTimersByTime(200); // 5 événements étalés sur 1s
      }
    });
    // Rien n'est encore parti : la fenêtre de coalescence n'est pas écoulée.
    expect(spy).not.toHaveBeenCalled();

    act(() => { vi.advanceTimersByTime(WS_COALESCE_MS); });

    // AVANT : 7 invalidations x 5 événements = 35 (dont 2 scans Redis complets
    // par événement). APRÈS : 5 invalidations, une seule fois.
    expect(invalidatedKeys(spy)).toEqual([
      ['jobs'], ['capacity'], ['callbacks'], ['alerts'], ['domains'],
    ]);
  });

  it('ne relance pas la timeline (plus aucun consommateur)', () => {
    vi.useFakeTimers();
    const qc = mkClient();
    const spy = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(() => useWsInvalidator(), { wrapper: mkWrapper(qc) });
    act(() => result.current.handleJobUpdate('j1'));
    act(() => { vi.advanceTimersByTime(WS_COALESCE_MS + 10); });
    expect(invalidatedKeys(spy)).not.toContainEqual(['timeline']);
  });

  it('purge le timer au démontage (pas de flush après unmount)', () => {
    vi.useFakeTimers();
    const qc = mkClient();
    const spy = vi.spyOn(qc, 'invalidateQueries');
    const { result, unmount } = renderHook(() => useWsInvalidator(), { wrapper: mkWrapper(qc) });
    act(() => result.current.handleJobUpdate('j1'));
    unmount();
    act(() => { vi.advanceTimersByTime(WS_COALESCE_MS * 2); });
    expect(spy).not.toHaveBeenCalled();
  });
});

describe('queryKeys — clés dé-imbriquées', () => {
  it("['jobs'] ne préfixe plus détails/perf/replay", () => {
    expect(queryKeys.jobs()).toEqual(['jobs']);
    expect(queryKeys.jobDetails('x')[0]).not.toBe('jobs');
    expect(queryKeys.jobPerformance('x')[0]).not.toBe('jobs');
    expect(queryKeys.jobReplay('x')[0]).not.toBe('jobs');
  });

  it("['capacity'] ne préfixe plus l'historique", () => {
    expect(queryKeys.capacityHistory('1h')[0]).not.toBe('capacity');
  });

  it("['domains'] préfixe les listes mais pas le détail d'un domaine", () => {
    expect(queryKeys.domains('7d')[0]).toBe('domains');
    expect(queryKeys.domainDetail('a.fr', '7d')[0]).not.toBe('domains');
  });

  it("['albums'] ne préfixe plus produits / job de suppression", () => {
    expect(queryKeys.albums()).toEqual(['albums']);
    expect(queryKeys.albumProducts('a.fr', {})[0]).not.toBe('albums');
    expect(queryKeys.albumDeleteJob('jid')[0]).not.toBe('albums');
  });
});
