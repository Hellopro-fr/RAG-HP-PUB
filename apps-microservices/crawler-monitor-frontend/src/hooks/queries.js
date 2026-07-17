/**
 * React Query hooks — the data layer of the dashboard.
 *
 * Conventions:
 *  - All hooks take `token` as first arg (auth comes from App.jsx)
 *  - Query keys are arrays starting with the resource name
 *  - WebSocket-driven invalidation lives in App.jsx via queryClient.invalidateQueries
 */

import { useCallback, useMemo } from 'react';
import { useQuery, useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';

export const queryKeys = {
  jobs:               () => ['jobs'],
  jobDetails:         (id) => ['jobs', id, 'details'],
  capacity:           () => ['capacity'],
  capacityHistory:    (window) => ['capacity', 'history', window],
  callbacks:          () => ['callbacks'],
  systemHealth:       () => ['system', 'health'],
  systemStats:        (window) => ['system', 'stats', window],
  replicasHistoryAll: (window) => ['replicas', 'history', 'all', window],
  timeline:           (window) => ['timeline', window],
  domains:            (window) => ['domains', window],
  domainDetail:       (domain, window) => ['domains', domain, window],
  alerts:             () => ['alerts'],
  jobPerformance:     (id) => ['jobs', id, 'performance'],
  jobReplay:          (id) => ['jobs', id, 'replay'],
  capacityPlanning:   (window) => ['capacity-planning', 'ram', window],
  albums:             () => ['albums'],
  albumProducts:      (domain, params) => ['albums', domain, 'products', params],
  albumErrors:        (domain) => ['albums', domain, 'errors'],
  albumDeleteJob:     (jobId) => ['albums', 'delete-job', jobId],
};

/* ---------- Jobs ---------- */

export function useJobsQuery(token, options = {}) {
  return useQuery({
    queryKey: queryKeys.jobs(),
    queryFn: () => api.get('/jobs', token),
    enabled: !!token,
    ...options,
  });
}

// A route param can come back as the literal string "undefined" / "null" if
// a Link/navigate was given a falsy id. Treat those as no-id to avoid firing
// a doomed GET /api/jobs/undefined/details that always 404s.
const isValidJobId = (id) =>
  typeof id === 'string' && id.length > 0 && id !== 'undefined' && id !== 'null';

export function useJobDetailsQuery(token, id, options = {}) {
  return useQuery({
    queryKey: queryKeys.jobDetails(id),
    queryFn: () => api.get(`/jobs/${id}/details`, token),
    enabled: !!token && isValidJobId(id),
    // job details can change as the crawler runs — slightly shorter staleness
    staleTime: 10 * 1000,
    ...options,
  });
}

/* ---------- Capacity ---------- */

export function useCapacityQuery(token, options = {}) {
  return useQuery({
    queryKey: queryKeys.capacity(),
    queryFn: () => api.get('/capacity', token),
    enabled: !!token,
    ...options,
  });
}

export function useCapacityHistoryQuery(token, window = '1h', options = {}) {
  return useQuery({
    queryKey: queryKeys.capacityHistory(window),
    queryFn: () => api.get('/capacity/history', token, { query: { window }, retry: { attempts: 1 } }),
    enabled: !!token,
    // Backend persists a snapshot every 60s. Polling at 60s matches that cadence
    // without pointless requests.
    refetchInterval: 60 * 1000,
    ...options,
  });
}

/* ---------- Callbacks ---------- */

export function useCallbacksQuery(token, options = {}) {
  return useQuery({
    queryKey: queryKeys.callbacks(),
    queryFn: () => api.get('/callbacks', token),
    enabled: !!token,
    ...options,
  });
}

/* ---------- System ---------- */

export function useSystemHealthQuery(token, options = {}) {
  return useQuery({
    queryKey: queryKeys.systemHealth(),
    queryFn: () => api.get('/system/health', token),
    enabled: !!token,
    refetchInterval: 30 * 1000,
    ...options,
  });
}

export function useSystemStatsQuery(token, window = '24h', options = {}) {
  return useQuery({
    queryKey: queryKeys.systemStats(window),
    queryFn: () => api.get('/system/stats', token, { query: { window } }),
    enabled: !!token,
    ...options,
  });
}

/* ---------- Replicas ---------- */

export function useReplicasHistoryQuery(token, window = '1h', options = {}) {
  return useQuery({
    queryKey: queryKeys.replicasHistoryAll(window),
    queryFn: () => api.get('/replicas/history', token, { query: { window }, retry: { attempts: 1 } }),
    enabled: !!token,
    // Replica history gets new points every 2s via heartbeats. 60s polling is
    // enough for the sparkline — the ~2s live values already come from WS.
    refetchInterval: 60 * 1000,
    ...options,
  });
}

/* ---------- Job Performance ---------- */

export function useJobPerformanceQuery(token, jobId, options = {}) {
  return useQuery({
    queryKey: queryKeys.jobPerformance(jobId),
    queryFn: () => api.get(`/jobs/${jobId}/performance`, token),
    enabled: !!token && isValidJobId(jobId),
    refetchInterval: 15 * 1000, // refresh every 15s while viewing a running job
    ...options,
  });
}

export function useCapacityPlanningQuery(token, window = '1h', options = {}) {
  return useQuery({
    queryKey: queryKeys.capacityPlanning(window),
    queryFn: () => api.get('/capacity-planning/ram', token, { query: { window } }),
    enabled: !!token,
    // Aggregate view; not worth refetching frequently. User can click refresh.
    staleTime: 60 * 1000,
    refetchInterval: false,
    ...options,
  });
}

export function useJobReplayQuery(token, jobId, options = {}) {
  return useQuery({
    queryKey: queryKeys.jobReplay(jobId),
    queryFn: () => api.get(`/jobs/${jobId}/replay`, token),
    enabled: !!token && isValidJobId(jobId),
    // Replay is static historical data; no auto-refresh.
    staleTime: 30 * 1000,
    ...options,
  });
}

/* ---------- Domains ---------- */

export function useDomainsQuery(token, window = '7d', options = {}) {
  return useQuery({
    queryKey: queryKeys.domains(window),
    queryFn: () => api.get('/domains', token, { query: { window } }),
    enabled: !!token,
    ...options,
  });
}

export function useDomainDetailQuery(token, domain, window = '7d', options = {}) {
  return useQuery({
    queryKey: queryKeys.domainDetail(domain, window),
    queryFn: () => api.get(`/domains/${encodeURIComponent(domain)}`, token, { query: { window } }),
    enabled: !!token && !!domain,
    ...options,
  });
}

/* ---------- Timeline ---------- */

/**
 * Accepts either a preset window ('1h','6h',...) OR custom {from, to} ISO dates.
 * When custom dates are passed, the window preset is ignored.
 */
export function useTimelineQuery(token, window = '6h', { from, to, ...options } = {}) {
  const isCustom = !!from && !!to;
  return useQuery({
    queryKey: isCustom ? queryKeys.timeline(`custom:${from}:${to}`) : queryKeys.timeline(window),
    queryFn: () => isCustom
      ? api.get('/timeline', token, { query: { from, to } })
      : api.get('/timeline', token, { query: { window } }),
    enabled: !!token,
    // Timeline is WS-invalidated on every job_update. We don't poll — the
    // moving-window "tail" being slightly stale for a few minutes is fine
    // given 30s staleTime default.
    refetchInterval: false,
    ...options,
  });
}

/* ---------- Alerts ---------- */

export function useAlertsQuery(token, options = {}) {
  return useQuery({
    queryKey: queryKeys.alerts(),
    queryFn: () => api.get('/alerts', token, { retry: { attempts: 1 } }),
    enabled: !!token,
    // Alerts are also invalidated by WS job_update (see useWsInvalidator).
    // Keep a 60s fallback poll for threshold crossings that don't correspond
    // to a job event (replica high CPU, capacity saturation).
    refetchInterval: 60 * 1000,
    ...options,
  });
}

/* ---------- Albums ---------- */

export function useAlbumsQuery(token, options = {}) {
  return useQuery({
    queryKey: queryKeys.albums(),
    queryFn: () => api.get('/albums', token),
    enabled: !!token,
    staleTime: 30 * 1000,
    ...options,
  });
}

export function useAlbumProductsQuery(token, domain, params = {}, options = {}) {
  return useInfiniteQuery({
    queryKey: queryKeys.albumProducts(domain, params),
    queryFn: ({ pageParam = 1 }) => api.get(
      `/albums/${encodeURIComponent(domain)}/products`,
      token,
      { query: { ...params, page: pageParam } },
    ),
    enabled: !!token && !!domain,
    initialPageParam: 1,
    getNextPageParam: (last) => last?.next_page ?? undefined,
    staleTime: 15 * 1000,
    ...options,
  });
}

export function useAlbumErrorsQuery(token, domain, options = {}) {
  return useQuery({
    queryKey: queryKeys.albumErrors(domain),
    queryFn: () => api.get(`/albums/${encodeURIComponent(domain)}/errors`, token),
    enabled: !!token && !!domain,
    ...options,
  });
}

export function useAlbumDeleteJobQuery(token, jobId, options = {}) {
  return useQuery({
    queryKey: queryKeys.albumDeleteJob(jobId),
    queryFn: () => api.get(`/albums/jobs/${jobId}`, token),
    enabled: !!token && !!jobId,
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      if (status === 'queued' || status === 'running') return 1500;
      return false;
    },
    ...options,
  });
}

