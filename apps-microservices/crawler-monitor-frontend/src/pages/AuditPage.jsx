import { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw, AlertCircle, FileText, Filter, Search, Download,
} from 'lucide-react';
import { api } from '../lib/api';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '../components/ui/table';
import {
  Tooltip, TooltipTrigger, TooltipContent,
} from '../components/ui/tooltip';
import Pill from '../components/ui/Pill';
import { cn } from '../lib/utils';

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

// Libellés des colonnes
const HEAD_TOOLTIPS = {
  when:     'Date et heure de l’événement (timezone locale)',
  user:     'Utilisateur authentifié qui a déclenché l’action (anonymous si non loggué)',
  action:   'Nom de l’action : login, queue_drop, callback_retry, dataset_deduplicate…',
  status:   'Résultat de l’action : ok (succès) ou error (échec)',
  target:   'Cible concernée : id de queue, url, job, etc.',
  metadata: 'Détails additionnels structurés (clé=valeur · clé=valeur)',
  ip:       'Adresse IP source de la requête',
};

const HeadWithTip = ({ tip, children }) => (
  <TableHead className="text-[10px] font-semibold uppercase tracking-[0.06em] text-ink-3 h-8 border-b border-hairline">
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="cursor-help border-b border-dotted border-ink-3/40">
          {children}
        </span>
      </TooltipTrigger>
      <TooltipContent>{tip}</TooltipContent>
    </Tooltip>
  </TableHead>
);

const actionTone = (action) => {
  if (!action) return 'neutral';
  if (action.startsWith('login_')) return 'info';
  if (action.startsWith('callback_')) return 'accent';
  if (action.startsWith('queue_drop') || action.startsWith('dataset_dedup')) return 'err';
  return 'warn';
};

const fmtMetadata = (m) => {
  if (!m || typeof m !== 'object') return '';
  return Object.entries(m).map(([k, v]) => `${k}=${v}`).join(' · ');
};

const truncate = (s, n) => (s && s.length > n ? s.slice(0, n - 1) + '…' : (s || ''));

