import { useState, useEffect, useRef, useCallback } from 'react';
import { Routes, Route, Link, useNavigate, useLocation, Navigate } from 'react-router-dom';
import {
  Activity, AlertCircle, RefreshCw, LogOut, FileText,
} from 'lucide-react';
import { api, setOnUnauthorized } from './lib/api';
import LoginPage from './components/LoginPage';
import Overview from './pages/Overview';
import QueuePage from './pages/QueuePage';
import DatasetPage from './pages/DatasetPage';
import CallbacksPage from './pages/CallbacksPage';
import AuditPage from './pages/AuditPage';

/**
 * App is the auth gate + layout shell + router.
 *
 * - Holds auth state (token in localStorage) and exposes login/logout
 * - Holds shared dashboard state: jobs, capacity, replicas, callbacks count,
 *   currently-selected job (URL-driven via /jobs/:id)
 * - Manages the WebSocket connection (job_update, replica_heartbeat)
 * - Renders the top header + <Routes>
 *
 * Data layer (manual fetches + state) will be migrated to React Query in W3.1.
 */
const App = () => {
  const [token, setToken] = useState(localStorage.getItem('authToken'));
  const [allJobs, setAllJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const [, setIsConnected] = useState(false);
  const wsRef = useRef(null);
  const jobCache = useRef({});
  const selectedJobRef = useRef(null);

  const [replicas, setReplicas] = useState({});
  const [capacity, setCapacity] = useState(null);
  const [failedCallbackCount, setFailedCallbackCount] = useState(0);

  const navigate = useNavigate();
  const location = useLocation();

  const handleLogin = (newToken) => {
    localStorage.setItem('authToken', newToken);
    setToken(newToken);
    navigate('/', { replace: true });
  };

  const handleLogout = useCallback(() => {
    localStorage.removeItem('authToken');
    setToken(null);
    setSelectedJob(null);
    jobCache.current = {};
    navigate('/', { replace: true });
  }, [navigate]);

  // Centralized 401 handler — called by lib/api when any request returns 401.
  useEffect(() => {
    setOnUnauthorized(handleLogout);
    return () => setOnUnauthorized(null);
  }, [handleLogout]);

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get('/jobs', token);
      setAllJobs(data);
    } catch (error) {
      console.error('Error fetching jobs:', error);
    } finally {
      setLoading(false);
    }
  }, [token]);

  const fetchCapacity = useCallback(async () => {
    try {
      const data = await api.get('/capacity', token);
      setCapacity(data);
    } catch (error) {
      console.error('Error fetching capacity:', error);
    }
  }, [token]);

  const fetchCallbacks = useCallback(async () => {
    try {
      const data = await api.get('/callbacks', token);
      setFailedCallbackCount(data.count);
    } catch (error) {
      console.error('Error fetching callbacks:', error);
    }
  }, [token]);

  const fetchJobDetails = useCallback(async (id) => {
    if (jobCache.current[id] && selectedJobRef.current?.id === id && !showRaw) {
      // Already loaded — no-op (avoids redundant fetch when navigating back to same job)
      if (selectedJob?.id !== id) setSelectedJob(jobCache.current[id]);
      return;
    }

    setShowRaw(false);
    setLoadingDetails(true);
    try {
      const data = await api.get(`/jobs/${id}/details`, token);
      jobCache.current[id] = data;
      setSelectedJob(data);
    } catch (error) {
      console.error('Error fetching job details:', error);
      setSelectedJob({ id, error: error.message });
    } finally {
      setLoadingDetails(false);
    }
  }, [token, showRaw, selectedJob]);

  const clearSelectedJob = useCallback(() => {
    setSelectedJob(null);
    setShowRaw(false);
  }, []);

  useEffect(() => {
    if (token) {
      fetchJobs();
      fetchCapacity();
      fetchCallbacks();
    }
  }, [token, fetchJobs, fetchCapacity, fetchCallbacks]);

  // Keep ref in sync for WebSocket handler (avoids stale closure)
  useEffect(() => { selectedJobRef.current = selectedJob; }, [selectedJob]);

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
          fetchJobs();
          fetchCapacity();
          fetchCallbacks();
          if (data.crawl_id && selectedJobRef.current?.id === data.crawl_id) {
            fetchJobDetails(data.crawl_id);
          }
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
  }, [token, fetchJobs, fetchCapacity, fetchCallbacks, fetchJobDetails]);

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

  const overviewProps = {
    token,
    allJobs,
    loading,
    capacity,
    replicas,
    selectedJob,
    loadingDetails,
    showRaw,
    setShowRaw,
    fetchJobDetails,
    clearSelectedJob,
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
              to="/audit"
              className="p-2 rounded-md hover:bg-gray-700 transition-colors text-gray-400 hover:text-white"
              title="Audit log"
            >
              <FileText className="w-5 h-5" />
            </Link>
            <button onClick={fetchJobs} className="p-2 rounded-md hover:bg-gray-700 transition-colors" title="Rafraîchir">
              <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button onClick={handleLogout} className="p-2 rounded-md hover:bg-red-700 transition-colors text-red-400 hover:text-white" title="Déconnexion">
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </div>
      </header>

      <Routes>
        <Route path="/" element={<Overview {...overviewProps} />} />
        <Route path="/jobs/:id" element={<Overview {...overviewProps} />}>
          <Route path="queue" element={<QueuePage token={token} />} />
          <Route path="dataset" element={<DatasetPage token={token} />} />
        </Route>
        <Route path="/callbacks" element={<CallbacksPage token={token} onClose={fetchCallbacks} />} />
        <Route path="/audit" element={<AuditPage token={token} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}

export default App;