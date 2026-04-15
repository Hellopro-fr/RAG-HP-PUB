import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import {
  Activity, AlertCircle, RefreshCw, LogOut, Server, CheckCircle, XCircle,
  Zap, Archive, Search, Filter, Calendar, ChevronLeft, ChevronRight, TrendingUp
} from 'lucide-react';
import { API_URL, JOBS_PER_PAGE } from './lib/constants';
import LoginPage from './components/LoginPage';
import StatCard from './components/StatCard';
import ReplicaMonitor from './components/ReplicaMonitor';
import JobCard from './components/JobCard';
import JobDetails from './components/JobDetails';

const App = () => {
  const [token, setToken] = useState(localStorage.getItem('authToken'));
  const [allJobs, setAllJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef(null);
  const jobCache = useRef({});
  const selectedJobRef = useRef(null);

  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [replicas, setReplicas] = useState({});
  const [capacity, setCapacity] = useState(null);
  const [failedCallbackCount, setFailedCallbackCount] = useState(0);

  const filteredJobs = useMemo(() => {
    return allJobs.filter(job => {
      const jobDate = new Date(job.start_time);
      const start = startDate ? new Date(startDate) : null;
      const end = endDate ? new Date(endDate) : null;

      if (start && jobDate < start) return false;
      if (end) {
        const endOfDay = new Date(end);
        endOfDay.setHours(23, 59, 59, 999);
        if (jobDate > endOfDay) return false;
      }

      const matchesStatus = statusFilter === 'all' || job.status === statusFilter;
      const matchesSearch = searchTerm === '' ||
        job.id.includes(searchTerm) ||
        (job.domain && job.domain.toLowerCase().includes(searchTerm.toLowerCase()));

      return matchesStatus && matchesSearch;
    }).sort((a, b) => new Date(b.start_time) - new Date(a.start_time));
  }, [allJobs, searchTerm, statusFilter, startDate, endDate]);

  const paginatedJobs = useMemo(() => {
    const startIndex = (currentPage - 1) * JOBS_PER_PAGE;
    return filteredJobs.slice(startIndex, startIndex + JOBS_PER_PAGE);
  }, [filteredJobs, currentPage]);

  const totalPages = Math.ceil(filteredJobs.length / JOBS_PER_PAGE);

  const globalStats = useMemo(() => {
    const finished = filteredJobs.filter(j => j.status === 'finished').length;
    const failed = filteredJobs.filter(j => j.status === 'failed').length;
    const running = filteredJobs.filter(j => j.status === 'running').length;
    const archived = filteredJobs.filter(j => j.status === 'archived').length;
    return { finished, failed, running, archived, total: filteredJobs.length };
  }, [filteredJobs]);

  const handleLogin = (newToken) => {
    localStorage.setItem('authToken', newToken);
    setToken(newToken);
  };

  const handleLogout = () => {
    localStorage.removeItem('authToken');
    setToken(null);
  };

  const authFetch = async (url, options = {}) => {
    const headers = {
      ...options.headers,
      'Authorization': `Bearer ${token}`,
    };
    const res = await fetch(url, { ...options, headers });
    if (res.status === 401) {
      handleLogout();
      throw new Error('Unauthorized');
    }
    return res;
  };

  useEffect(() => {
    if (token) {
      fetchJobs();
      fetchCapacity();
      fetchCallbacks();
    }
  }, [token]);

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
  }, [token]);

  // Clean up zombie replicas (older than 30s)
  useEffect(() => {
    const interval = setInterval(() => {
      setReplicas(prev => {
        const now = Date.now();
        const next = {};
        let changed = false;
        Object.entries(prev).forEach(([id, data]) => {
          // Keep if heartbeat is recent (< 30s)
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

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    try {
      const response = await authFetch(`${API_URL}/jobs`);
      const data = await response.json();
      setAllJobs(data);
    } catch (error) {
      console.error('Error fetching jobs:', error);
    } finally {
      setLoading(false);
    }
  }, [token]);

  const fetchCapacity = useCallback(async () => {
    try {
      const response = await authFetch(`${API_URL}/capacity`);
      const data = await response.json();
      setCapacity(data);
    } catch (error) {
      console.error('Error fetching capacity:', error);
    }
  }, [token]);

  const fetchCallbacks = useCallback(async () => {
    try {
      const response = await authFetch(`${API_URL}/callbacks`);
      const data = await response.json();
      setFailedCallbackCount(data.count);
    } catch (error) {
      console.error('Error fetching callbacks:', error);
    }
  }, [token]);

  const fetchJobDetails = useCallback(async (id) => {
    if (jobCache.current[id] && selectedJob?.id === id && !showRaw) {
      return;
    }

    setShowRaw(false);
    setLoadingDetails(true);

    try {
      const response = await authFetch(`${API_URL}/jobs/${id}/details`);
      if (!response.ok) throw new Error(`HTTP error ${response.status}`);
      const data = await response.json();

      jobCache.current[id] = data;
      setSelectedJob(data);
    } catch (error) {
      console.error('Error fetching job details:', error);
      setSelectedJob({ id, error: error.message });
    } finally {
      setLoadingDetails(false);
    }
  }, [selectedJob, showRaw]);

  if (!token) {
    return <LoginPage onLogin={handleLogin} />;
  }

  return (
    <div className="min-h-screen bg-gray-900 text-gray-300 font-sans">
      <header className="bg-gray-800/80 backdrop-blur-sm border-b border-gray-700 sticky top-0 z-20">
        <div className="container mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Activity className="w-8 h-8 text-blue-400" />
            <h1 className="text-xl font-bold text-white">Crawler Dashboard Pro</h1>
          </div>
          <div className="flex gap-2">
            {failedCallbackCount > 0 && (
              <div className="flex items-center gap-2 px-3 py-1 bg-red-900/50 border border-red-500/30 rounded-lg text-sm">
                <AlertCircle className="w-4 h-4 text-red-400" />
                <span className="text-red-300">{failedCallbackCount} callback{failedCallbackCount > 1 ? 's' : ''} en échec</span>
              </div>
            )}
            <button onClick={fetchJobs} className="p-2 rounded-md hover:bg-gray-700 transition-colors" title="Rafraîchir">
              <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button onClick={handleLogout} className="p-2 rounded-md hover:bg-red-700 transition-colors text-red-400 hover:text-white" title="Déconnexion">
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </div>
      </header>

      <main className="container mx-auto p-4 space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <StatCard title="Total" value={globalStats.total} icon={Server} color="gray" />
          <StatCard title="Succès" value={globalStats.finished} icon={CheckCircle} color="green" />
          <StatCard title="Échecs" value={globalStats.failed} icon={XCircle} color="red" />
          <StatCard title="En cours" value={globalStats.running} icon={Zap} color="blue" />
          <StatCard title="Archivés" value={globalStats.archived} icon={Archive} color="gray" />
        </div>

        {capacity && capacity.max_global_jobs > 0 && (
          <div className="bg-gray-800 rounded-lg p-4 shadow-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-semibold text-gray-400">
                Capacité globale
              </span>
              <span className={`text-sm font-bold ${capacity.is_full ? 'text-red-400' : 'text-green-400'}`}>
                {capacity.running_jobs} / {capacity.max_global_jobs} slots
              </span>
            </div>
            <div className="h-3 bg-gray-700 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  capacity.is_full ? 'bg-red-500' : capacity.running_jobs / capacity.max_global_jobs > 0.8 ? 'bg-yellow-500' : 'bg-green-500'
                }`}
                style={{ width: `${Math.min((capacity.running_jobs / capacity.max_global_jobs) * 100, 100)}%` }}
              />
            </div>
          </div>
        )}

        {/* Replica Monitor */}
        <ReplicaMonitor replicas={replicas} />

        <div className="bg-gray-800 p-3 rounded-lg space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative flex-grow min-w-[200px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
              <input
                type="text"
                placeholder="Filtrer par ID ou domaine..."
                value={searchTerm}
                onChange={e => {
                  setSearchTerm(e.target.value);
                  setCurrentPage(1);
                }}
                className="w-full bg-gray-900 border border-gray-700 rounded-md pl-10 pr-4 py-2 focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
            </div>
            <div className="relative">
              <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
              <select
                value={statusFilter}
                onChange={e => {
                  setStatusFilter(e.target.value);
                  setCurrentPage(1);
                }}
                className="bg-gray-900 border border-gray-700 rounded-md pl-10 pr-4 py-2 appearance-none focus:ring-2 focus:ring-blue-500 focus:outline-none"
              >
                <option value="all">Tous les statuts</option>
                <option value="finished">Succès</option>
                <option value="failed">Échec</option>
                <option value="running">En cours</option>
                <option value="stopping">Arrêt...</option>
                <option value="archived">Archivé</option>
                <option value="restarting_oom">Restart OOM</option>
              </select>
            </div>
            <div className="flex items-center gap-2">
              <Calendar className="w-5 h-5 text-gray-500" />
              <input
                type="date"
                value={startDate}
                onChange={e => {
                  setStartDate(e.target.value);
                  setCurrentPage(1);
                }}
                className="bg-gray-900 border border-gray-700 rounded-md px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:outline-none text-sm"
              />
              <span className="text-gray-500">à</span>
              <input
                type="date"
                value={endDate}
                onChange={e => {
                  setEndDate(e.target.value);
                  setCurrentPage(1);
                }}
                className="bg-gray-900 border border-gray-700 rounded-md px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:outline-none text-sm"
              />
              {(startDate || endDate) && (
                <button
                  onClick={() => {
                    setStartDate('');
                    setEndDate('');
                    setCurrentPage(1);
                  }}
                  className="px-3 py-2 bg-red-600 hover:bg-red-700 rounded-md text-sm text-white transition-colors"
                >
                  ✕
                </button>
              )}
            </div>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between text-sm text-gray-400 pt-2 border-t border-gray-700">
              <span>{filteredJobs.length} jobs trouvés</span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>

                <div className="flex items-center gap-2">
                  <span className="hidden sm:inline">Page</span>
                  <input
                    type="number"
                    min="1"
                    max={totalPages}
                    value={currentPage}
                    onChange={(e) => {
                      const val = parseInt(e.target.value);
                      if (!isNaN(val) && val >= 1 && val <= totalPages) {
                        setCurrentPage(val);
                      }
                    }}
                    className="w-16 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-center focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  />
                  <span className="text-gray-500">/ {totalPages}</span>
                </div>

                <button
                  onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="flex gap-4 items-start">
          <div className="w-1/3 space-y-3 max-h-[calc(100vh-20rem)] overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <RefreshCw className="w-8 h-8 animate-spin text-blue-400" />
              </div>
            ) : paginatedJobs.length === 0 ? (
              <div className="text-center py-12 text-gray-400">
                <Server className="w-12 h-12 mx-auto mb-4 opacity-50" />
                <p>Aucun job trouvé</p>
              </div>
            ) : (
              paginatedJobs.map(job => (
                <JobCard
                  key={job.id}
                  job={job}
                  onClick={() => fetchJobDetails(job.id)}
                  isSelected={selectedJob?.id === job.id}
                />
              ))
            )}
          </div>

          <div className="flex-1 bg-gray-800 rounded-lg p-6">
            {loadingDetails ? (
              <div className="flex items-center justify-center py-20">
                <RefreshCw className="w-12 h-12 animate-spin text-blue-400" />
              </div>
            ) : selectedJob ? (
              <JobDetails
                job={selectedJob}
                onToggleRaw={() => setShowRaw(!showRaw)}
                showRaw={showRaw}
                token={token}
                onSelectJob={fetchJobDetails}
              />
            ) : (
              <div className="text-center py-20 text-gray-400">
                <TrendingUp className="w-16 h-16 mx-auto mb-4 opacity-50" />
                <p className="text-lg">Sélectionnez un job pour voir les détails</p>
                <p className="text-sm mt-2">Cliquez sur un job dans la liste de gauche</p>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
