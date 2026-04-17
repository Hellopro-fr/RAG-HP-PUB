import { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  Globe, RefreshCw, AlertCircle, ChevronLeft, Clock,
  CheckCircle, XCircle, RotateCcw, Archive, AlertTriangle,
} from 'lucide-react';
import { useDomainDetailQuery } from '../hooks/queries';
import { Card } from '../components/ui/card';
import { Button } from '../components/ui/button';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '../components/ui/table';
import { cn } from '../lib/utils';

const WINDOW_OPTIONS = ['24h', '7d', '30d'];

// status → accent (shared with JobCard's palette)
const STATUS_META = {
  finished:       { accent: 'success',     text: 'Succès',   Icon: CheckCircle },
  failed:         { accent: 'destructive', text: 'Échec',    Icon: XCircle },
  running:        { accent: 'info',        text: 'En cours', Icon: RefreshCw },
  stopping:       { accent: 'warning',     text: 'Arrêt',    Icon: AlertTriangle },
  archived:       { accent: 'muted',       text: 'Archivé',  Icon: Archive },
  restarting_oom: { accent: 'warning',     text: 'OOM',      Icon: RotateCcw },
};

const ACCENT_CLASSES = {
  info:        { badge: 'bg-info/15 text-info',               bubble: 'bg-info/15 border-info/40',               icon: 'text-info' },
  success:     { badge: 'bg-success/15 text-success',         bubble: 'bg-success/15 border-success/40',         icon: 'text-success' },
  destructive: { badge: 'bg-destructive/15 text-destructive', bubble: 'bg-destructive/15 border-destructive/40', icon: 'text-destructive' },
  warning:     { badge: 'bg-warning/15 text-warning',         bubble: 'bg-warning/15 border-warning/40',         icon: 'text-warning' },
  muted:       { badge: 'bg-muted text-muted-foreground',     bubble: 'bg-muted border-border',                  icon: 'text-muted-foreground' },
};

const fmtDate = (s) => s ? new Date(s).toLocaleString('fr-FR') : '—';

const ChainNode = ({ entry, isFirst }) => {
  if (!entry || !entry.id) return null;
  const meta = STATUS_META[(entry.status || '').toLowerCase()] || { accent: 'muted', text: entry.status, Icon: Clock };
  const accent = ACCENT_CLASSES[meta.accent];
  const Icon = meta.Icon;
  return (
    <Link
      to={`/jobs/${entry.id}`}
      className={cn('group flex min-w-[110px] flex-col items-center gap-1', !isFirst && 'opacity-90')}
      title={`${meta.text} · ${fmtDate(entry.start_time)}`}
    >
      <div className={cn(
        'flex h-12 w-12 items-center justify-center rounded-full border-2 transition-colors group-hover:border-foreground/40',
        accent.bubble
      )}>
        <Icon className={cn('h-5 w-5', accent.icon)} />
      </div>
      <div className="max-w-[110px] truncate font-mono text-xs text-foreground">
        #{String(entry.id || '').slice(0, 10)}
      </div>
      <div className="text-[10px] text-muted-foreground">
        {String(fmtDate(entry.start_time) || '').slice(0, 16)}
      </div>
      {entry.crawl_mode === 'update' && (
        <span className="rounded bg-primary/15 px-1 text-[9px] text-primary">↻ update</span>
      )}
      {entry.oom_restart_count > 0 && (
        <span className="rounded bg-warning/15 px-1 text-[9px] text-warning">
          {entry.oom_restart_count}× OOM
        </span>
      )}
    </Link>
  );
};

