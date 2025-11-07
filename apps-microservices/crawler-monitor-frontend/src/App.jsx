import React, { useState, useEffect, useRef } from 'react';
import { Activity, CheckCircle, XCircle, Clock, AlertTriangle, RefreshCw, Eye, Code } from 'lucide-react';

const API_URL = '/api';

function App() {
  const [jobs, setJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const wsRef = useRef(null);

  const fetchJobs = async () => {
    try {
      const response = await fetch(`${API_URL}/jobs`);
      const data = await response.json();
      setJobs(data);
      if (!selectedJob && data.length > 0) {
        // Automatically select the first job if none is selected
        // fetchJobDetails(data[0].id);
      }
    } catch (error) {
      console.error('Error fetching jobs:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchJobDetails = async (id) => {
    // Dans cette architecture, les détails viennent de l'appel /api/jobs
    const jobDetail = jobs.find(j => j.id === id);
    setSelectedJob(jobDetail || null);
  };

  useEffect(() => {
    fetchJobs();

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api`;
    
    wsRef.current = new WebSocket(wsUrl);
    
    wsRef.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'file_changed') { // We kept the same message type for simplicity
        fetchJobs();
        // If a job is selected and it's the one that was updated, refresh its details
        if (selectedJob && data.path.includes(selectedJob.id)) {
           // Refetching jobs will update the details in the list
        }
      }
    };

    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, [selectedJob]); // Re-run effect if selectedJob changes

  const formatDuration = (ms) => {
    if (!ms) return 'N/A';
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  };

  const formatDate = (dateStr) => {
    return new Date(dateStr).toLocaleString('fr-FR');
  };

  const getStatusBadge = (job) => {
    if (!job.stats) {
      return { color: 'gray', text: 'En cours', icon: Clock };
    }
    if (job.stats.requestsFailed > 0 && job.stats.requestsFinished === 0) {
      return { color: 'red', text: 'Échec', icon: XCircle };
    }
    if (job.stats.requestsFailed > 0) {
      return { color: 'yellow', text: 'Partiel', icon: AlertTriangle };
    }
    return { color: 'green', text: 'Succès', icon: CheckCircle };
  };

  const JobCard = ({ job }) => {
    const status = getStatusBadge(job);
    const StatusIcon = status.icon;

    return (
      <div
        onClick={() => fetchJobDetails(job.id)}
        className={`bg-gray-800 rounded-lg p-4 cursor-pointer hover:bg-gray-700 border-l-4 transition-all ${
          selectedJob?.id === job.id ? 'border-blue-500 bg-gray-700' : `border-${status.color}-500`
        }`}
      >
        <div className="flex items-start justify-between mb-2">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-white font-semibold">Job #{job.id}</span>
              <span className={`px-2 py-0.5 rounded text-xs font-medium bg-${status.color}-500/20 text-${status.color}-400`}>
                {status.text}
              </span>
            </div>
            {job.domain && (
              <p className="text-gray-400 text-sm truncate">{job.domain}</p>
            )}
          </div>
          <StatusIcon className={`w-5 h-5 text-${status.color}-400`} />
        </div>
        
        {job.stats && (
          <div className="grid grid-cols-3 gap-2 mt-3 text-xs">
            <div>
              <p className="text-gray-500">Total</p>
              <p className="text-white font-semibold">{job.stats.requestsTotal}</p>
            </div>
            <div>
              <p className="text-gray-500">Succès</p>
              <p className="text-green-400 font-semibold">{job.stats.requestsFinished}</p>
            </div>
            <div>
              <p className="text-gray-500">Échecs</p>
              <p className="text-red-400 font-semibold">{job.stats.requestsFailed}</p>
            </div>
          </div>
        )}
        
        <div className="mt-3 text-xs text-gray-500">
          {formatDate(job.lastModified)}
        </div>
      </div>
    );
  };

  const JobDetails = ({ job }) => {
    if (!job) return null;

    const renderContent = () => {
      if (!job.stats) {
        return (
          <div className="text-center py-12 text-gray-400">
            <Clock className="w-12 h-12 mx-auto mb-4 animate-spin" />
            <p>Job en cours d'exécution ou log incomplet...</p>
          </div>
        );
      }

      const successRate = job.stats.requestsTotal > 0
        ? ((job.stats.requestsFinished / job.stats.requestsTotal) * 100).toFixed(1)
        : 0;

      if (showRaw) {
        return (
          <div className="bg-gray-900 rounded-lg p-4 overflow-auto max-h-[calc(100vh-200px)]">
            <pre className="text-xs text-gray-300 font-mono">{job.rawContent}</pre>
          </div>
        );
      }
      
      return (
        <>
          {/* Stats Grid */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-gray-800 rounded-lg p-4">
              <Activity className="w-5 h-5 text-blue-400 mb-2" />
              <p className="text-2xl font-bold text-white">{job.stats.requestsTotal}</p>
              <p className="text-gray-400 text-sm">Total</p>
            </div>
            <div className="bg-gray-800 rounded-lg p-4">
              <CheckCircle className="w-5 h-5 text-green-400 mb-2" />
              <p className="text-2xl font-bold text-green-400">{job.stats.requestsFinished}</p>
              <p className="text-gray-400 text-sm">Succès</p>
            </div>
            <div className="bg-gray-800 rounded-lg p-4">
              <XCircle className="w-5 h-5 text-red-400 mb-2" />
              <p className="text-2xl font-bold text-red-400">{job.stats.requestsFailed}</p>
              <p className="text-gray-400 text-sm">Échecs</p>
            </div>
            <div className="bg-gray-800 rounded-lg p-4">
              <Clock className="w-5 h-5 text-purple-400 mb-2" />
              <p className="text-2xl font-bold text-white">
                {formatDuration(job.stats.crawlerRuntimeMillis)}
              </p>
              <p className="text-gray-400 text-sm">Durée</p>
            </div>
          </div>

          {/* Success Rate */}
          <div className="bg-gray-800 rounded-lg p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-white font-semibold">Taux de réussite</span>
              <span className="text-2xl font-bold text-blue-400">{successRate}%</span>
            </div>
            <div className="w-full bg-gray-700 rounded-full h-3">
              <div
                className={`h-3 rounded-full transition-all ${
                  successRate > 80 ? 'bg-green-500' : successRate > 50 ? 'bg-yellow-500' : 'bg-red-500'
                }`}
                style={{ width: `${successRate}%` }}
              />
            </div>
          </div>

          {/* Timeline & HTTP Codes */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-gray-800 rounded-lg p-4">
              <h3 className="text-white font-semibold mb-3">Timeline</h3>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Début</span>
                  <span className="text-white">{formatDate(job.stats.crawlerStartedAt)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Fin</span>
                  <span className="text-white">{formatDate(job.stats.crawlerFinishedAt)}</span>
                </div>
              </div>
            </div>

            {job.stats.requestsWithStatusCode && (
              <div className="bg-gray-800 rounded-lg p-4">
                <h3 className="text-white font-semibold mb-3">Codes HTTP</h3>
                <div className="flex gap-3 flex-wrap">
                  {Object.entries(job.stats.requestsWithStatusCode).map(([code, count]) => (
                    <div
                      key={code}
                      className={`px-3 py-1 rounded-lg text-center ${
                        code.startsWith('2')
                          ? 'bg-green-500/20 text-green-400'
                          : code.startsWith('4')
                          ? 'bg-red-500/20 text-red-400'
                          : 'bg-yellow-500/20 text-yellow-400'
                      }`}
                    >
                      <p className="font-bold">{code}</p>
                      <p className="text-xs opacity-75">{count}x</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Errors */}
          {job.errors && job.errors.length > 0 && (
            <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <AlertCircle className="w-5 h-5 text-red-400" />
                <h3 className="text-red-400 font-semibold">Erreurs ({job.errors.length})</h3>
              </div>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {job.errors.map((error, idx) => (
                  <div key={idx} className="bg-gray-900/50 rounded p-3 text-sm text-red-300 font-mono">
                    {error}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Warnings */}
          {job.warnings && job.warnings.length > 0 && (
            <div className="bg-yellow-900/20 border border-yellow-500/30 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <AlertTriangle className="w-5 h-5 text-yellow-400" />
                <h3 className="text-yellow-400 font-semibold">Avertissements ({job.warnings.length})</h3>
              </div>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {job.warnings.slice(0, 10).map((warning, idx) => (
                  <div key={idx} className="bg-gray-900/50 rounded p-3 text-sm text-yellow-300 font-mono">
                    {warning}
                  </div>
                ))}
                {job.warnings.length > 10 && (
                  <p className="text-gray-500 text-sm mt-2">
                    ... et {job.warnings.length - 10} autres avertissements
                  </p>
                )}
              </div>
            </div>
          )}
        </>
      );
    }

    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-white">Job #{job.id}</h2>
            {job.site && <p className="text-gray-400 mt-1 truncate">{job.site}</p>}
          </div>
          <button
            onClick={() => setShowRaw(!showRaw)}
            className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors text-white"
          >
            <Code className="w-4 h-4" />
            {showRaw ? 'Vue détaillée' : 'Logs bruts'}
          </button>
        </div>
        {renderContent()}
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-gray-900 text-gray-300">
      <header className="bg-gray-800 border-b border-gray-700 sticky top-0 z-10">
        <div className="px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Activity className="w-8 h-8 text-blue-400" />
              <div>
                <h1 className="text-2xl font-bold text-white">Crawlee Monitor</h1>
                <p className="text-gray-400 text-sm">Surveillance en temps réel</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <button
                onClick={() => setAutoRefresh(!autoRefresh)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
                  autoRefresh
                    ? 'bg-blue-600 hover:bg-blue-700 text-white'
                    : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
                }`}
              >
                <RefreshCw className={`w-4 h-4 ${autoRefresh ? 'animate-spin' : ''}`} />
                Auto-refresh
              </button>
              <button
                onClick={fetchJobs}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
              >
                Actualiser
              </button>
            </div>
          </div>
        </div>
      </header>

      <div className="flex h-[calc(100vh-81px)]">
        <aside className="w-96 bg-gray-800 border-r border-gray-700 overflow-y-auto">
          <div className="p-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-white font-semibold">Jobs ({jobs.length})</h2>
              <span className="text-gray-400 text-sm">
                {jobs.filter(j => j.stats).length} terminés
              </span>
            </div>
            {loading ? (
              <div className="text-center py-8">
                <RefreshCw className="w-8 h-8 text-gray-500 animate-spin mx-auto mb-2" />
                <p className="text-gray-500">Chargement...</p>
              </div>
            ) : jobs.length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                <Eye className="w-12 h-12 mx-auto mb-2 opacity-50" />
                <p>Aucun job détecté</p>
              </div>
            ) : (
              <div className="space-y-3">
                {jobs.map(job => (
                  <JobCard key={job.id} job={job} />
                ))}
              </div>
            )}
          </div>
        </aside>

        <main className="flex-1 overflow-y-auto">
          <div className="p-6">
            {selectedJob ? (
              <JobDetails job={selectedJob} />
            ) : (
              <div className="flex items-center justify-center h-full">
                <div className="text-center text-gray-500">
                  <Eye className="w-16 h-16 mx-auto mb-4 opacity-50" />
                  <p className="text-lg">Sélectionnez un job pour voir les détails</p>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
export default App;
