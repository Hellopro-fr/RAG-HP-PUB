import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Search, RefreshCw, ChevronLeft, ChevronRight, ExternalLink, AlertTriangle,
} from 'lucide-react';
import { api } from '../lib/api';
import { Input } from './ui/input';
import { Button } from './ui/button';

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

  const searchTimer = useRef(null);
  useEffect(() => {
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      setDebounced(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(searchTimer.current);
  }, [search]);

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

  // Reset scroll de la liste à chaque search/page/category change : sinon
  // l'utilisateur reste scrollé au milieu d'anciens résultats, ne voit pas
  // le nouveau "top" de liste, et croit que la recherche n'a rien retourné.
  const listRef = useRef(null);
  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = 0;
    // Scroll aussi la liste into view (utile si on vient d'une longue page)
    listRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [debounced, page, category]);

  const counterLabel = useMemo(() => {
    if (loading) return 'Chargement…';
    if (total === 0) return '0 URL';
    return `${total.toLocaleString('fr-FR')} URL${total > 1 ? 's' : ''}`;
  }, [loading, total]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="relative min-w-[200px] flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Rechercher une URL…"
            className="pl-9"
          />
        </div>
        <span className="font-mono text-xs text-muted-foreground">{counterLabel}</span>
      </div>

      {error && (
        <div className="flex items-center justify-between gap-3 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          <span className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" /> Impossible de charger les URLs. {error}
          </span>
          <Button variant="destructive" size="sm" onClick={fetchPage}>
            Réessayer
          </Button>
        </div>
      )}

      {loading && items.length === 0 ? (
        <div className="flex justify-center py-12">
          <RefreshCw className="h-5 w-5 animate-spin text-primary" />
        </div>
      ) : !error && items.length === 0 ? (
        <div className="py-8 text-center text-sm text-muted-foreground">
          Aucune URL dans cette catégorie.
        </div>
      ) : (
        <ul
          ref={listRef}
          className="divide-y divide-border rounded-md border border-border bg-background max-h-[60vh] overflow-y-auto"
        >
          {items.map((it, i) => (
            <li key={`${it.url}-${i}`} className="p-3 transition-colors hover:bg-accent/40">
              <a
                href={it.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-start gap-2 break-all text-sm text-primary hover:text-primary/80"
              >
                <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{it.url}</span>
              </a>
              {category === 'error' && it.error && (
                <p className="mt-1 pl-5 text-xs text-destructive">{it.error}</p>
              )}
            </li>
          ))}
        </ul>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page <= 1 || loading}
          >
            <ChevronLeft className="h-3.5 w-3.5" /> Préc.
          </Button>
          <span className="font-mono text-xs text-muted-foreground">
            Page {page} / {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages || loading}
          >
            Suiv. <ChevronRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      )}
    </div>
  );
};

export default UrlListBrowser;
