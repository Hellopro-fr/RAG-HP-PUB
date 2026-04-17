import { useState, useEffect } from 'react';
import {
  Code, XCircle, RefreshCw, Search, Trash2, Filter,
  ChevronLeft, ChevronRight, AlignLeft, CheckCircle
} from 'lucide-react';
import Editor from 'react-simple-code-editor';
import Prism from 'prismjs';
import 'prismjs/components/prism-json';
import { api } from '../lib/api';
import ConfirmDestructive from './ConfirmDestructive';

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
  // Debounced copy of searchTerm: updated 300ms after the user stops typing.
  // Prevents a backend call on every keystroke.
  const [debouncedSearch, setDebouncedSearch] = useState('');

  // Status filter state (Task 9)
  const [statusFilter, setStatusFilter] = useState('all'); // 'all' | 'pending' | 'handled'
  const [counts, setCounts] = useState(null); // { total, pending, handled } — unfiltered totals from backend

  // Pagination State
  const [page, setPage] = useState(1);
  const [limit] = useState(50);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);

  // Debounce the search term (one effect + timeout)
  useEffect(() => {
    const id = setTimeout(() => setDebouncedSearch(searchTerm), 300);
    return () => clearTimeout(id);
  }, [searchTerm]);

  useEffect(() => {
    fetchFiles();
  }, [jobId, page, debouncedSearch, statusFilter]); // Refetch on page, (debounced) search, or status change

  const fetchFiles = async () => {
    setLoading(true);
    try {
      const data = await api.get(
        `/jobs/${jobId}/request-queues`,
        token,
        { query: {
            page: String(page),
            limit: String(limit),
            search: debouncedSearch,
            status: statusFilter,
          } }
      );

      // Handle paginated response
      if (data.items) {
        setFiles(data.items);
        setTotalPages(data.totalPages);
        setTotalItems(data.total);
        if (data.counts) setCounts(data.counts);
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
      const data = await api.get(`/jobs/${jobId}/request-queues/${file.domain}/${file.name}`, token);
      // Defensive pretty-print: backend returns parsed object, but a stringified
      // payload could arrive in the future and we should not crash on it.
      try {
        setContent(JSON.stringify(data, null, 2));
      } catch {
        setContent(typeof data === 'string' ? data : String(data));
      }
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

      await api.post(
        `/jobs/${jobId}/request-queues/${selectedFile.domain}/${selectedFile.name}`,
        token,
        jsonContent
      );

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
      const data = await api.get(`/jobs/${jobId}/request-queues/analyze`, token);
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
      const data = await api.post(`/jobs/${jobId}/request-queues/clean-patterns`, token);
      setSuccessMsg(`Nettoyage patterns terminé : ${data.deleted} fichiers supprimés sur ${data.scanned} scannés.`);
      setQueueAnalysis(null); // Reset analysis after cleanup
      fetchFiles(); // Refresh list
    } catch (err) {
      setError(`Erreur lors du nettoyage patterns : ${err.message}`);
    } finally {
      setRepairing(false);
    }
  };

  const [showDropConfirm, setShowDropConfirm] = useState(false);

  const performDrop = async () => {
    setRepairing(true);
    setError(null);
    setSuccessMsg(null);
    try {
      await api.post(`/jobs/${jobId}/request-queues/drop`, token);
      setSuccessMsg(`Queue entièrement vidée avec succès !`);
      fetchFiles(); // Refresh list - should be empty
      setQueueAnalysis(null); // Clear analysis
      setShowDropConfirm(false);
    } catch (err) {
      setError(`Erreur lors du "Drop" : ${err.message}`);
    } finally {
      setRepairing(false);
    }
  };

  const dropQueue = () => setShowDropConfirm(true);

  // Search is now handled server-side via fetchFiles
  const handleSearchChange = (e) => {
    setSearchTerm(e.target.value);
    setPage(1); // Reset to first page on search
  };

  const changeStatusFilter = (next) => {
    setStatusFilter(next);
    setPage(1); // Reset to first page on filter change
  };

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
      <style>{`
        .queue-json-editor .token.property    { color: #22d3ee; } /* cyan-400 */
        .queue-json-editor .token.string      { color: #4ade80; } /* green-400 */
        .queue-json-editor .token.number      { color: #fb923c; } /* orange-400 */
        .queue-json-editor .token.boolean,
        .queue-json-editor .token.null        { color: #c084fc; } /* purple-400 */
        .queue-json-editor .token.punctuation { color: #6b7280; } /* gray-500 */
        .queue-json-editor .token.operator    { color: #9ca3af; } /* gray-400 */
        .queue-json-editor textarea,
        .queue-json-editor pre {
          white-space: pre !important;
          overflow-wrap: normal !important;
          word-break: normal !important;
          color: #e5e7eb; /* gray-200 — base text */
          background: transparent !important;
        }
        /* react-simple-code-editor sets overflow: hidden on its inline container,
           which clips the pre even when white-space: pre would push content past
           the wrapper. Override to overflow: visible so the pre extends to its
           natural width, and force min-width: max-content so the container grows
           with its longest line. The outer .queue-json-editor (overflow-auto)
           then provides the horizontal scroll. */
        .queue-json-editor > div {
          min-width: max-content !important;
          overflow: visible !important;
        }
      `}</style>
      <ConfirmDestructive
        open={showDropConfirm}
        title="Drop entire queue"
        description={
          <>
            Cela va supprimer <strong>{totalItems}</strong> requête{totalItems > 1 ? 's' : ''} en attente
            pour le job <code className="text-orange-300">{jobId}</code>.
            <br /><br />
            Le crawler repartira de zéro (l&apos;historique des URLs déjà visitées est conservé).
            Cette action est <strong>irréversible</strong> pour la queue actuelle.
          </>
        }
        shortId={String(jobId).slice(0, 8)}
        onConfirm={performDrop}
        onCancel={() => setShowDropConfirm(false)}
        busy={repairing}
      />
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
              {/* Counts bar (Task 9) — stays constant across filter toggles */}
              {counts && (
                <div className="flex items-center gap-3 text-xs text-gray-300 bg-gray-800 border border-gray-700 rounded px-3 py-2">
                  <span className="text-gray-400">Total</span>
                  <span className="text-white font-semibold">{counts.total.toLocaleString('fr-FR')}</span>
                  <span className="text-gray-600">·</span>
                  <span className="text-gray-400">✓ Traités</span>
                  <span className="text-green-400 font-semibold">{counts.handled.toLocaleString('fr-FR')}</span>
                  <span className="text-gray-600">·</span>
                  <span className="text-gray-400">○ En attente</span>
                  <span className="text-yellow-400 font-semibold">{counts.pending.toLocaleString('fr-FR')}</span>
                </div>
              )}

              {/* Status segmented toggle (Task 9) */}
              <div className="flex gap-1">
                {[
                  { id: 'all',     label: 'Tous' },
                  { id: 'handled', label: '✓ Traités' },
                  { id: 'pending', label: '○ En attente' },
                ].map(opt => (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => changeStatusFilter(opt.id)}
                    className={
                      'text-xs px-3 py-1.5 rounded transition-colors ' +
                      (statusFilter === opt.id
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600')
                    }
                  >
                    {opt.label}
                  </button>
                ))}
              </div>

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
                  <div className="font-medium truncate flex items-center gap-2" title={file.url || file.name}>
                    <span
                      className={file.isHandled ? 'text-green-400 shrink-0' : 'text-gray-500 shrink-0'}
                      title={file.isHandled ? 'Traité' : 'En attente'}
                      aria-label={file.isHandled ? 'Traité' : 'En attente'}
                    >
                      {file.isHandled ? '✓' : '○'}
                    </span>
                    <span className="truncate">{file.url || file.name}</span>
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

          {/* Editor area — min-w-0 on the panel itself so the whole column can shrink
              below the intrinsic width of its longest child (a long URL in the header). */}
          <div className="flex-1 min-w-0 flex flex-col bg-gray-900 overflow-hidden">
            {selectedFile ? (
              <>
                <div className="p-2 bg-gray-800 border-b border-gray-700 flex justify-between items-center gap-2">
                  {/* flex-1 min-w-0 is required so `truncate` on the children actually shrinks
                      the inner div instead of pushing the action buttons past the modal edge. */}
                  <div className="flex flex-col overflow-hidden flex-1 min-w-0">
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

                <div className="queue-json-editor flex-1 bg-gray-900 overflow-auto">
                  <Editor
                    value={content}
                    onValueChange={setContent}
                    highlight={code => Prism.highlight(code, Prism.languages.json, 'json')}
                    padding={16}
                    textareaClassName="focus:outline-none"
                    preClassName=""
                    style={{
                      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
                      fontSize: 13,
                      minHeight: '100%',
                    }}
                  />
                </div>
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