/* ---------- Albums mutations ---------- */

function useAlbumInvalidator() {
  const queryClient = useQueryClient();
  return useCallback((domain) => {
    queryClient.invalidateQueries({ queryKey: ['albums'] });
    if (domain) {
      queryClient.invalidateQueries({ queryKey: ['albums', domain] });
    }
  }, [queryClient]);
}

export function useProductRedownloadMutation(token) {
  const invalidate = useAlbumInvalidator();
  return useMutation({
    mutationFn: ({ domain, productId }) => api.post(
      `/albums/${encodeURIComponent(domain)}/products/${encodeURIComponent(productId)}/redownload`,
      token,
      undefined,
    ),
    onSuccess: (_data, vars) => invalidate(vars?.domain),
  });
}

export function useImageRedownloadMutation(token) {
  const invalidate = useAlbumInvalidator();
  return useMutation({
    mutationFn: ({ domain, productId, imageId }) => api.post(
      `/albums/${encodeURIComponent(domain)}/products/${encodeURIComponent(productId)}/images/${encodeURIComponent(imageId)}/redownload`,
      token,
      undefined,
    ),
    onSuccess: (_data, vars) => invalidate(vars?.domain),
  });
}

export function useDeleteAlbumMutation(token) {
  const invalidate = useAlbumInvalidator();
  return useMutation({
    mutationFn: ({ domain }) => api.delete(`/albums/${encodeURIComponent(domain)}`, token),
    onSuccess: (_data, vars) => invalidate(vars?.domain),
  });
}

