import { useState, useEffect, useRef, useCallback, lazy, Suspense } from 'react';
import { Routes, Route, useNavigate, Navigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { setOnUnauthorized } from './lib/api';
import { isReplicaLive } from './lib/replicas';
import { wsBackoffDelay } from './lib/backoff';
import {
  useCallbacksQuery,
  useSystemHealthQuery,
  useWsInvalidator,
  queryKeys,
} from './hooks/queries';
import LoginPage from './components/LoginPage';
import ErrorBoundary from './components/ErrorBoundary';
import Overview from './pages/Overview';
import { AppShell } from './components/layout/AppShell';
import { CoherenceProvider } from './coherence/CoherenceProvider';

// Lazy-loaded pages: downloaded only when the user navigates to them.
// Shrinks the initial bundle (Overview is the main entry; the rest is 50%+ of code
// that users rarely touch on first visit).
const QueuePage     = lazy(() => import('./pages/QueuePage'));
const DatasetPage   = lazy(() => import('./pages/DatasetPage'));
const CallbacksPage = lazy(() => import('./pages/CallbacksPage'));
const AuditPage     = lazy(() => import('./pages/AuditPage'));
const DomainsPage   = lazy(() => import('./pages/DomainsPage'));
const DomainPage    = lazy(() => import('./pages/DomainPage'));
const ReplayPage    = lazy(() => import('./pages/ReplayPage'));
const CapacityPlanningPage = lazy(() => import('./pages/CapacityPlanningPage'));
const CoherenceHealthPage = lazy(() => import('./coherence/components/CoherenceHealthPage'));
const AlbumsPage    = lazy(() => import('./pages/AlbumsPage'));
const AlbumDetailPage = lazy(() => import('./pages/AlbumDetailPage'));

const PageFallback = () => (
  <div className="flex items-center justify-center py-20">
    <RefreshCw className="w-8 h-8 animate-spin text-accent" />
  </div>
);

/** Code de fermeture WS « policy violation » — le backend l'utilise pour un token refusé. */
const WS_CLOSE_POLICY_VIOLATION = 1008;
/** Plafond de reconnexions avant de rester simplement hors ligne (plus de spam). */
const WS_MAX_RECONNECT_ATTEMPTS = 20;

/** Masque le JWT dans une URL WS avant de la logguer. */
const maskWsUrl = (url) => url.replace(/token=[^&]+/, 'token=***');

/**
 * App — auth gate + layout shell + router.
 *
 * Data layer is now React Query. App still holds:
 *   - token (auth)
 *   - replicas (WebSocket-only state, no REST endpoint)
 *   - WS connection lifecycle
 *
 * Everything else (jobs, capacity, callbacks count, job details) is fetched
 * via hooks (src/hooks/queries.js) directly in the page that needs them.
 * WebSocket job_update events are coalesced then trigger invalidateQueries via
 * useWsInvalidator().
 */
const App = () => {
  const [token, setToken] = useState(localStorage.getItem('authToken'));
  const [replicas, setReplicas] = useState({});
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef(null);
  // Reconnexion WS : timer en attente et compteur de tentatives (backoff).
  const reconnectTimerRef = useRef(null);
  const reconnectAttemptRef = useRef(0);

  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { handleJobUpdate } = useWsInvalidator();

  const handleLogin = (newToken) => {
    localStorage.setItem('authToken', newToken);
    setToken(newToken);
    navigate('/', { replace: true });
  };

  const handleLogout = useCallback(() => {
    localStorage.removeItem('authToken');
    setToken(null);
    queryClient.clear(); // drop cached data so a different user starts fresh
    navigate('/', { replace: true });
  }, [navigate, queryClient]);

  // Centralized 401 handler — called by lib/api when a request is refused.
  useEffect(() => {
    setOnUnauthorized(handleLogout);
    return () => setOnUnauthorized(null);
  }, [handleLogout]);

  // `handleLogout` change d'identité dès que `navigate` ou `queryClient` change
  // (chaque navigation react-router). Le garder en dépendance de l'effet WS
  // rejouait cet effet à chaque changement de page : socket fermée + rouverte,
  // heartbeats perdus. On le lit donc via un ref, mis à jour dans son propre
  // effet — l'effet WS ne dépend plus que du token et de handleJobUpdate.
  const logoutRef = useRef(handleLogout);
  useEffect(() => {
    logoutRef.current = handleLogout;
  }, [handleLogout]);

  // Header badge: number of failed callbacks (drives the visual cue).
  const callbacksQuery = useCallbacksQuery(token);
  const failedCallbackCount = callbacksQuery.data?.count || 0;
  const isJobsLoading = !!queryClient.isFetching({ queryKey: queryKeys.jobs(), exact: true });

  // Santé backend — alimente le badge « Live / Dégradé » de la Topbar.
  const systemHealthQuery = useSystemHealthQuery(token);
  const healthData = systemHealthQuery.data ?? null;
  const health = healthData
    ? {
        ...healthData,
        degraded: healthData.status === 'degraded' || healthData.redis_connected === false,
      }
    : null;

  // Heartbeat batching: replicas emit every 2s each. With N replicas we were
  // getting N re-renders per 2s (= full tree re-render of Overview + Recharts
  // internals). On long sessions this balloons Chrome's memory into the GB
  // range (Recharts retains D3 state, React accumulates fibers). We now buffer
  // heartbeats in a ref and flush once per second max — 1 re-render/s
  // regardless of replica count.
  const pendingReplicasRef = useRef({});
  const replicasFlushTimerRef = useRef(null);

  // WebSocket connection — avec reconnexion automatique (backoff exponentiel)
  useEffect(() => {
    if (!token) return;

    let cancelled = false; // fermé volontairement (cleanup) — propre à CETTE instance d'effet

    const flushReplicas = () => {
      replicasFlushTimerRef.current = null;
      const pending = pendingReplicasRef.current;
      pendingReplicasRef.current = {};
      if (Object.keys(pending).length === 0) return;
      setReplicas(prev => ({ ...prev, ...pending }));
    };

    const connect = () => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/api?token=${token}`;
      // Le JWT ne doit JAMAIS finir dans la console (partage de captures d'écran).
      if (import.meta.env.DEV) console.log('[ws] connexion à', maskWsUrl(wsUrl));
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (import.meta.env.DEV) console.log('[ws] connecté');
        setIsConnected(true);
        reconnectAttemptRef.current = 0; // reset du backoff après une connexion réussie
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'job_update') {
            // Coalescé côté useWsInvalidator (une vague / 2,5 s).
            handleJobUpdate(data.crawl_id);
          } else if (data.type === 'replica_heartbeat') {
            const hb = data.data;
            if (!hb || !hb.replicaId) return;
            // Buffer: same replicaId collapses to the latest heartbeat only.
            // Stamp browser-local receive time → liveness immune to clock skew
            // between this machine and the crawler container (see lib/replicas).
            pendingReplicasRef.current[hb.replicaId] = { ...hb, receivedAt: Date.now() };
            if (!replicasFlushTimerRef.current) {
              replicasFlushTimerRef.current = setTimeout(flushReplicas, 1000);
            }
          }
        } catch (e) {
          console.error('WebSocket message error:', e);
        }
      };

      ws.onclose = (event) => {
        setIsConnected(false);
        // Fermeture volontaire (unmount / changement de token) : pas de reconnexion.
        if (cancelled) return;

        // Token refusé explicitement par le backend (upgrade accepté puis close
        // 1008 « invalid_token »). Reboucler ne servirait qu'à marteler l'API.
        if (event?.code === WS_CLOSE_POLICY_VIOLATION) {
          if (import.meta.env.DEV) console.warn('[ws] token refusé (1008) — déconnexion');
          logoutRef.current?.();
          return;
        }

        // AUCUNE autre fermeture ne déconnecte l'opérateur. On a longtemps
        // compté les fermetures sans onopen (code 1006) comme la signature d'un
        // token mort : un simple redéploiement du backend (7 s d'indisponibilité)
        // produit exactement la même trace et vidait la session en pleine
        // surveillance. Seul le 1008 « invalid_token » est un verdict du serveur.
        if (reconnectAttemptRef.current >= WS_MAX_RECONNECT_ATTEMPTS) {
          // On reste hors ligne : le fallback REST 15 s prend le relais.
          if (import.meta.env.DEV) console.warn('[ws] abandon des reconnexions');
          return;
        }

        const delay = wsBackoffDelay(reconnectAttemptRef.current++);
        if (import.meta.env.DEV) console.log(`[ws] déconnecté — nouvelle tentative dans ${delay}ms`);
        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null;
          connect();
        }, delay);
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (wsRef.current) wsRef.current.close();
      // Drop any pending flush to avoid setState after unmount
      if (replicasFlushTimerRef.current) {
        clearTimeout(replicasFlushTimerRef.current);
        replicasFlushTimerRef.current = null;
      }
      pendingReplicasRef.current = {};
    };
  }, [token, handleJobUpdate]);

  // Fallback REST : si le WS est déconnecté, on rafraîchit les données clés
  // toutes les 15s pour que le dashboard ne gèle pas silencieusement.
  useEffect(() => {
    if (!token || isConnected) return;
    const interval = setInterval(() => {
      queryClient.invalidateQueries({ queryKey: queryKeys.jobs(), exact: true });
      queryClient.invalidateQueries({ queryKey: queryKeys.capacity(), exact: true });
      queryClient.invalidateQueries({ queryKey: queryKeys.callbacks() });
    }, 15_000);
    return () => clearInterval(interval);
  }, [token, isConnected, queryClient]);

  // Clean up zombie replicas (older than 30s)
  useEffect(() => {
    const interval = setInterval(() => {
      setReplicas(prev => {
        const now = Date.now();
        const next = {};
        let changed = false;
        Object.entries(prev).forEach(([id, data]) => {
          if (isReplicaLive(data, now)) {
            next[id] = data;
          } else {
            changed = true;
          }
        });
        return changed ? next : prev;
      });
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  if (!token) {
    return <LoginPage onLogin={handleLogin} />;
  }

  const handleManualRefresh = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.jobs(), exact: true });
    queryClient.invalidateQueries({ queryKey: queryKeys.capacity(), exact: true });
    queryClient.invalidateQueries({ queryKey: queryKeys.callbacks() });
  };

  return (
    <CoherenceProvider token={token} replicas={replicas}>
      <AppShell
        wsConnected={isConnected}
        health={health}
        badges={{ failedCallbacks: failedCallbackCount }}
        onLogout={handleLogout}
        onRefresh={handleManualRefresh}
        isRefreshing={isJobsLoading}
      >
        {/* Second ErrorBoundary : une page qui explose ne doit pas emporter le shell. */}
        <ErrorBoundary>
          <Suspense fallback={<PageFallback />}>
            <Routes>
              <Route path="/" element={<Overview token={token} replicas={replicas} />} />
              <Route path="/jobs/:id" element={<Overview token={token} replicas={replicas} />} />
              {/* Routes sœurs — plus imbriquées : Overview n'a plus d'<Outlet/>. */}
              <Route path="/jobs/:id/queue" element={<QueuePage token={token} />} />
              <Route path="/jobs/:id/dataset" element={<DatasetPage token={token} />} />
              <Route path="/jobs/:id/replay" element={<ReplayPage token={token} />} />
              <Route path="/callbacks" element={<CallbacksPage token={token} onClose={() => callbacksQuery.refetch()} />} />
              <Route path="/audit" element={<AuditPage token={token} />} />
              <Route path="/domains" element={<DomainsPage token={token} />} />
              <Route path="/domains/:domain" element={<DomainPage token={token} />} />
              <Route path="/albums" element={<AlbumsPage token={token} />} />
              <Route path="/albums/:domain" element={<AlbumDetailPage token={token} />} />
              <Route path="/capacity-planning" element={<CapacityPlanningPage token={token} />} />
              <Route path="/health" element={<CoherenceHealthPage token={token} />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </AppShell>
    </CoherenceProvider>
  );
}

export default App;
