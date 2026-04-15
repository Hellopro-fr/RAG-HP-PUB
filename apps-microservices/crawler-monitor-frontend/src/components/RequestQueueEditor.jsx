import { useState, useEffect } from 'react';
import {
  Code, XCircle, RefreshCw, Search, Trash2, Filter,
  ChevronLeft, ChevronRight, AlignLeft, CheckCircle
} from 'lucide-react';
import { API_URL } from '../lib/constants';

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

export default RequestQueueEditor;