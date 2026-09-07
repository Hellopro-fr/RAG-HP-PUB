/**
 * React Query hooks — the data layer of the dashboard.
 *
 * Conventions:
 *  - All hooks take `token` as first arg (auth comes from App.jsx)
 *  - Query keys are arrays starting with the resource name
 *  - Les clés sont DÉ-IMBRIQUÉES : une invalidation par préfixe (['jobs'])
 *    ne doit jamais entraîner le refetch d'une ressource plus lourde
 *    (détails / perf / replay d'un job).
 *  - WebSocket-driven invalidation lives in `useWsInvalidator` (bas de fichier)
 */

import { useCallback, useEffect, useMemo, useRef } from 'react';
import { useQuery, useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import { TERMINAL_JOB_STATUSES, isTerminalStatus } from '../lib/constants';

export const queryKeys = {
  jobs:               () => ['jobs'],
  jobDetails:         (id) => ['job-details', id],
  jobPerformance:     (id) => ['job-perf', id],
  jobReplay:          (id) => ['job-replay', id],
  capacity:           () => ['capacity'],
  capacityHistory:    (window) => ['capacity-history', window],
  replicasHistory:    (window) => ['replicas-history', window],
  capacityPlanning:   (window) => ['capacity-planning', 'ram', window],
  callbacks:          () => ['callbacks'],
  systemHealth:       () => ['system', 'health'],
  domains:            (window) => ['domains', window],
  domainDetail:       (domain, window) => ['domain-detail', domain, window],
  alerts:             () => ['alerts'],
  albums:             () => ['albums'],
  albumProducts:      (domain, params) => ['album-products', domain, params],
  albumDeleteJob:     (jobId) => ['album-delete-job', jobId],
};

// Statuts terminaux : définition unique dans lib/constants.js. Ré-exportés ici
// pour les appelants historiques qui les importaient depuis les hooks.
export { TERMINAL_JOB_STATUSES };

const isTerminal = isTerminalStatus;

/* ---------- Jobs ---------- */

export function useJobsQuery(token, options = {}) {
  return useQuery({
    queryKey: queryKeys.jobs(),
    queryFn: ({ signal }) => api.get('/jobs', token, { signal }),
    enabled: !!token,
    // /api/jobs pèse plusieurs Mo en prod : on évite les refetch rapprochés.
    staleTime: 15 * 1000,
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
    queryFn: ({ signal }) => api.get(`/jobs/${id}/details`, token, { signal }),
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
    queryFn: ({ signal }) => api.get('/capacity', token, { signal }),
    enabled: !!token,
    staleTime: 15 * 1000,
    ...options,
  });
}

export function useCapacityHistoryQuery(token, window = '1h', options = {}) {
  return useQuery({
    queryKey: queryKeys.capacityHistory(window),
    queryFn: ({ signal }) => api.get('/capacity/history', token, { query: { window }, retry: { attempts: 1 }, signal }),
    enabled: !!token,
    // Backend persists a snapshot every 60s. Polling at 60s matches that cadence
    // without pointless requests.
    refetchInterval: 60 * 1000,
    ...options,
  });
}

/**
 * Historique brut des heartbeats de TOUS les replicas.
 *
 * GET /api/replicas/history?window= → { window, replicas: { <id>: [{ts, cpu,
 * ram, totalRam, jobId}, …] } }. Le backend n'accepte que « 15m » et « 1h »
 * (replicahistory.ParseReplicaWindow) : l'appelant doit désactiver la query
 * au-delà. C'est la SEULE source de série temporelle de RAM — /capacity/history
 * ne renvoie que { ts, running, max, full }.
 */
export function useReplicasHistoryQuery(token, window = '1h', options = {}) {
  const { enabled: enabledByCaller, ...rest } = options;
  return useQuery({
    queryKey: queryKeys.replicasHistory(window),
    queryFn: ({ signal }) => api.get('/replicas/history', token, {
      query: { window }, retry: { attempts: 1 }, signal,
    }),
    // Heartbeat toutes les 2s côté crawler, mais la courbe est bucketée à 30s :
    // un rafraîchissement par minute suffit largement.
    refetchInterval: 60 * 1000,
    ...rest,
    enabled: (enabledByCaller ?? true) && !!token,
  });
}

export function useCapacityPlanningQuery(token, window = '1h', options = {}) {
  return useQuery({
    queryKey: queryKeys.capacityPlanning(window),
    queryFn: ({ signal }) => api.get('/capacity-planning/ram', token, { query: { window }, signal }),
    enabled: !!token,
    // Aggregate view; not worth refetching frequently. User can click refresh.
    staleTime: 60 * 1000,
    refetchInterval: false,
    ...options,
  });
}

/* ---------- Callbacks ---------- */

export function useCallbacksQuery(token, options = {}) {
  return useQuery({
    queryKey: queryKeys.callbacks(),
    queryFn: ({ signal }) => api.get('/callbacks', token, { signal }),
    enabled: !!token,
    ...options,
  });
}

/* ---------- System ---------- */

export function useSystemHealthQuery(token, options = {}) {
  return useQuery({
    queryKey: queryKeys.systemHealth(),
    queryFn: ({ signal }) => api.get('/system/health', token, { signal, retry: { attempts: 1 } }),
    enabled: !!token,
    refetchInterval: 30 * 1000,
    ...options,
  });
}

/* ---------- Job Performance ---------- */

/**
 * @param {object} [options]
 * @param {string} [options.jobStatus] — statut du job affiché. Le payload
 *   /jobs/:id/performance ne le porte pas (cf. Go internal/domain/jobperf) :
 *   l'appelant doit le fournir pour qu'on cesse de poller un job terminé.
 * @param {boolean} [options.enabled] — condition SUPPLÉMENTAIRE de l'appelant
 *   (ex. « l'onglet Métriques est affiché »). Elle se combine en ET avec le
 *   garde-fou token/id, elle ne le remplace pas.
 */
export function useJobPerformanceQuery(token, jobId, options = {}) {
  const { jobStatus, enabled: enabledByCaller, ...rest } = options;
  const terminal = isTerminal(jobStatus);
  return useQuery({
    queryKey: queryKeys.jobPerformance(jobId),
    queryFn: ({ signal }) => api.get(`/jobs/${jobId}/performance`, token, { signal }),
    refetchInterval: (q) => {
      // Défense en profondeur : si un jour le backend renvoie le statut, on le lit.
      const fromData = q.state.data?.status ?? q.state.data?.job?.status;
      if (isTerminal(fromData) || terminal) return false;
      return 15 * 1000;
    },
    ...rest,
    enabled: (enabledByCaller ?? true) && !!token && isValidJobId(jobId),
    // Garde-fou : un job terminé n'est JAMAIS pollé, même si l'appelant a passé
    // son propre refetchInterval.
    ...(terminal ? { refetchInterval: false } : null),
  });
}

export function useJobReplayQuery(token, jobId, options = {}) {
  return useQuery({
    queryKey: queryKeys.jobReplay(jobId),
    queryFn: ({ signal }) => api.get(`/jobs/${jobId}/replay`, token, { signal }),
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
    queryFn: ({ signal }) => api.get('/domains', token, { query: { window }, signal }),
    enabled: !!token,
    staleTime: 60 * 1000,
    ...options,
  });
}

export function useDomainDetailQuery(token, domain, window = '7d', options = {}) {
  return useQuery({
    queryKey: queryKeys.domainDetail(domain, window),
    queryFn: ({ signal }) => api.get(`/domains/${encodeURIComponent(domain)}`, token, { query: { window }, signal }),
    enabled: !!token && !!domain,
    staleTime: 60 * 1000,
    ...options,
  });
}

/* ---------- Alerts ---------- */

export function useAlertsQuery(token, options = {}) {
  return useQuery({
    queryKey: queryKeys.alerts(),
    queryFn: ({ signal }) => api.get('/alerts', token, { retry: { attempts: 1 }, signal }),
    enabled: !!token,
    staleTime: 60 * 1000,
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
    queryFn: ({ signal }) => api.get('/albums', token, { signal }),
    enabled: !!token,
    staleTime: 30 * 1000,
    ...options,
  });
}

export function useAlbumProductsQuery(token, domain, params = {}, options = {}) {
  return useInfiniteQuery({
    queryKey: queryKeys.albumProducts(domain, params),
    queryFn: ({ pageParam = 1, signal }) => api.get(
      `/albums/${encodeURIComponent(domain)}/products`,
      token,
      { query: { ...params, page: pageParam }, signal },
    ),
    enabled: !!token && !!domain,
    initialPageParam: 1,
    getNextPageParam: (last) => last?.next_page ?? undefined,
    staleTime: 15 * 1000,
    ...options,
  });
}

/**
 * Suivi d'un job de suppression d'album.
 *
 * Le registre des jobs vit EN MÉMOIRE dans image-download-service : après un
 * redémarrage du service le job est perdu et l'API répond 404. On arrête alors
 * le polling (sinon boucle infinie de 404 toutes les 1,5 s) et on expose
 * l'erreur pour que la page affiche un toast.
 */
export function useAlbumDeleteJobQuery(token, jobId, options = {}) {
  return useQuery({
    queryKey: queryKeys.albumDeleteJob(jobId),
    queryFn: ({ signal }) => api.get(`/albums/jobs/${jobId}`, token, { signal, retry: { attempts: 1 } }),
    enabled: !!token && !!jobId,
    retry: false,
    refetchInterval: (q) => {
      if (q.state.status === 'error') return false;
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
    // Clés dé-imbriquées : ['albums'] n'attrape plus les produits, on invalide
    // donc les deux explicitement.
    queryClient.invalidateQueries({ queryKey: queryKeys.albums(), exact: true });
    if (domain) {
      queryClient.invalidateQueries({ queryKey: ['album-products', domain] });
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

/* ---------- WS invalidation helper ---------- */

/** Fenêtre de coalescence des job_update (ms). */
export const WS_COALESCE_MS = 2500;

/**
 * Job actuellement affiché — état de MODULE, pas de hook.
 *
 * `useWsInvalidator` est appelé par plusieurs composants (App pour le WS,
 * Overview pour déclarer le job affiché). Avec un `useRef` par instance,
 * `setWatchedJobId` d'Overview n'était jamais vu par la vague de flush d'App :
 * les détails du job ouvert n'étaient rafraîchis que si React Query voyait
 * déjà un observer monté. Une seule case partagée règle le problème.
 */
const watchedJobId = { current: null };

/** Remise à zéro entre deux tests (état de module, donc persistant). */
export function __resetWatchedJobIdForTests() {
  watchedJobId.current = null;
}

/** Une query est « affichée » si au moins un composant monté l'observe. */
function isObserved(queryClient, queryKey) {
  const q = queryClient.getQueryCache().find({ queryKey });
  return !!q && q.getObserversCount() > 0;
}

/**
 * Returns a callback to invalidate queries on incoming WS events.
 * Called by the App-level WS handler.
 *
 *   handleJobUpdate(crawlId)  → range crawlId dans la vague courante ; la vague
 *                               est vidée au plus toutes les WS_COALESCE_MS.
 *   setWatchedJobId(id)       → déclare le job actuellement affiché : ses
 *                               détails/perf seront rafraîchis même si le
 *                               compteur d'observers n'est pas encore à jour.
 *
 * Par vague on invalide : jobs (exact), capacity (exact), callbacks, alerts et
 * les listes /domains (préfixe, toutes fenêtres). ['timeline'] a disparu : plus
 * aucun consommateur. Les détails/perf d'un job ne sont invalidés que s'ils
 * sont réellement affichés — sans quoi chaque job_update déclenchait deux scans
 * Redis complets côté backend.
 *
 * IMPORTANT: returns a STABLE object/callback (memoized). This avoids the
 * App.jsx WebSocket effect re-running on every render — which used to
 * reconnect the WS in a loop and miss heartbeats (regression fixed).
 */
export function useWsInvalidator() {
  const queryClient = useQueryClient();
  const pendingRef = useRef(null);   // Set<crawlId> de la vague en cours
  const timerRef = useRef(null);

  const flush = useCallback(() => {
    timerRef.current = null;
    const ids = pendingRef.current ?? new Set();
    pendingRef.current = null;

    queryClient.invalidateQueries({ queryKey: queryKeys.jobs(), exact: true });
    queryClient.invalidateQueries({ queryKey: queryKeys.capacity(), exact: true });
    queryClient.invalidateQueries({ queryKey: queryKeys.callbacks() });
    queryClient.invalidateQueries({ queryKey: queryKeys.alerts() });
    // Listes /domains : préfixe volontaire (une entrée par fenêtre).
    queryClient.invalidateQueries({ queryKey: ['domains'] });

    for (const id of ids) {
      if (!id) continue;
      const watched = watchedJobId.current === id;
      const detailsKey = queryKeys.jobDetails(id);
      const perfKey = queryKeys.jobPerformance(id);
      if (watched || isObserved(queryClient, detailsKey)) {
        queryClient.invalidateQueries({ queryKey: detailsKey, exact: true });
      }
      if (watched || isObserved(queryClient, perfKey)) {
        queryClient.invalidateQueries({ queryKey: perfKey, exact: true });
      }
    }
  }, [queryClient]);

  const handleJobUpdate = useCallback((crawlId) => {
    if (!pendingRef.current) pendingRef.current = new Set();
    if (crawlId) pendingRef.current.add(crawlId);
    if (timerRef.current) return; // vague déjà programmée
    timerRef.current = setTimeout(flush, WS_COALESCE_MS);
  }, [flush]);

  const setWatchedJobId = useCallback((id) => {
    watchedJobId.current = id || null;
  }, []);

  useEffect(() => () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    pendingRef.current = null;
  }, []);

  return useMemo(
    () => ({ handleJobUpdate, setWatchedJobId }),
    [handleJobUpdate, setWatchedJobId],
  );
}
