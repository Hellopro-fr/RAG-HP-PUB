import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import {
  Activity, CheckCircle, XCircle, Clock, AlertTriangle, RefreshCw, Code,
  Search, Calendar, Filter, Server, Download, ChevronLeft, ChevronRight,
  AlertCircle, Info, Zap, ExternalLink, TrendingUp, LogOut, AlignLeft, Cpu, Trash2,
  Archive, RotateCcw
} from 'lucide-react';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';

const API_URL = '/api';
const JOBS_PER_PAGE = 20;

const StatCard = ({ title, value, icon: Icon, color, trend }) => (
  <div className="bg-gray-800 p-4 rounded-lg flex items-center gap-4 shadow-lg hover:bg-gray-750 transition-all">
    <div className={`w-12 h-12 flex items-center justify-center rounded-lg bg-${color}-500/20`}>
      <Icon className={`w-6 h-6 text-${color}-400`} />
    </div>
    <div className="flex-1">
      <p className="text-2xl font-bold text-white">{value}</p>
      <p className="text-sm text-gray-400">{title}</p>
      {trend && (
        <p className={`text-xs mt-1 ${trend > 0 ? 'text-green-400' : 'text-red-400'}`}>
          {trend > 0 ? '↑' : '↓'} {Math.abs(trend)}%
        </p>
      )}
    </div>
  </div>
);

const JobCard = ({ job, onClick, isSelected }) => {
  const getStatusInfo = (job) => {
    const status = job.status || 'pending';
    switch (status.toLowerCase()) {
      case 'running': return { color: 'blue', text: 'En cours', icon: RefreshCw, spin: true };
      case 'finished': return { color: 'green', text: 'Succès', icon: CheckCircle };
      case 'failed': return { color: 'red', text: 'Échec', icon: XCircle };
      case 'stopping': return { color: 'yellow', text: 'Arrêt...', icon: AlertTriangle };
      case 'archived': return { color: 'gray', text: 'Archivé', icon: Archive };
      case 'restarting_oom': return { color: 'orange', text: 'Restart OOM', icon: RotateCcw, spin: true };
      default: return { color: 'gray', text: status, icon: Clock };
    }
  };

  const status = getStatusInfo(job);
  const StatusIcon = status.icon;

  return (
    <div
      onClick={onClick}
      className={`bg-gray-800 rounded-lg p-4 cursor-pointer hover:bg-gray-700 border-l-4 transition-all ${isSelected ? 'border-blue-500 bg-gray-700 shadow-lg' : `border-${status.color}-500`
        }`}
    >
      <div className="flex justify-between items-start">
        <div className="min-w-0 flex-1">
          <p className="text-white font-semibold truncate">Job #{job.id}</p>
          <p className="text-gray-400 text-sm truncate">{job.domain}</p>
        </div>
        <div className="flex-shrink-0 flex items-center gap-2">
          <span className={`px-2 py-0.5 rounded text-xs font-medium bg-${status.color}-500/20 text-${status.color}-400`}>
            {status.text}
          </span>
          <StatusIcon className={`w-5 h-5 text-${status.color}-400 ${status.spin ? 'animate-spin' : ''}`} />
        </div>
      </div>
      <p className="mt-3 text-xs text-gray-500">{new Date(job.start_time).toLocaleString('fr-FR')}</p>
    </div>
  );
};