const AuditPage = ({ token }) => {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [actionFilter, setActionFilter] = useState('');
  const [userFilter, setUserFilter] = useState('');
  // Debounce 300ms du userFilter pour éviter un fetch à chaque frappe
  const [debouncedUser, setDebouncedUser] = useState('');
  const [days, setDays] = useState(1);
  const [limit] = useState(100);
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    const id = setTimeout(() => {
      setDebouncedUser(userFilter);
      setOffset(0);
    }, 300);
    return () => clearTimeout(id);
  }, [userFilter]);

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
          ...(debouncedUser ? { user: debouncedUser } : {}),
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
  }, [token, actionFilter, debouncedUser, days, limit, offset]);

  useEffect(() => { fetchEntries(); }, [fetchEntries]);

  const totalPages = Math.max(1, Math.ceil(total / limit));
  const currentPage = Math.floor(offset / limit) + 1;

  const handleExport = () => {
    const blob = new Blob([JSON.stringify(items, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `audit-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="p-4">
      {/* Hero */}
      <div className="flex items-center gap-3 mb-5">
        <FileText className="h-5 w-5 text-ink-2" />
        <h1 className="text-[26px] font-semibold tracking-[-0.025em] text-ink-0 font-display">Audit log</h1>
        {/* Live dot */}
        <span className="flex items-center gap-1.5 font-mono text-[11px] text-ok">
          <span className="h-2 w-2 rounded-full bg-ok animate-pulse-dot" />
          live
        </span>
        <span className="ml-auto font-mono text-[12px] text-ink-3">{total} entrées</span>
        {/* Refresh button */}
        <button
          onClick={fetchEntries}
          disabled={loading}
          aria-label="Rafraîchir"
          className="p-1.5 rounded-md hover:bg-bg-2 text-ink-2"
        >
          <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
        </button>
        {/* Export button */}
        <button
          onClick={handleExport}
          className="p-1.5 rounded-md hover:bg-bg-2 text-ink-2"
          aria-label="Exporter"
        >
          <Download className="h-4 w-4" />
        </button>
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        {/* Period toggle */}
        <div className="flex gap-0.5 rounded-md border border-hairline bg-bg-2 p-0.5">
          {[{ value: 1, label: '24h' }, { value: 7, label: '7j' }, { value: 30, label: '30j' }].map(opt => (
            <button
              key={opt.value}
              onClick={() => { setDays(opt.value); setOffset(0); }}
              className={cn(
                'rounded px-2.5 py-1 text-[11px] font-medium transition-colors',
                days === opt.value ? 'bg-surface text-ink-0 shadow-sm' : 'text-ink-2 hover:text-ink-1'
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {/* Action filter select */}
        <div className="relative">
          <Filter className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-ink-3" />
          <select
            value={actionFilter}
            onChange={e => { setActionFilter(e.target.value); setOffset(0); }}
            className="h-8 pl-8 pr-3 appearance-none rounded-md border border-hairline bg-bg-1 text-[12px] text-ink-0 focus:outline-none focus:border-accent"
          >
            {ACTION_OPTIONS.map(a => (
              <option key={a} value={a}>{a || 'Toutes actions'}</option>
            ))}
          </select>
        </div>

        {/* Search input */}
        <div className="relative flex-1 max-w-[260px]">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-ink-3" />
          <input
            type="text"
            placeholder="Filtrer par user…"
            value={userFilter}
            onChange={e => setUserFilter(e.target.value)}
            className="w-full h-8 pl-8 pr-3 rounded-md border border-hairline bg-bg-1 text-[12px] text-ink-0 placeholder:text-ink-3 focus:outline-none focus:border-accent"
          />
        </div>
      </div>

      {/* Table container */}
      <div className="bg-surface rounded-lg border border-hairline overflow-hidden">
        {error && (
          <div className="px-4 py-2 text-[12px] text-err border-b border-err/20 bg-err-soft flex items-center gap-2">
            <AlertCircle className="h-4 w-4 flex-shrink-0" /> {error}
          </div>
        )}

        <div className="max-h-[70vh] overflow-auto">
          {loading && items.length === 0 ? (
            <div className="flex items-center justify-center py-16">
              <RefreshCw className="h-6 w-6 animate-spin text-ink-3" />
            </div>
          ) : items.length === 0 ? (
            <div className="py-16 text-center">
              <FileText className="mx-auto mb-3 h-10 w-10 opacity-30 text-ink-3" />
              <p className="text-[13px] text-ink-2">Aucune entrée pour ces filtres.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <HeadWithTip tip={HEAD_TOOLTIPS.when}>When</HeadWithTip>
                  <HeadWithTip tip={HEAD_TOOLTIPS.user}>User</HeadWithTip>
                  <HeadWithTip tip={HEAD_TOOLTIPS.action}>Action</HeadWithTip>
                  <HeadWithTip tip={HEAD_TOOLTIPS.status}>Status</HeadWithTip>
                  <HeadWithTip tip={HEAD_TOOLTIPS.target}>Target</HeadWithTip>
                  <HeadWithTip tip={HEAD_TOOLTIPS.metadata}>Metadata</HeadWithTip>
                  <HeadWithTip tip={HEAD_TOOLTIPS.ip}>IP</HeadWithTip>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((e, idx) => (
                  <TableRow key={`${e.ts}-${idx}`} className="hover:bg-bg-2">
                    <TableCell className="font-mono text-[11px] text-ink-3 whitespace-nowrap">
                      {new Date(e.ts).toLocaleString('fr-FR')}
                    </TableCell>
                    <TableCell className="font-mono text-[11px] text-ink-1">
                      {truncate(e.user, 16)}
                    </TableCell>
                    <TableCell>
                      <Pill tone={actionTone(e.action)}>{e.action}</Pill>
                    </TableCell>
                    <TableCell>
                      <Pill tone={e.status === 'ok' ? 'ok' : 'err'}>{e.status || '?'}</Pill>
                    </TableCell>
                    <TableCell className="font-mono text-[11px] text-ink-1" title={e.target || ''}>
                      {truncate(e.target, 24)}
                    </TableCell>
                    <TableCell className="font-mono text-[11px] text-ink-3">
                      {fmtMetadata(e.metadata)}
                    </TableCell>
                    <TableCell className="font-mono text-[11px] text-ink-3">
                      {e.ip || ''}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>

        {/* Pagination footer */}
        <div className="flex items-center justify-between border-t border-hairline px-4 py-2.5">
          <span className="font-mono text-[11px] text-ink-3">Page {currentPage} / {totalPages}</span>
          <div className="flex gap-2">
            <button
              onClick={() => setOffset(o => Math.max(0, o - limit))}
              disabled={offset === 0 || loading}
              className="px-3 py-1 text-[11px] rounded-md border border-hairline text-ink-2 hover:bg-bg-2 disabled:opacity-40"
            >
              Précédent
            </button>
            <button
              onClick={() => setOffset(o => o + limit)}
              disabled={currentPage >= totalPages || loading}
              className="px-3 py-1 text-[11px] rounded-md border border-hairline text-ink-2 hover:bg-bg-2 disabled:opacity-40"
            >
              Suivant
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AuditPage;