export function useDeleteProductMutation(token) {
  const invalidate = useAlbumInvalidator();
  return useMutation({
    mutationFn: ({ domain, productId }) => api.delete(
      `/albums/${encodeURIComponent(domain)}/products/${encodeURIComponent(productId)}`,
      token,
    ),
    onSuccess: (_data, vars) => invalidate(vars?.domain),
  });
}

export function useDeleteImageMutation(token) {
  const invalidate = useAlbumInvalidator();
  return useMutation({
    mutationFn: ({ domain, productId, imageId }) => api.delete(
      `/albums/${encodeURIComponent(domain)}/products/${encodeURIComponent(productId)}/images/${encodeURIComponent(imageId)}`,
      token,
    ),
    onSuccess: (_data, vars) => invalidate(vars?.domain),
  });
}

export function useMarkSyncedMutation(token) {
  const invalidate = useAlbumInvalidator();
  return useMutation({
    mutationFn: ({ domain, productId }) => api.post(
      `/albums/${encodeURIComponent(domain)}/products/${encodeURIComponent(productId)}/mark-synced`,
      token,
      undefined,
    ),
    onSuccess: (_data, vars) => invalidate(vars?.domain),
  });
}

/* ---------- WS invalidation helper ---------- */

/**
 * Returns a callback to invalidate queries on incoming WS events.
 * Called by the App-level WS handler.
 *
 *   handleJobUpdate(crawlId)  → invalidates jobs list, capacity, callbacks count,
 *                                and the job details if it's the affected id.
 *
 * IMPORTANT: returns a STABLE object/callback (memoized). This avoids the
 * App.jsx WebSocket effect re-running on every render — which used to
 * reconnect the WS in a loop and miss heartbeats (regression fixed).
 */
export function useWsInvalidator() {
  const queryClient = useQueryClient();
  const handleJobUpdate = useCallback((crawlId) => {
    queryClient.invalidateQueries({ queryKey: queryKeys.jobs() });
    queryClient.invalidateQueries({ queryKey: queryKeys.capacity() });
    queryClient.invalidateQueries({ queryKey: queryKeys.callbacks() });
    // Invalidate all timeline + domain windows (prefix match across windows)
    queryClient.invalidateQueries({ queryKey: ['timeline'] });
    queryClient.invalidateQueries({ queryKey: ['domains'] });
    queryClient.invalidateQueries({ queryKey: queryKeys.alerts() });
    if (crawlId) {
      queryClient.invalidateQueries({ queryKey: queryKeys.jobDetails(crawlId) });
    }
  }, [queryClient]);
  return useMemo(() => ({ handleJobUpdate }), [handleJobUpdate]);
}