import { useState, useEffect, useRef, useCallback } from 'react';
import { Routes, Route, Link, useNavigate, Navigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import {
  Activity, AlertCircle, RefreshCw, LogOut, FileText, Globe,
} from 'lucide-react';
import { setOnUnauthorized } from './lib/api';
import { useCallbacksQuery, useWsInvalidator, queryKeys } from './hooks/queries';
import LoginPage from './components/LoginPage';
import Overview from './pages/Overview';
import QueuePage from './pages/QueuePage';
import DatasetPage from './pages/DatasetPage';
import CallbacksPage from './pages/CallbacksPage';
import AuditPage from './pages/AuditPage';
import DomainsPage from './pages/DomainsPage';
import DomainPage from './pages/DomainPage';

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
 * WebSocket job_update events trigger queryClient.invalidateQueries via
 * useWsInvalidator().
 */
const App = () => {
  const [token, setToken] = useState(localStorage.getItem('authToken'));
  const [replicas, setReplicas] = useState({});
  const [, setIsConnected] = useState(false);
  const wsRef = useRef(null);

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

  // Centralized 401 handler — called by lib/api when any request returns 401.
  useEffect(() => {
    setOnUnauthorized(handleLogout);
    return () => setOnUnauthorized(null);
  }, [handleLogout]);

  // Header badge: number of failed callbacks (drives the visual cue).
  const callbacksQuery = useCallbacksQuery(token);
  const failedCallbackCount = callbacksQuery.data?.count || 0;
  const isJobsLoading = !!queryClient.isFetching({ queryKey: queryKeys.jobs() });

  // WebSocket connection
  useEffect(() => {
    if (!token) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api?token=${token}`;
    console.log('Connecting to WebSocket:', wsUrl);
    wsRef.current = new WebSocket(wsUrl);

    wsRef.current.onopen = () => {
      console.log('Connected to WebSocket');
      setIsConnected(true);
    };

    wsRef.current.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'job_update') {
          handleJobUpdate(data.crawl_id);
        } else if (data.type === 'replica_heartbeat') {
          setReplicas(prev => ({
            ...prev,
            [data.data.replicaId]: data.data
          }));
        }
      } catch (e) {
        console.error('WebSocket message error:', e);
      }
    };

    wsRef.current.onclose = () => {
      console.log('WebSocket disconnected');
      setIsConnected(false);
    };

    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, [token, handleJobUpdate]);

  // Clean up zombie replicas (older than 30s)
  useEffect(() => {
    const interval = setInterval(() => {
      setReplicas(prev => {
        const now = Date.now();
        const next = {};
        let changed = false;
        Object.entries(prev).forEach(([id, data]) => {
          if (now - data.timestamp < 30000) {
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
    queryClient.invalidateQueries({ queryKey: queryKeys.jobs() });
    queryClient.invalidateQueries({ queryKey: queryKeys.capacity() });
    queryClient.invalidateQueries({ queryKey: queryKeys.callbacks() });
  };

  return (
    <div className="min-h-screen bg-gray-900 text-gray-300 font-sans">
      <header className="bg-gray-800/80 backdrop-blur-sm border-b border-gray-700 sticky top-0 z-20">
        <div className="container mx-auto px-4 py-3 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-4 hover:opacity-80 transition-opacity">
            <Activity className="w-8 h-8 text-blue-400" />
            <h1 className="text-xl font-bold text-white">Crawler Dashboard Pro</h1>
          </Link>
          <div className="flex gap-2">
            {failedCallbackCount > 0 && (
              <Link
                to="/callbacks"
                className="flex items-center gap-2 px-3 py-1 bg-red-900/50 hover:bg-red-900/70 border border-red-500/30 rounded-lg text-sm transition-colors"
                title="Voir les callbacks en échec"
              >
                <AlertCircle className="w-4 h-4 text-red-400" />
                <span className="text-red-300">{failedCallbackCount} callback{failedCallbackCount > 1 ? 's' : ''} en échec</span>
              </Link>
            )}
            <Link
              to="/domains"
              className="p-2 rounded-md hover:bg-gray-700 transition-colors text-gray-400 hover:text-white"
              title="Domains"
            >
              <Globe className="w-5 h-5" />
            </Link>
            <Link
              to="/audit"
              className="p-2 rounded-md hover:bg-gray-700 transition-colors text-gray-400 hover:text-white"
              title="Audit log"
            >
              <FileText className="w-5 h-5" />
            </Link>
            <button onClick={handleManualRefresh} className="p-2 rounded-md hover:bg-gray-700 transition-colors" title="Rafraîchir">
              <RefreshCw className={`w-5 h-5 ${isJobsLoading ? 'animate-spin' : ''}`} />
            </button>
            <button onClick={handleLogout} className="p-2 rounded-md hover:bg-red-700 transition-colors text-red-400 hover:text-white" title="Déconnexion">
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </div>
      </header>

      <Routes>
        <Route path="/" element={<Overview token={token} replicas={replicas} />} />
        <Route path="/jobs/:id" element={<Overview token={token} replicas={replicas} />}>
          <Route path="queue" element={<QueuePage token={token} />} />
          <Route path="dataset" element={<DatasetPage token={token} />} />
        </Route>
        <Route path="/callbacks" element={<CallbacksPage token={token} onClose={() => callbacksQuery.refetch()} />} />
        <Route path="/audit" element={<AuditPage token={token} />} />
        <Route path="/domains" element={<DomainsPage token={token} />} />
        <Route path="/domains/:domain" element={<DomainPage token={token} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}

export default App;