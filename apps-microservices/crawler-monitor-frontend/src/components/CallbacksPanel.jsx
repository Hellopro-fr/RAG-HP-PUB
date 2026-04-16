import { useState, useEffect, useCallback } from 'react';
import {
  XCircle, RefreshCw, RotateCcw, Trash2, AlertCircle, CheckCircle, Mail
} from 'lucide-react';
import { api } from '../lib/api';
import ConfirmDestructive from './ConfirmDestructive';

const typeBadgeClasses = (type) => {
  switch (type) {
    case 'success': return 'bg-green-500/20 text-green-400';
    case 'failure': return 'bg-red-500/20 text-red-400';
    case 'stop':    return 'bg-yellow-500/20 text-yellow-400';
    default:        return 'bg-gray-500/20 text-gray-300';
  }
};

const truncate = (s, n = 50) => {
  if (!s) return '';
  return s.length > n ? s.slice(0, n - 1) + '…' : s;
};

const CallbacksPanel = ({ token, onClose }) => {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [busyIndex, setBusyIndex] = useState(null);          // 'retry-N' or 'delete-N'
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [clearing, setClearing] = useState(false);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get('/callbacks', token);
      setItems(data.items || []);
    } catch (err) {
      setError(`Erreur de chargement : ${err.message}`);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { fetchItems(); }, [fetchItems]);

  const retryItem = async (index) => {
    setBusyIndex(`retry-${index}`);
    setError(null);
    setSuccess(null);
    try {
      const data = await api.post(`/callbacks/${index}/retry`, token);
      if (data && data.success) {
        setSuccess(`Callback #${index} relancé avec succès (${data.status}).`);
      } else {
        setError(`Échec retry #${index} : ${(data && data.error) || 'inconnu'}`);
      }
      await fetchItems();
    } catch (err) {
      // 502 from backend means retry attempted but webhook still failed — surface it nicely
      const msg = err.body && err.body.error ? err.body.error : err.message;
      setError(`Échec retry #${index} : ${msg}`);
      await fetchItems(); // refresh to show updated manual_retry_attempts
    } finally {
      setBusyIndex(null);
    }
  };

  const deleteItem = async (index) => {
    if (!window.confirm(`Supprimer le callback #${index} de la liste ?`)) return;
    setBusyIndex(`delete-${index}`);
    setError(null);
    setSuccess(null);
    try {
      await api.delete(`/callbacks/${index}`, token);
      setSuccess(`Callback #${index} supprimé.`);
      await fetchItems();
    } catch (err) {
      setError(`Erreur suppression : ${err.message}`);
    } finally {
      setBusyIndex(null);
    }
  };

  const performClearAll = async () => {
    setClearing(true);
    setError(null);
    setSuccess(null);
    try {
      const data = await api.post('/callbacks/clear', token);
      setSuccess(`Liste vidée (${(data && data.cleared) || 0} entrées).`);
      setShowClearConfirm(false);
      await fetchItems();
    } catch (err) {
      setError(`Erreur clear : ${err.message}`);
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
      <ConfirmDestructive
        open={showClearConfirm}
        title="Clear all callbacks"
        description={
          <>
            Va supprimer <strong>{items.length}</strong> callback{items.length > 1 ? 's' : ''} en échec
            de la liste Redis. Aucune relance ne sera tentée — utilise <em>Retry all</em> avant si tu veux ré-essayer.
            <br /><br />
            Cette action est <strong>irréversible</strong>.
          </>
        }
        shortId="callbacks"
        onConfirm={performClearAll}
        onCancel={() => setShowClearConfirm(false)}
        busy={clearing}
      />

      <div className="bg-gray-800 rounded-lg shadow-xl w-full max-w-5xl h-[85vh] flex flex-col">
        <div className="flex justify-between items-center p-4 border-b border-gray-700">
          <h3 className="text-xl font-bold text-white flex items-center gap-2">
            <Mail className="w-5 h-5 text-red-400" />
            Callbacks en échec ({items.length})
          </h3>
          <div className="flex items-center gap-2">
            <button
              onClick={fetchItems}
              disabled={loading}
              className="p-2 rounded hover:bg-gray-700 disabled:opacity-50"
              title="Rafraîchir"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            {items.length > 0 && (
              <button
                onClick={() => setShowClearConfirm(true)}
                className="px-3 py-1.5 bg-red-700 hover:bg-red-600 rounded text-sm text-white flex items-center gap-2"
              >
                <Trash2 className="w-4 h-4" />
                Tout supprimer ({items.length})
              </button>
            )}
            <button onClick={onClose} className="text-gray-400 hover:text-white" title="Fermer">
              <XCircle className="w-6 h-6" />
            </button>
          </div>
        </div>

        {error && (
          <div className="px-4 py-2 bg-red-900/40 border-b border-red-700/50 text-red-300 text-sm flex items-center gap-2">
            <AlertCircle className="w-4 h-4" /> {error}
          </div>
        )}
        {success && (
          <div className="px-4 py-2 bg-green-900/40 border-b border-green-700/50 text-green-300 text-sm flex items-center gap-2">
            <CheckCircle className="w-4 h-4" /> {success}
          </div>
        )}

        <div className="flex-1 overflow-auto">
          {loading && items.length === 0 ? (
            <div className="flex items-center justify-center py-20">
              <RefreshCw className="w-8 h-8 animate-spin text-blue-400" />
            </div>
          ) : items.length === 0 ? (
            <div className="text-center py-20 text-gray-400">
              <CheckCircle className="w-16 h-16 mx-auto mb-4 text-green-500/60" />
              <p className="text-lg">Aucun callback en échec — tout est OK ✓</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-900 sticky top-0">
                <tr className="text-left text-gray-400 text-xs uppercase">
                  <th className="px-3 py-2">When</th>
                  <th className="px-3 py-2">Type</th>
                  <th className="px-3 py-2">Crawl</th>
                  <th className="px-3 py-2">URL</th>
                  <th className="px-3 py-2">Error</th>
                  <th className="px-3 py-2 text-right">Retries</th>
                  <th className="px-3 py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((entry, idx) => {
                  const isRetrying = busyIndex === `retry-${idx}`;
                  const isDeleting = busyIndex === `delete-${idx}`;
                  const ts = entry.timestamp ? new Date(entry.timestamp).toLocaleString('fr-FR') : '—';
                  return (
                    <tr key={idx} className="border-t border-gray-700 hover:bg-gray-700/30">
                      <td className="px-3 py-2 text-gray-300 whitespace-nowrap">{ts}</td>
                      <td className="px-3 py-2">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded ${typeBadgeClasses(entry.webhook_type)}`}>
                          {entry.webhook_type || 'unknown'}
                        </span>
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-gray-300">
                        {truncate(entry.crawl_id, 16)}
                      </td>
                      <td className="px-3 py-2 text-gray-300" title={entry.url}>
                        <span className="font-mono text-xs">{truncate(entry.url, 50)}</span>
                      </td>
                      <td className="px-3 py-2 text-red-300" title={entry.error || entry.last_manual_retry_error || ''}>
                        {truncate(entry.last_manual_retry_error || entry.error, 40)}
                      </td>
                      <td className="px-3 py-2 text-right text-gray-400">
                        {entry.manual_retry_attempts || 0}
                      </td>
                      <td className="px-3 py-2 text-right whitespace-nowrap">
                        <button
                          onClick={() => retryItem(idx)}
                          disabled={busyIndex !== null}
                          className="px-2 py-1 mr-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 rounded text-xs text-white inline-flex items-center gap-1"
                          title="Rejouer le webhook"
                        >
                          {isRetrying ? <RefreshCw className="w-3 h-3 animate-spin" /> : <RotateCcw className="w-3 h-3" />}
                          Retry
                        </button>
                        <button
                          onClick={() => deleteItem(idx)}
                          disabled={busyIndex !== null}
                          className="px-2 py-1 bg-gray-700 hover:bg-red-700 disabled:opacity-40 rounded text-xs text-white inline-flex items-center gap-1"
                          title="Supprimer cette entrée"
                        >
                          {isDeleting ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        <div className="px-4 py-2 border-t border-gray-700 text-[11px] text-gray-500">
          Les actions Retry / Delete / Clear sont tracées dans l&apos;audit log.
        </div>
      </div>
    </div>
  );
};

export default CallbacksPanel;