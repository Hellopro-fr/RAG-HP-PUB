import { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw, AlertCircle, FileText, Filter, Calendar,
} from 'lucide-react';
import { api } from '../lib/api';
import { Card } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Button } from '../components/ui/button';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '../components/ui/table';
import {
  Tooltip, TooltipTrigger, TooltipContent,
} from '../components/ui/tooltip';
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

// Fix 4a : libellés des colonnes
const HEAD_TOOLTIPS = {
  when:     'Date et heure de l\u2019événement (timezone locale)',
  user:     'Utilisateur authentifié qui a déclenché l\u2019action (anonymous si non loggué)',
  action:   'Nom de l\u2019action : login, queue_drop, callback_retry, dataset_deduplicate\u2026',
  status:   'Résultat de l\u2019action : ok (succès) ou error (échec)',
  target:   'Cible concernée : id de queue, url, job, etc.',
  metadata: 'Détails additionnels structurés (clé=valeur · clé=valeur)',
  ip:       'Adresse IP source de la requête',
};

const HeadWithTip = ({ tip, children }) => (
  <TableHead>
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="cursor-help border-b border-dotted border-muted-foreground/40">
          {children}
        </span>
      </TooltipTrigger>
      <TooltipContent>{tip}</TooltipContent>
    </Tooltip>
  </TableHead>
);

const statusClass = (status) =>
  status === 'ok'
    ? 'bg-success/15 text-success'
    : 'bg-destructive/15 text-destructive';

const actionClass = (action) => {
  if (!action) return 'bg-muted text-muted-foreground';
  if (action.startsWith('login_')) return 'bg-info/15 text-info';
  if (action.startsWith('callback_')) return 'bg-primary/15 text-primary';
  if (action.startsWith('queue_drop') || action.startsWith('dataset_dedup')) return 'bg-destructive/15 text-destructive';
  return 'bg-warning/15 text-warning';
};

const fmtMetadata = (m) => {
  if (!m || typeof m !== 'object') return '';
  return Object.entries(m).map(([k, v]) => `${k}=${v}`).join(' · ');
};

const truncate = (s, n) => (s && s.length > n ? s.slice(0, n - 1) + '…' : (s || ''));

const SELECT_CLS =
  'h-8 appearance-none rounded-md border border-input bg-background px-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring';

const AuditPage = ({ token }) => {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [actionFilter, setActionFilter] = useState('');
  const [userFilter, setUserFilter] = useState('');
  // Fix 4a : debounce 300ms du userFilter pour éviter un fetch à chaque frappe
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

  return (
    <div className="p-4">
      <Card className="overflow-hidden">
        <div className="flex items-center justify-between border-b border-border p-4">
          <h2 className="flex items-center gap-2 text-base font-semibold">
            <FileText className="h-4 w-4 text-primary" />
            Audit log
            <span className="font-mono text-xs font-normal text-muted-foreground">
              ({total} entrées)
            </span>
          </h2>
          <Button
            variant="ghost"
            size="icon"
            onClick={fetchEntries}
            disabled={loading}
            title="Rafraîchir"
          >
            <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
          </Button>
        </div>

        <div className="flex flex-wrap items-center gap-3 border-b border-border p-3 text-sm">
          <div className="flex items-center gap-2">
            <Calendar className="h-4 w-4 text-muted-foreground" />
            <select
              value={days}
              onChange={e => { setDays(Number(e.target.value)); setOffset(0); }}
              className={SELECT_CLS}
            >
              <option value={1}>24h</option>
              <option value={7}>7 jours</option>
              <option value={30}>30 jours (max)</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <select
              value={actionFilter}
              onChange={e => { setActionFilter(e.target.value); setOffset(0); }}
              className={SELECT_CLS}
            >
              {ACTION_OPTIONS.map(a => (
                <option key={a} value={a}>{a || 'Toutes actions'}</option>
              ))}
            </select>
          </div>
          <Input
            type="text"
            placeholder="Filtrer par user (admin, anonymous, …)"
            value={userFilter}
            onChange={e => setUserFilter(e.target.value)}
            className="h-8 min-w-[200px] flex-1"
          />
        </div>

        {error && (
          <div className="flex items-center gap-2 border-b border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" /> {error}
          </div>
        )}

        <div className="max-h-[70vh] overflow-auto">
          {loading && items.length === 0 ? (
            <div className="flex items-center justify-center py-16">
              <RefreshCw className="h-6 w-6 animate-spin text-primary" />
            </div>
          ) : items.length === 0 ? (
            <div className="py-16 text-center text-muted-foreground">
              <FileText className="mx-auto mb-3 h-10 w-10 opacity-40" />
              <p className="text-sm">Aucune entrée pour ces filtres.</p>
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
                  <TableRow key={`${e.ts}-${idx}`}>
                    <TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">
                      {new Date(e.ts).toLocaleString('fr-FR')}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{truncate(e.user, 16)}</TableCell>
                    <TableCell>
                      <span className={cn('rounded px-1.5 py-0.5 text-[10px]', actionClass(e.action))}>
                        {e.action}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className={cn('rounded px-1.5 py-0.5 text-[10px]', statusClass(e.status))}>
                        {e.status || '?'}
                      </span>
                    </TableCell>
                    <TableCell className="font-mono text-xs" title={e.target || ''}>
                      {truncate(e.target, 24)}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {fmtMetadata(e.metadata)}
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {e.ip || ''}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t border-border p-3 text-sm text-muted-foreground">
            <span className="font-mono">Page {currentPage} / {totalPages}</span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setOffset(o => Math.max(0, o - limit))}
                disabled={offset === 0 || loading}
              >
                Précédent
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setOffset(o => o + limit)}
                disabled={currentPage >= totalPages || loading}
              >
                Suivant
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
};

export default AuditPage;
