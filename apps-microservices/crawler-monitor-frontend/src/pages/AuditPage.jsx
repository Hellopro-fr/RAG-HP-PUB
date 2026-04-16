import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  XCircle, RefreshCw, AlertCircle, FileText, Filter, Calendar,
} from 'lucide-react';
import { api } from '../lib/api';

/**
 * /audit — view the FS-rotated audit log entries.
 *
 * Fetches GET /api/audit?from=&to=&action=&user=&limit=&offset=
 * Defaults to the last 24h; user can narrow to a specific action or user.
 */

const ACTION_OPTIONS = [
  '',
  'login_success', 'login_failure', 'login_attempt',
  'queue_drop', 'queue_clean_patterns', 'queue_repair', 'queue_file_edit',
  'dataset_deduplicate',
  'callback_retry', 'callback_delete', 'callback_clear_all',
];

const STATUS_BADGE = (status) =>
  status === 'ok'
    ? 'bg-green-500/20 text-green-400'
    : 'bg-red-500/20 text-red-400';

const ACTION_BADGE = (action) => {
  if (!action) return 'bg-gray-500/20 text-gray-300';
  if (action.startsWith('login_')) return 'bg-blue-500/20 text-blue-300';
  if (action.startsWith('callback_')) return 'bg-purple-500/20 text-purple-300';
  if (action.startsWith('queue_drop') || action.startsWith('dataset_dedup')) return 'bg-red-500/20 text-red-300';
  return 'bg-yellow-500/20 text-yellow-300';
};

const fmtMetadata = (m) => {
  if (!m || typeof m !== 'object') return '';
  return Object.entries(m).map(([k, v]) => `${k}=${v}`).join(' · ');
};

const truncate = (s, n) => (s && s.length > n ? s.slice(0, n - 1) + '…' : (s || ''));

const AuditPage = ({ token }) => {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Filters
  const [actionFilter, setActionFilter] = useState('');
  const [userFilter, setUserFilter] = useState('');
  const [days, setDays] = useState(1); // window: last N days
  const [limit, setLimit] = useState(100);
  const [offset, setOffset] = useState(0);

  const fetchEntries = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const now = new Date();
      const from = new Date(now.getTime() - days * 24 * 60 * 60 * 1000).toISOString();
      const to = now.toISOString();
      const data = await api.get('/audit', token, {
        query: {
          from, to,
          ...(actionFilter ? { action: actionFilter } : {}),
          ...(userFilter ? { user: userFilter } : {}),
          limit: String(limit),
          offset: String(offset),
        },
      });
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(`Erreur de chargement : ${err.message}`);
      setItems([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [token, actionFilter, userFilter, days, limit, offset]);

  useEffect(() => { fetchEntries(); }, [fetchEntries]);

  const totalPages = Math.max(1, Math.ceil(total / limit));
  const currentPage = Math.floor(offset / limit) + 1;

  return (
    <main className="container mx-auto p-4 space-y-4">
      <div className="bg-gray-800 rounded-lg shadow-xl">
        <div className="flex justify-between items-center p-4 border-b border-gray-700">
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <FileText className="w-5 h-5 text-blue-400" /> Audit log
            <span className="text-sm font-normal text-gray-400">({total} entrées sur la période)</span>
          </h2>
          <div className="flex items-center gap-2">
            <button
              onClick={fetchEntries}
              disabled={loading}
              className="p-2 rounded hover:bg-gray-700 disabled:opacity-50"
              title="Rafraîchir"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={() => navigate('/')}
              className="text-gray-400 hover:text-white"
              title="Fermer"
            >
              <XCircle className="w-6 h-6" />
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="p-4 border-b border-gray-700 flex flex-wrap items-center gap-3 text-sm">
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-gray-500" />
            <select
              value={days}
              onChange={e => { setDays(Number(e.target.value)); setOffset(0); }}
              className="bg-gray-900 border border-gray-700 rounded px-2 py-1 focus:ring-2 focus:ring-blue-500 focus:outline-none"
            >
              <option value={1}>24h</option>
              <option value={7}>7 jours</option>
              <option value={30}>30 jours (max)</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-gray-500" />
            <select
              value={actionFilter}
              onChange={e => { setActionFilter(e.target.value); setOffset(0); }}
              className="bg-gray-900 border border-gray-700 rounded px-2 py-1 focus:ring-2 focus:ring-blue-500 focus:outline-none"
            >
              {ACTION_OPTIONS.map(a => (
                <option key={a} value={a}>{a || 'Toutes actions'}</option>
              ))}
            </select>
          </div>
          <input
            type="text"
            placeholder="Filtrer par user (admin, anonymous, …)"
            value={userFilter}
            onChange={e => { setUserFilter(e.target.value); setOffset(0); }}
            className="flex-1 min-w-[200px] bg-gray-900 border border-gray-700 rounded px-3 py-1 focus:ring-2 focus:ring-blue-500 focus:outline-none"
          />
        </div>

        {error && (
          <div className="px-4 py-2 bg-red-900/40 border-b border-red-700/50 text-red-300 text-sm flex items-center gap-2">
            <AlertCircle className="w-4 h-4" /> {error}
          </div>
        )}

        <div className="overflow-auto max-h-[70vh]">
          {loading && items.length === 0 ? (
            <div className="flex items-center justify-center py-16">
              <RefreshCw className="w-8 h-8 animate-spin text-blue-400" />
            </div>
          ) : items.length === 0 ? (
            <div className="text-center py-16 text-gray-400">
              <FileText className="w-12 h-12 mx-auto mb-3 opacity-40" />
              <p>Aucune entrée pour ces filtres.</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-900 sticky top-0">
                <tr className="text-left text-gray-400 text-xs uppercase">
                  <th className="px-3 py-2">When</th>
                  <th className="px-3 py-2">User</th>
                  <th className="px-3 py-2">Action</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Target</th>
                  <th className="px-3 py-2">Metadata</th>
                  <th className="px-3 py-2">IP</th>
                </tr>
              </thead>
              <tbody>
                {items.map((e, idx) => (
                  <tr key={`${e.ts}-${idx}`} className="border-t border-gray-700 hover:bg-gray-700/30">
                    <td className="px-3 py-2 text-gray-300 whitespace-nowrap">
                      {new Date(e.ts).toLocaleString('fr-FR')}
                    </td>
                    <td className="px-3 py-2 text-gray-300 font-mono text-xs">{truncate(e.user, 16)}</td>
                    <td className="px-3 py-2">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${ACTION_BADGE(e.action)}`}>
                        {e.action}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${STATUS_BADGE(e.status)}`}>
                        {e.status || '?'}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-gray-300 font-mono text-xs" title={e.target || ''}>
                      {truncate(e.target, 24)}
                    </td>
                    <td className="px-3 py-2 text-gray-400 text-xs">
                      {fmtMetadata(e.metadata)}
                    </td>
                    <td className="px-3 py-2 text-gray-500 text-xs font-mono">{e.ip || ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {totalPages > 1 && (
          <div className="p-3 border-t border-gray-700 flex justify-between items-center text-sm text-gray-400">
            <span>Page {currentPage} / {totalPages}</span>
            <div className="flex gap-2">
              <button
                onClick={() => setOffset(o => Math.max(0, o - limit))}
                disabled={offset === 0 || loading}
                className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded disabled:opacity-50"
              >
                Précédent
              </button>
              <button
                onClick={() => setOffset(o => o + limit)}
                disabled={currentPage >= totalPages || loading}
                className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded disabled:opacity-50"
              >
                Suivant
              </button>
            </div>
          </div>
        )}
      </div>
    </main>
  );
};

export default AuditPage;