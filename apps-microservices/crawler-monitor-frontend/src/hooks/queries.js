/**
 * React Query hooks — the data layer of the dashboard.
 *
 * Conventions:
 *  - All hooks take `token` as first arg (auth comes from App.jsx)
 *  - Query keys are arrays starting with the resource name
 *  - WebSocket-driven invalidation lives in App.jsx via queryClient.invalidateQueries
 */

import { useQuery, useQueryClient } from '@tanstack/react-query';
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

export function useJobDetailsQuery(token, id, options = {}) {
  return useQuery({
    queryKey: queryKeys.jobDetails(id),
    queryFn: () => api.get(`/jobs/${id}/details`, token),
    enabled: !!token && !!id,
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
    refetchInterval: 60 * 1000, // background refresh every 60s for the sparkline
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
    refetchInterval: 30 * 1000, // background refresh every 30s for sparklines
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

export function useTimelineQuery(token, window = '6h', options = {}) {
  return useQuery({
    queryKey: queryKeys.timeline(window),
    queryFn: () => api.get('/timeline', token, { query: { window } }),
    enabled: !!token,
    refetchInterval: 30 * 1000, // background refresh
    ...options,
  });
}

/* ---------- WS invalidation helper ---------- */

/**
 * Returns a callback to invalidate queries on incoming WS events.
 * Called by the App-level WS handler.
 *
 *   handleJobUpdate(crawlId)  → invalidates jobs list, capacity, callbacks count,
 *                                and the job details if it's the affected id.
 */
export function useWsInvalidator() {
  const queryClient = useQueryClient();
  return {
    handleJobUpdate: (crawlId) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.jobs() });
      queryClient.invalidateQueries({ queryKey: queryKeys.capacity() });
      queryClient.invalidateQueries({ queryKey: queryKeys.callbacks() });
      // Invalidate all timeline + domain windows (prefix match across windows)
      queryClient.invalidateQueries({ queryKey: ['timeline'] });
      queryClient.invalidateQueries({ queryKey: ['domains'] });
      if (crawlId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.jobDetails(crawlId) });
      }
    },
  };
}