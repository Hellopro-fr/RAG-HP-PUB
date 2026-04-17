// src/components/UrlListBrowser.jsx
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Search, RefreshCw, ChevronLeft, ChevronRight, ExternalLink, AlertTriangle,
} from 'lucide-react';
import { api } from '../lib/api';

const LIMIT = 50;

/**
 * Paginated, searchable URL list for one dataset category.
 *
 * Props:
 *   jobId    - crawl job id (route param)
 *   category - 'success' | 'error' | 'nfr'
 *   token    - JWT
 */
const UrlListBrowser = ({ jobId, category, token }) => {
  const [items, setItems] = useState([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Debounce search input (300ms) — reset to page 1 on change.
  const searchTimer = useRef(null);
  useEffect(() => {
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      setDebounced(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(searchTimer.current);
  }, [search]);

  // Reset pagination + search when the category changes (tab switch).
  useEffect(() => {
    setSearch(''); setDebounced(''); setPage(1);
  }, [category]);

  const fetchPage = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get(`/jobs/${jobId}/dataset/urls`, token, {
        query: { category, page: String(page), limit: String(LIMIT), search: debounced },
      });
      setItems(data.items || []);
      setTotal(data.total || 0);
      setTotalPages(data.totalPages || 0);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [jobId, category, page, debounced, token]);

  useEffect(() => { fetchPage(); }, [fetchPage]);

  const counterLabel = useMemo(() => {
    if (loading) return 'Chargement…';
    if (total === 0) return '0 URL';
    return `${total.toLocaleString('fr-FR')} URL${total > 1 ? 's' : ''}`;
  }, [loading, total]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="w-4 h-4 text-gray-500 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Rechercher une URL…"
            className="w-full bg-gray-900 border border-gray-700 rounded pl-9 pr-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-blue-500"
          />
        </div>
        <span className="text-xs text-gray-400">{counterLabel}</span>
      </div>

      {error && (
        <div className="bg-red-900/20 border border-red-500/50 text-red-300 p-3 rounded flex items-center justify-between gap-3">
          <span className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" /> Impossible de charger les URLs. {error}
          </span>
          <button
            onClick={fetchPage}
            className="text-xs px-2 py-1 bg-red-600 hover:bg-red-700 rounded text-white"
          >Réessayer</button>
        </div>
      )}

      {loading && items.length === 0 ? (
        <div className="flex justify-center py-12">
          <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
        </div>
      ) : !error && items.length === 0 ? (
        <div className="text-gray-500 text-sm py-8 text-center">
          Aucune URL dans cette catégorie.
        </div>
      ) : (
        <ul className="divide-y divide-gray-700 bg-gray-900 border border-gray-700 rounded">
          {items.map((it, i) => (
            <li key={`${it.url}-${i}`} className="p-3 hover:bg-gray-800/60 transition-colors">
              <a
                href={it.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-400 hover:text-blue-300 text-sm break-all flex items-start gap-2"
              >
                <ExternalLink className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                <span>{it.url}</span>
              </a>
              {category === 'error' && it.error && (
                <p className="text-red-400 text-xs mt-1 pl-5">{it.error}</p>
              )}
            </li>
          ))}
        </ul>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between gap-3">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page <= 1 || loading}
            className="flex items-center gap-1 text-xs px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded disabled:opacity-40"
          ><ChevronLeft className="w-3.5 h-3.5" /> Préc.</button>
          <span className="text-xs text-gray-400">
            Page {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages || loading}
            className="flex items-center gap-1 text-xs px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded disabled:opacity-40"
          >Suiv. <ChevronRight className="w-3.5 h-3.5" /></button>
        </div>
      )}
    </div>
  );
};

export default UrlListBrowser;