const DomainPage = ({ token }) => {
  const { domain } = useParams();
  const navigate = useNavigate();
  const [window, setWindow] = useState('7d');
  const query = useDomainDetailQuery(token, domain, window);
  const data = query.data;

  const chain = data?.chain || [];
  const jobs = data?.jobs || [];

  const success = jobs.filter(j => ['finished', 'archived'].includes((j.status || '').toLowerCase())).length;
  const failure = jobs.filter(j => (j.status || '').toLowerCase() === 'failed').length;
  const running = jobs.filter(j => ['running', 'stopping', 'restarting_oom'].includes((j.status || '').toLowerCase())).length;
  const oomTotal = jobs.reduce((acc, j) => acc + (j.oom_restart_count || 0), 0);
  const completed = success + failure;
  const successRate = completed > 0 ? success / completed : null;
  const updateCount = jobs.filter(j => j.crawl_mode === 'update').length;

  const successRateClass =
    successRate == null ? 'text-muted-foreground'
    : successRate >= 0.9 ? 'text-success'
    : successRate >= 0.7 ? 'text-warning'
    : 'text-destructive';

  return (
    <div className="p-4 space-y-4">
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border p-4">
          <h2 className="flex items-center gap-2 text-base font-semibold">
            <Globe className="h-4 w-4 text-primary" />
            <span className="font-mono">{domain}</span>
          </h2>
          <div className="flex items-center gap-2">
            <div className="flex gap-0.5 rounded-md border border-border bg-muted p-0.5">
              {WINDOW_OPTIONS.map(w => (
                <button
                  key={w}
                  onClick={() => setWindow(w)}
                  className={cn(
                    'rounded px-2 py-0.5 text-xs transition-colors',
                    w === window
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                  )}
                >
                  {w}
                </button>
              ))}
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => query.refetch()}
              disabled={query.isFetching}
              title="Rafraîchir"
            >
              <RefreshCw className={cn('h-4 w-4', query.isFetching && 'animate-spin')} />
            </Button>
          </div>
        </div>

        {query.isError && (
          <div className="flex items-center gap-2 border-b border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" /> {query.error?.message || 'Erreur de chargement'}
          </div>
        )}

        {/* KPI row */}
        <div className="grid grid-cols-2 gap-3 border-b border-border p-4 md:grid-cols-5">
          {[
            { label: 'Total jobs',   value: jobs.length,                             cls: 'text-foreground' },
            { label: 'Success rate', value: successRate == null ? '—' : `${(successRate * 100).toFixed(1)}%`, cls: successRateClass },
            { label: 'En cours',     value: running,                                 cls: 'text-info' },
            { label: 'OOM restarts', value: oomTotal,                                cls: 'text-warning' },
            { label: 'Update mode',  value: `${updateCount}/${jobs.length || 0}`,   cls: 'text-primary' },
          ].map(kpi => (
            <div key={kpi.label} className="rounded-md border border-border bg-muted/30 p-3">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{kpi.label}</div>
              <div className={cn('font-mono text-2xl font-bold tracking-tight', kpi.cls)}>{kpi.value}</div>
            </div>
          ))}
        </div>

        {/* Run chain */}
        <div className="border-b border-border p-4">
          <div className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Run chain (via previous_crawl_id)
          </div>
          {chain.length === 0 ? (
            <div className="text-sm italic text-muted-foreground">
              Pas de chaîne — aucune relation previous_crawl_id détectée.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <div className="flex min-w-min items-start gap-2">
                {chain.map((entry, idx) => (
                  <div key={entry.id} className="flex items-center gap-2">
                    <ChainNode entry={entry} isFirst={idx === 0} />
                    {idx < chain.length - 1 && (
                      <ChevronLeft className="mt-6 h-4 w-4 text-muted-foreground" />
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Jobs list */}
        <div className="max-h-[50vh] overflow-auto">
          {query.isLoading && jobs.length === 0 ? (
            <div className="flex items-center justify-center py-16">
              <RefreshCw className="h-6 w-6 animate-spin text-primary" />
            </div>
          ) : jobs.length === 0 ? (
            <div className="py-16 text-center text-sm text-muted-foreground">
              Aucun job dans la fenêtre.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Job</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Mode</TableHead>
                  <TableHead className="text-right">OOM</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.map(j => {
                  const meta = STATUS_META[(j.status || '').toLowerCase()] || { accent: 'muted', text: j.status };
                  const accent = ACCENT_CLASSES[meta.accent];
                  return (
                    <TableRow
                      key={j.id}
                      onClick={() => navigate(`/jobs/${j.id}`)}
                      className="cursor-pointer"
                    >
                      <TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">
                        {fmtDate(j.start_time)}
                      </TableCell>
                      <TableCell className="font-mono text-xs text-foreground">
                        {String(j.id || '').slice(0, 12)}
                      </TableCell>
                      <TableCell>
                        <span className={cn('rounded px-1.5 py-0.5 text-[10px]', accent.badge)}>
                          {meta.text}
                        </span>
                      </TableCell>
                      <TableCell>
                        {j.crawl_mode === 'update' && (
                          <span className="rounded bg-primary/15 px-1.5 py-0.5 text-[10px] text-primary">↻ update</span>
                        )}
                        {j.crawl_mode === 'standard' && (
                          <span className="text-[10px] text-muted-foreground">standard</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right font-mono text-warning">
                        {j.oom_restart_count || ''}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </div>
      </Card>
    </div>
  );
};

export default DomainPage;