const AdvancedLogViewer = ({ content, jobId }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [levelFilter, setLevelFilter] = useState('all');
  const [currentPage, setCurrentPage] = useState(1);
  const [linesPerPage] = useState(100);

  const parsedLines = useMemo(() => {
    return content.split('\n').map((line, index) => {
      const lowerLine = line.toLowerCase();
      let level = 'info';
      if (lowerLine.includes('error')) level = 'error';
      else if (lowerLine.includes('warn')) level = 'warn';

      const urlMatch = line.match(/(https?:\/\/[^\s]+)/);
      const url = urlMatch ? urlMatch[1] : null;

      const timestampMatch = line.match(/(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2})/);
      const timestamp = timestampMatch ? timestampMatch[1] : null;

      return { line, level, url, timestamp, index };
    });
  }, [content]);

  const filteredLines = useMemo(() => {
    return parsedLines.filter(({ line, level }) => {
      const matchesSearch = !searchTerm || line.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesLevel = levelFilter === 'all' || level === levelFilter;
      return matchesSearch && matchesLevel;
    });
  }, [parsedLines, searchTerm, levelFilter]);

  const paginatedLines = useMemo(() => {
    const startIndex = (currentPage - 1) * linesPerPage;
    return filteredLines.slice(startIndex, startIndex + linesPerPage);
  }, [filteredLines, currentPage, linesPerPage]);

  const totalPages = Math.ceil(filteredLines.length / linesPerPage);

  const levelStats = useMemo(() => {
    const stats = { error: 0, warn: 0, info: 0 };
    parsedLines.forEach(({ level }) => stats[level]++);
    return stats;
  }, [parsedLines]);

  const highlightLog = (level) => {
    switch (level) {
      case 'error': return 'text-red-400 bg-red-900/20';
      case 'warn': return 'text-yellow-400 bg-yellow-900/20';
      default: return 'text-gray-300';
    }
  };

  const highlightSearchTerm = (text) => {
    if (!searchTerm) return text;
    const parts = text.split(new RegExp(`(${searchTerm})`, 'gi'));
    return parts.map((part, i) =>
      part.toLowerCase() === searchTerm.toLowerCase()
        ? <span key={i} className="bg-yellow-500 text-black font-bold">{part}</span>
        : part
    );
  };

  const downloadLogs = (format) => {
    let data, filename, type;

    if (format === 'txt') {
      data = filteredLines.map(l => l.line).join('\n');
      filename = `job-${jobId}-logs.txt`;
      type = 'text/plain';
    } else if (format === 'json') {
      data = JSON.stringify(filteredLines, null, 2);
      filename = `job-${jobId}-logs.json`;
      type = 'application/json';
    } else if (format === 'csv') {
      data = 'Index,Level,Line,URL,Timestamp\n' +
        filteredLines.map(l =>
          `${l.index},"${l.level}","${l.line.replace(/"/g, '""')}","${l.url || ''}","${l.timestamp || ''}"`
        ).join('\n');
      filename = `job-${jobId}-logs.csv`;
      type = 'text/csv';
    }

    const blob = new Blob([data], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-3 flex items-center gap-3">
          <XCircle className="w-8 h-8 text-red-400" />
          <div>
            <p className="text-2xl font-bold text-red-400">{levelStats.error}</p>
            <p className="text-sm text-gray-400">Erreurs</p>
          </div>
        </div>
        <div className="bg-yellow-900/20 border border-yellow-500/30 rounded-lg p-3 flex items-center gap-3">
          <AlertTriangle className="w-8 h-8 text-yellow-400" />
          <div>
            <p className="text-2xl font-bold text-yellow-400">{levelStats.warn}</p>
            <p className="text-sm text-gray-400">Avertissements</p>
          </div>
        </div>
        <div className="bg-blue-900/20 border border-blue-500/30 rounded-lg p-3 flex items-center gap-3">
          <Info className="w-8 h-8 text-blue-400" />
          <div>
            <p className="text-2xl font-bold text-blue-400">{levelStats.info}</p>
            <p className="text-sm text-gray-400">Info</p>
          </div>
        </div>
      </div>

      <div className="bg-gray-800 p-4 rounded-lg space-y-3">
        <div className="flex gap-3 flex-wrap">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              type="text"
              placeholder="Rechercher dans les logs..."
              value={searchTerm}
              onChange={e => {
                setSearchTerm(e.target.value);
                setCurrentPage(1);
              }}
              className="w-full bg-gray-900 border border-gray-700 rounded-md pl-10 pr-4 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
          </div>

          <select
            value={levelFilter}
            onChange={e => {
              setLevelFilter(e.target.value);
              setCurrentPage(1);
            }}
            className="bg-gray-900 border border-gray-700 rounded-md px-4 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
          >
            <option value="all">Tous les niveaux</option>
            <option value="error">Erreurs</option>
            <option value="warn">Avertissements</option>
            <option value="info">Info</option>
          </select>

          <div className="flex gap-2">
            <button
              onClick={() => downloadLogs('txt')}
              className="flex items-center gap-2 px-3 py-2 bg-blue-600 hover:bg-blue-700 rounded-md text-sm transition-colors"
            >
              <Download className="w-4 h-4" />
              TXT
            </button>
            <button
              onClick={() => downloadLogs('json')}
              className="flex items-center gap-2 px-3 py-2 bg-green-600 hover:bg-green-700 rounded-md text-sm transition-colors"
            >
              <Download className="w-4 h-4" />
              JSON
            </button>
            <button
              onClick={() => downloadLogs('csv')}
              className="flex items-center gap-2 px-3 py-2 bg-purple-600 hover:bg-purple-700 rounded-md text-sm transition-colors"
            >
              <Download className="w-4 h-4" />
              CSV
            </button>
          </div>
        </div>

        <div className="flex items-center justify-between text-sm text-gray-400">
          <span>{filteredLines.length} lignes trouvées</span>
          {totalPages > 1 && (
            <div className="flex items-center gap-2">
              <button
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="p-1 hover:bg-gray-700 rounded disabled:opacity-50 disabled:cursor-not-allowed"
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
                  className="w-12 bg-gray-900 border border-gray-700 rounded px-1 py-0.5 text-center text-xs focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
                <span className="text-xs text-gray-400">/ {totalPages}</span>
              </div>

              <button
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="p-1 hover:bg-gray-700 rounded disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="bg-gray-900 rounded-lg font-mono text-xs max-h-[60vh] overflow-auto">
        <div className="p-4">
          {paginatedLines.map(({ line, level, url, timestamp, index }) => (
            <div
              key={index}
              className={`flex gap-4 items-start py-1 hover:bg-gray-800/50 ${highlightLog(level)} px-2 rounded`}
            >
              <span className="text-gray-600 select-none w-12 text-right flex-shrink-0">
                {index + 1}
              </span>
              <span className="flex-1 whitespace-pre-wrap break-all">
                {highlightSearchTerm(line)}
              </span>
              {url && (
                <a
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex-shrink-0 text-blue-400 hover:text-blue-300"
                  title="Ouvrir l'URL"
                >
                  <ExternalLink className="w-4 h-4" />
                </a>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

const ErrorVisualization = ({ errors, warnings }) => {
  const errorTypes = useMemo(() => {
    const types = {};
    errors.forEach(err => {
      const type = err.split(':')[0] || 'Unknown';
      types[type] = (types[type] || 0) + 1;
    });
    return Object.entries(types).map(([name, value]) => ({ name, value }));
  }, [errors]);

  const COLORS = ['#ef4444', '#f97316', '#f59e0b', '#eab308', '#84cc16'];

  return (
    <div className="bg-gray-800 p-4 rounded-lg">
      <h3 className="text-lg font-semibold text-white mb-4">Distribution des Erreurs</h3>
      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Pie
            data={errorTypes}
            cx="50%"
            cy="50%"
            labelLine={false}
            label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
            outerRadius={80}
            fill="#8884d8"
            dataKey="value"
          >
            {errorTypes.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
};

const RequestQueueEditor = ({ jobId, onClose, token }) => {
  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [repairing, setRepairing] = useState(false);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');

  // Pagination State
  const [page, setPage] = useState(1);
  const [limit] = useState(50);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);

  const authFetch = async (url, options = {}) => {
    const headers = {
      ...options.headers,
      'Authorization': `Bearer ${token}`,
    };
    const res = await fetch(url, { ...options, headers });
    if (!res.ok) {
      if (res.status === 401) throw new Error('Unauthorized');
      throw new Error('Request failed');
    }
    return res;
  };

  useEffect(() => {
    fetchFiles();
  }, [jobId, page, searchTerm]); // Refetch on page or search change

  const fetchFiles = async () => {
    setLoading(true);
    try {
      const query = new URLSearchParams({
        page: page.toString(),
        limit: limit.toString(),
        search: searchTerm
      });

      const res = await authFetch(`${API_URL}/jobs/${jobId}/request-queues?${query}`);
      const data = await res.json();

      // Handle paginated response
      if (data.items) {
        setFiles(data.items);
        setTotalPages(data.totalPages);
        setTotalItems(data.total);
      } else {
        // Fallback for old API structure (array)
        setFiles(Array.isArray(data) ? data : []);
        setTotalPages(1);
        setTotalItems(Array.isArray(data) ? data.length : 0);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadFile = async (file) => {
    setLoading(true);
    setSelectedFile(file);
    setError(null);
    setSuccessMsg(null);
    try {
      const res = await authFetch(`${API_URL}/jobs/${jobId}/request-queues/${file.domain}/${file.name}`);
      const data = await res.json();
      setContent(JSON.stringify(data, null, 2));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const formatJson = () => {
    try {
      const parsed = JSON.parse(content);
      setContent(JSON.stringify(parsed, null, 2));
      setError(null);
    } catch (e) {
      setError('JSON Invalide: ' + e.message);
    }
  };

  const saveFile = async () => {
    if (!selectedFile) return;
    setSaving(true);
    setError(null);
    setSuccessMsg(null);
    try {
      // Validate JSON
      let jsonContent;
      try {
        jsonContent = JSON.parse(content);
      } catch (e) {
        throw new Error('JSON Invalide: ' + e.message);
      }

      await authFetch(`${API_URL}/jobs/${jobId}/request-queues/${selectedFile.domain}/${selectedFile.name}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(jsonContent)
      });

      setSuccessMsg('Fichier sauvegardé avec succès !');
      // Refresh list to update metadata if changed
      fetchFiles();
    } catch (err) {
      setError(`Erreur: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const [queueAnalysis, setQueueAnalysis] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);

  const analyzeQueue = async () => {
    setAnalyzing(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const res = await authFetch(`${API_URL}/jobs/${jobId}/request-queues/analyze`);
      const data = await res.json();
      setQueueAnalysis(data);
      setSuccessMsg(`Analyse terminée : ${data.total} URLs analysées`);
    } catch (err) {
      setError(`Erreur lors de l'analyse : ${err.message}`);
    } finally {
      setAnalyzing(false);
    }
  };

  const cleanPatterns = async () => {
    if (!window.confirm('Êtes-vous sûr de vouloir nettoyer les patterns ? Cela supprimera les URLs correspondant aux filtres (login, cart, facebook, etc.).')) {
      return;
    }

    setRepairing(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const res = await authFetch(`${API_URL}/jobs/${jobId}/request-queues/clean-patterns`, {
        method: 'POST'
      });
      const data = await res.json();
      setSuccessMsg(`Nettoyage patterns terminé : ${data.deleted} fichiers supprimés sur ${data.scanned} scannés.`);
      setQueueAnalysis(null); // Reset analysis after cleanup
      fetchFiles(); // Refresh list
    } catch (err) {
      setError(`Erreur lors du nettoyage patterns : ${err.message}`);
    } finally {
      setRepairing(false);
    }
  };

  const dropQueue = async () => {
    if (!window.confirm('☠️ DANGER : Êtes-vous sûr de vouloir TOUT SUPPRIMER ?\n\nCela va vider entièrement la queue de requêtes. Le crawler repartira de zéro (mais l\'historique des URLs déjà visitées est conservé).\n\nCette action est irréversible pour la queue actuelle.')) {
      return;
    }

    setRepairing(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const res = await authFetch(`${API_URL}/jobs/${jobId}/request-queues/drop`, {
        method: 'POST'
      });
      const data = await res.json();
      setSuccessMsg(`Queue entièrement vidée avec succès !`);
      fetchFiles(); // Refresh list - should be empty
      setQueueAnalysis(null); // Clear analysis
    } catch (err) {
      setError(`Erreur lors du "Drop" : ${err.message}`);
    } finally {
      setRepairing(false);
    }
  };

  // Search is now handled server-side via fetchFiles
  const handleSearchChange = (e) => {
    setSearchTerm(e.target.value);
    setPage(1); // Reset to first page on search
  };

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-800 rounded-lg shadow-xl w-full max-w-6xl h-[90vh] flex flex-col transition-all">
        <div className="flex justify-between items-center p-4 border-b border-gray-700">
          <h3 className="text-xl font-bold text-white flex items-center gap-2">
            <Code className="w-5 h-5" /> Éditeur Request Queue
          </h3>
          <div className="flex items-center gap-4">
            <button onClick={onClose} className="text-gray-400 hover:text-white">
              <XCircle className="w-6 h-6" />
            </button>
          </div>
        </div>

        <div className="flex-1 flex overflow-hidden">
          {/* Left Panel: Analysis, Actions, Search, File List, Pagination */}
          <div className="w-1/3 border-r border-gray-700 flex flex-col bg-gray-800">
            {/* Header & Tools */}
            <div className="p-3 bg-gray-900 border-b border-gray-700 space-y-3">
              <div className="flex justify-between items-center">
                <h4 className="text-sm font-semibold text-gray-400">Queue ({totalItems})</h4>
                <div className="flex gap-2">
                  {!queueAnalysis && (
                    <button
                      onClick={analyzeQueue}
                      disabled={analyzing}
                      className="px-2 py-1 bg-blue-600 hover:bg-blue-700 rounded text-xs text-white flex items-center gap-1"
                      title="Analyser la composition de la queue"
                    >
                      {analyzing ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Search className="w-3 h-3" />}
                      Analyser
                    </button>
                  )}
                </div>
              </div>

              {/* Analysis Results Widget */}
              {queueAnalysis && (
                <div className="bg-gray-800 p-3 rounded border border-gray-600 text-xs space-y-2 animate-in fade-in slide-in-from-top-2">
                  <div className="flex justify-between font-bold text-white mb-1">
                    <span>Résultat Analyse</span>
                    <button
                      onClick={() => setQueueAnalysis(null)}
                      className="text-gray-500 hover:text-white"
                      title="Fermer"
                    >
                      <XCircle className="w-3 h-3" />
                    </button>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div className="bg-red-900/30 p-1.5 rounded border border-red-900/50">
                      <span className="text-red-400 block">Bloquées</span>
                      <span className="font-bold text-white">{queueAnalysis.blocked}</span>
                    </div>
                    <div className="bg-green-900/30 p-1.5 rounded border border-green-900/50">
                      <span className="text-green-400 block">Valides</span>
                      <span className="font-bold text-white">{queueAnalysis.valid}</span>
                    </div>
                  </div>

                  <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden flex w-full">
                    <div style={{ width: `${queueAnalysis.blockedPercent}%` }} className="bg-red-500 h-full" />
                    <div style={{ width: `${queueAnalysis.validPercent}%` }} className="bg-green-500 h-full" />
                  </div>

                  {/* Smart Actions */}
                  <div className="pt-1 flex gap-2">
                    {/* Always allow Drop/Reset if user wants to force restart */}
                    <button
                      onClick={dropQueue}
                      className="flex-1 py-1.5 bg-red-900/50 hover:bg-red-800 text-red-200 border border-red-800 rounded flex justify-center items-center gap-2"
                      title="Supprimer TOUTES les URLs (Valides et Bloquées)"
                    >
                      <Trash2 className="w-3 h-3" /> Tout Supprimer
                    </button>

                    {/* Show Clean Patterns only if there are blocked items */}
                    {queueAnalysis.blocked > 0 && (
                      <button
                        onClick={cleanPatterns}
                        className="flex-1 py-1.5 bg-orange-600 hover:bg-orange-700 rounded text-white flex justify-center items-center gap-2"
                        title="Supprimer uniquement les URLs bloquées"
                      >
                        <Filter className="w-3 h-3" /> Nettoyer ({queueAnalysis.blocked})
                      </button>
                    )}
                  </div>
                </div>
              )}

              {/* Search */}
              <input
                type="text"
                placeholder="Rechercher URL..."
                className="w-full bg-gray-800 text-white text-xs p-2 rounded border border-gray-700 focus:border-blue-500 outline-none"
                value={searchTerm}
                onChange={handleSearchChange}
              />
            </div>

            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {loading && !selectedFile && <div className="text-center p-4"><RefreshCw className="animate-spin mx-auto" /></div>}
              {files.length === 0 && !loading && <div className="text-center p-4 text-gray-500">Aucune requête trouvée</div>}
              {files.map(file => (
                <button
                  key={file.path}
                  onClick={() => loadFile(file)}
                  className={`w-full text-left px-3 py-2 rounded text-sm truncate group ${selectedFile?.path === file.path ? 'bg-blue-600 text-white' : 'text-gray-300 hover:bg-gray-700'
                    }`}
                >
                  <div className="font-medium truncate" title={file.url || file.name}>
                    {file.url || file.name}
                  </div>
                  <div className="flex justify-between items-center mt-1">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${file.method === 'GET' ? 'bg-green-900/50 text-green-300' : 'bg-yellow-900/50 text-yellow-300'
                      }`}>
                      {file.method || 'UNK'}
                    </span>
                    <span className="text-xs opacity-50">{file.retryCount || 0} retries</span>
                  </div>
                </button>
              ))}
            </div>

            {/* Pagination Controls */}
            <div className="p-2 bg-gray-900 border-t border-gray-700 flex justify-between items-center">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1 || loading}
                className="p-1 rounded hover:bg-gray-700 disabled:opacity-30 disabled:hover:bg-transparent text-white"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
              <span className="text-xs text-gray-400">
                {page} / {totalPages}
              </span>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages || loading}
                className="p-1 rounded hover:bg-gray-700 disabled:opacity-30 disabled:hover:bg-transparent text-white"
              >
                <ChevronRight className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Editor area */}
          <div className="flex-1 flex flex-col bg-gray-900">
            {selectedFile ? (
              <>
                <div className="p-2 bg-gray-800 border-b border-gray-700 flex justify-between items-center">
                  <div className="flex flex-col overflow-hidden mr-2">
                    <span className="text-xs font-mono text-gray-400 truncate">{selectedFile.path}</span>
                    <span className="text-sm font-bold text-white truncate" title={selectedFile.url}>{selectedFile.url}</span>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <button
                      onClick={formatJson}
                      className="flex items-center gap-2 px-3 py-1 bg-gray-600 hover:bg-gray-500 rounded text-sm text-white"
                      title="Formater le JSON"
                    >
                      <AlignLeft className="w-4 h-4" />
                      Formater
                    </button>
                    <button
                      onClick={saveFile}
                      disabled={saving}
                      className="flex items-center gap-2 px-3 py-1 bg-green-600 hover:bg-green-700 rounded text-sm text-white disabled:opacity-50"
                    >
                      {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
                      Sauvegarder
                    </button>
                  </div>
                </div>

                {error && <div className="p-2 bg-red-900/50 text-red-200 text-sm border-b border-red-700">{error}</div>}
                {successMsg && <div className="p-2 bg-green-900/50 text-green-200 text-sm border-b border-green-700">{successMsg}</div>}

                <textarea
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  className="flex-1 w-full bg-gray-900 text-gray-300 font-mono text-sm p-4 focus:outline-none resize-none"
                  spellCheck="false"
                />
              </>
            ) : (
              <div className="flex-1 flex items-center justify-center text-gray-500">
                Sélectionnez une requête pour l'éditer
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

const DatasetAnalyzer = ({ jobId, onClose, token }) => {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [purging, setPurging] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const authFetch = async (url, options = {}) => {
    const headers = { ...options.headers, 'Authorization': `Bearer ${token}` };
    const res = await fetch(url, { ...options, headers });
    if (!res.ok) throw new Error('Request failed');
    return res;
  };

  const analyzeDataset = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch(`${API_URL}/jobs/${jobId}/dataset/analyze`);
      const data = await res.json();
      setStats(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const purgeDuplicates = async () => {
    if (!window.confirm(`Êtes-vous sûr de vouloir supprimer ${stats.duplicateCount} doublons ? Cette action est irréversible.`)) return;

    setPurging(true);
    setError(null);
    try {
      const res = await authFetch(`${API_URL}/jobs/${jobId}/dataset/deduplicate`, { method: 'POST' });
      const data = await res.json();
      setSuccess(`Opération réussie: ${data.removedCount} fichiers supprimés.`);
      analyzeDataset(); // Refresh stats
    } catch (err) {
      setError(err.message);
    } finally {
      setPurging(false);
    }
  };

  useEffect(() => {
    analyzeDataset();
  }, [jobId]);

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl overflow-hidden">
        <div className="flex justify-between items-center p-4 border-b border-gray-700 bg-gray-750">
          <h3 className="text-xl font-bold text-white flex items-center gap-2">
            <Server className="w-5 h-5 text-purple-400" /> Analyse Dataset
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-white">
            <XCircle className="w-6 h-6" />
          </button>
        </div>

        <div className="p-6">
          {loading && !stats ? (
            <div className="flex justify-center py-12">
              <RefreshCw className="w-8 h-8 animate-spin text-blue-500" />
            </div>
          ) : stats ? (
            <div className="space-y-6">
              <div className="grid grid-cols-3 gap-4">
                <div className="bg-gray-700 p-4 rounded-lg text-center">
                  <p className="text-gray-400 text-sm">Total Items</p>
                  <p className="text-2xl font-bold text-white">{stats.totalItems}</p>
                </div>
                <div className="bg-gray-700 p-4 rounded-lg text-center">
                  <p className="text-gray-400 text-sm">URLs Uniques</p>
                  <p className="text-2xl font-bold text-green-400">{stats.uniqueUrls}</p>
                </div>
                <div className="bg-gray-700 p-4 rounded-lg text-center border border-red-500/30">
                  <p className="text-gray-400 text-sm">Doublons</p>
                  <p className="text-2xl font-bold text-red-400">{stats.duplicateCount}</p>
                </div>
              </div>

              {stats.duplicateCount > 0 ? (
                <div className="bg-red-900/20 border border-red-500/50 p-4 rounded-lg">
                  <h4 className="font-bold text-red-400 mb-2 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4" /> Doublons détectés
                  </h4>
                  <p className="text-sm text-gray-300 mb-4">
                    Le dataset contient <strong>{stats.duplicateCount}</strong> entrées en double.
                    Cela arrive souvent après une reprise de crawl ("resume") suite à un arrêt d'urgence.
                  </p>
                  <div className="flex gap-3">
                    <button
                      onClick={purgeDuplicates}
                      disabled={purging}
                      className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded font-medium flex items-center gap-2 transition-colors disabled:opacity-50"
                    >
                      {purging ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                      Purger les doublons
                    </button>
                  </div>
                </div>
              ) : (
                <div className="bg-green-900/20 border border-green-500/30 p-4 rounded-lg flex items-center gap-3">
                  <CheckCircle className="w-6 h-6 text-green-400" />
                  <span className="text-green-300 font-medium">Le dataset est propre. Aucun doublon détecté.</span>
                </div>
              )}

              {stats.duplicatesExample && stats.duplicatesExample.length > 0 && (
                <div className="bg-gray-900 p-4 rounded-lg font-mono text-xs text-gray-400">
                  <p className="mb-2 uppercase text-gray-500">Exemples de doublons :</p>
                  <ul className="list-disc pl-4 space-y-1">
                    {stats.duplicatesExample.map((url, i) => (
                      <li key={i}>{url}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <div className="bg-red-900/20 p-4 text-red-400 rounded">
              Erreur impossible de charger les stats. {error}
            </div>
          )}

          {success && (
            <div className="mt-4 bg-green-900/30 text-green-400 p-3 rounded flex items-center gap-2">
              <CheckCircle className="w-4 h-4" /> {success}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const JobDetails = ({ job, onToggleRaw, showRaw, token }) => {
  const [showQueueEditor, setShowQueueEditor] = useState(false);
  const [showDatasetAnalyzer, setShowDatasetAnalyzer] = useState(false);

  if (!job) return null;
  if (job.error) {
    return (
      <div className="text-center py-12">
        <XCircle className="w-16 h-16 mx-auto mb-4 text-red-400" />
        <p className="text-red-400 text-lg mb-2">Erreur lors du chargement des détails</p>
        <p className="text-gray-400 text-sm">{job.error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-start">
        <div>
          <h2 className="text-2xl font-bold text-white">Job #{job.id}</h2>
          <div className="flex items-center gap-3 mt-1 flex-wrap">
            {job.domain && <span className="text-sm text-gray-400">{job.domain}</span>}
            {job.crawl_mode && (
              <span className={`text-xs px-2 py-0.5 rounded ${
                job.crawl_mode === 'update' ? 'bg-purple-500/20 text-purple-400' : 'bg-blue-500/20 text-blue-400'
              }`}>
                {job.crawl_mode === 'update' ? 'Mode Update' : 'Mode Standard'}
              </span>
            )}
            {job.previous_crawl_id && (
              <span className="text-xs text-gray-500">prev: {job.previous_crawl_id}</span>
            )}
            {job.oom_restart_count > 0 && (
              <span className="text-xs px-2 py-0.5 rounded bg-orange-500/20 text-orange-400">
                {job.oom_restart_count} OOM restart{job.oom_restart_count > 1 ? 's' : ''}
              </span>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowQueueEditor(true)}
            className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors text-white"
          >
            <Code className="w-4 h-4" />
            Explorer la Queue
          </button>
          <button
            onClick={() => setShowDatasetAnalyzer(true)}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors text-white"
          >
            <Server className="w-4 h-4" />
            Analyser Dataset
          </button>
          <button
            onClick={onToggleRaw}
            className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors text-white"
          >
            <Code className="w-4 h-4" />
            {showRaw ? 'Vue Avancée' : 'Logs Bruts'}
          </button>
        </div>
      </div>

      {showQueueEditor && <RequestQueueEditor jobId={job.id} onClose={() => setShowQueueEditor(false)} token={token} />}
      {showDatasetAnalyzer && <DatasetAnalyzer jobId={job.id} onClose={() => setShowDatasetAnalyzer(false)} token={token} />}

      {showRaw ? (
        <AdvancedLogViewer content={job.rawContent || "Contenu brut non disponible."} jobId={job.id} />
      ) : !job.hasStats && !job.stats ? (
        <div className="text-center py-12 text-gray-400">
          <Clock className="w-12 h-12 mx-auto mb-4 animate-spin" />
          <p className="text-lg mb-2">Les statistiques détaillées ne sont pas encore disponibles.</p>
          <p className="text-sm">Le job est peut-être en cours d'exécution ou le fichier de log n'est pas encore complet.</p>
          <button
            onClick={onToggleRaw}
            className="mt-4 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white"
          >
            Voir les logs avancés
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard title="Total Requêtes" value={job.stats.requestsTotal || 0} icon={Server} color="blue" />
            <StatCard title="Succès" value={job.stats.requestsFinished || 0} icon={CheckCircle} color="green" />
            <StatCard title="Échecs" value={job.stats.requestsFailed || 0} icon={XCircle} color="red" />
            <StatCard title="Durée" value={`${((job.stats.crawlerRuntimeMillis || 0) / 1000).toFixed(2)}s`} icon={Clock} color="purple" />
          </div>

          {job.errors && job.errors.length > 0 && (
            <>
              <ErrorVisualization errors={job.errors} warnings={job.warnings || []} />
              <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-4">
                <h3 className="text-red-400 font-semibold mb-2 flex items-center gap-2">
                  <AlertCircle className="w-5 h-5" />
                  Erreurs ({job.errors.length})
                </h3>
                <div className="max-h-40 overflow-y-auto space-y-2 font-mono text-sm text-red-300">
                  {job.errors.slice(0, 10).map((e, i) => <p key={i} className="p-2 bg-red-900/30 rounded">{e}</p>)}
                  {job.errors.length > 10 && (
                    <p className="text-gray-400 italic">... et {job.errors.length - 10} autres erreurs</p>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};

const LoginPage = ({ onLogin }) => {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${API_URL}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      });
      const data = await res.json();
      if (res.ok) {
        onLogin(data.token);
      } else {
        setError(data.error || 'Login failed');
      }
    } catch (err) {
      setError('Connection error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 flex items-center justify-center p-4">
      <div className="bg-gray-800 p-8 rounded-lg shadow-xl w-full max-w-md border border-gray-700">
        <h1 className="text-2xl font-bold text-white mb-6 text-center flex items-center justify-center gap-2">
          <Activity className="w-8 h-8 text-blue-500" />
          Crawler Monitor
        </h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-gray-400 text-sm font-bold mb-2">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-gray-700 text-white border border-gray-600 rounded p-3 focus:outline-none focus:border-blue-500"
              placeholder="Enter admin password"
            />
          </div>
          {error && <p className="text-red-400 text-sm text-center">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded transition-colors disabled:opacity-50"
          >
            {loading ? 'Logging in...' : 'Login'}
          </button>
        </form>
      </div>
    </div>
  );
};

const ReplicaMonitor = ({ replicas }) => {
  const formatBytes = (bytes) => {
    if (!bytes) return '0 MB';
    const mb = bytes / 1024 / 1024;
    return `${mb.toFixed(0)} MB`;
  };

  const formatCpu = (load) => {
    if (!load) return '0%';
    return `${(load * 100).toFixed(1)}%`;
  };

  const getStatusColor = (timestamp) => {
    const age = Date.now() - timestamp;
    if (age < 5000) return 'green';
    if (age < 15000) return 'yellow';
    return 'red';
  };

  const CircularProgress = ({ cpu, ram, totalRam }) => {
    const size = 140;
    const strokeWidth = 12;
    const radius = (size - strokeWidth) / 2;
    const circumference = 2 * Math.PI * radius;

    const cpuPercent = Math.min((cpu || 0) * 100, 100);
    // DYNAMIC: Use totalRam from heartbeat, fallback to 6GB if not provided
    const ramLimit = totalRam || (6 * 1024 * 1024 * 1024);
    const ramPercent = Math.min((ram / ramLimit) * 100, 100);

    const cpuOffset = circumference - (cpuPercent / 100) * circumference;
    const ramOffset = circumference - (ramPercent / 100) * circumference;

    return (
      <svg width={size} height={size} className="transform -rotate-90">
        {/* Background circles */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius - 18}
          fill="none"
          stroke="#374151"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#374151"
          strokeWidth={strokeWidth}
        />

        {/* CPU (inner circle) */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius - 18}
          fill="none"
          stroke="url(#cpuGradient)"
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={cpuOffset}
          strokeLinecap="round"
          className="transition-all duration-500"
        />

        {/* RAM (outer circle) */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="url(#ramGradient)"
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={ramOffset}
          strokeLinecap="round"
          className="transition-all duration-500"
        />

        {/* Gradients */}
        <defs>
          <linearGradient id="cpuGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#3b82f6" />
            <stop offset="100%" stopColor="#06b6d4" />
          </linearGradient>
          <linearGradient id="ramGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#a855f7" />
            <stop offset="100%" stopColor="#ec4899" />
          </linearGradient>
        </defs>
      </svg>
    );
  };

  const activeReplicas = Object.values(replicas).filter(r => Date.now() - r.timestamp < 30000);

  return (
    <div className="bg-gray-800 rounded-lg p-6 shadow-xl">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <Server className="w-6 h-6 text-blue-400" />
          Crawler Replicas
          <span className="text-sm font-normal text-gray-400 ml-2">
            ({activeReplicas.length} active)
          </span>
        </h2>
      </div>

      {activeReplicas.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <Server className="w-16 h-16 mx-auto mb-4 opacity-30" />
          <p>Aucun replica actif</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {activeReplicas.map((replica) => {
            const statusColor = getStatusColor(replica.timestamp);

            return (
              <div
                key={replica.replicaId}
                className="bg-gray-900 rounded-lg p-5 border border-gray-700 hover:border-gray-600 transition-all"
              >
                {/* Header */}
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <div className={`w-3 h-3 rounded-full ${statusColor === 'green' ? 'bg-green-500 animate-pulse' :
                      statusColor === 'yellow' ? 'bg-yellow-500' : 'bg-red-500'
                      }`} />
                    <span className="text-white font-semibold text-sm truncate">
                      {replica.replicaId.substring(0, 12)}
                    </span>
                  </div>
                  <Cpu className="w-4 h-4 text-blue-400" />
                </div>

                {/* Circular Progress */}
                <div className="flex flex-col items-center mb-4">
                  <div className="relative">
                    <CircularProgress cpu={replica.cpu} ram={replica.ram} totalRam={replica.totalRam} />
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                      <div className="text-center">
                        <div className="text-xs text-gray-400">CPU</div>
                        <div className="text-lg font-bold text-cyan-400">{formatCpu(replica.cpu)}</div>
                        <div className="text-xs text-gray-400 mt-1">RAM</div>
                        <div className="text-sm font-semibold text-pink-400">{formatBytes(replica.ram)}</div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Job Info */}
                {replica.domain && (
                  <div className="mb-3 p-2 bg-gray-800 rounded text-xs">
                    <div className="text-gray-400">Job:</div>
                    <div className="text-white font-mono truncate">{replica.domain}</div>
                  </div>
                )}

                {/* Top Processes */}
                {replica.topProcesses && replica.topProcesses.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-gray-700">
                    <div className="text-xs text-gray-400 mb-2">Top RAM Processes:</div>
                    <div className="space-y-1">
                      {replica.topProcesses.map((proc, idx) => (
                        <div key={idx} className="flex justify-between text-xs">
                          <span className="text-gray-300 truncate flex-1 font-mono">{proc.name}</span>
                          <span className="text-purple-400 ml-2">{formatBytes(proc.ram)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

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