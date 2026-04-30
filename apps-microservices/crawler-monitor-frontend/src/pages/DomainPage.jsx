import { useState, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  Globe, RefreshCw, AlertCircle, ChevronLeft, Clock,
  CheckCircle, XCircle, RotateCcw, Archive, AlertTriangle,
} from 'lucide-react';
import { useDomainDetailQuery } from '../hooks/queries';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '../components/ui/table';
import {
  Tooltip, TooltipTrigger, TooltipContent,
} from '../components/ui/tooltip';
import Pill from '../components/ui/Pill';
import { cn } from '../lib/utils';

const WINDOW_OPTIONS = ['24h', '7d', '30d'];

const STATUS_META = {
  finished:       { tone: 'ok',      text: 'Succes',   Icon: CheckCircle },
  failed:         { tone: 'err',     text: 'Echec',    Icon: XCircle },
  running:        { tone: 'ok',      text: 'En cours', Icon: RefreshCw, dot: true, pulse: true },
  stopping:       { tone: 'warn',    text: 'Arret',    Icon: AlertTriangle },
  archived:       { tone: 'neutral', text: 'Archive',  Icon: Archive },
  restarting_oom: { tone: 'warn',    text: 'OOM',      Icon: RotateCcw },
};

const fmtDate = (s) => s ? new Date(s).toLocaleString('fr-FR') : '—';

const HEAD_TOOLTIPS = {
  when:   'Date et heure de demarrage du job',
  job:    'Identifiant du job (tronque - clique la ligne pour ouvrir la page detail)',
  status: 'Statut courant du job (finished/failed/running/...)',
  mode:   'Mode de crawl : "update" (incremental) ou standard',
  oom:    'Out Of Memory - nombre de redemarrages suite a un depassement memoire',
};

const HeadWithTip = ({ tip, className, children }) => (
  <TableHead className={cn('text-[10px] font-semibold uppercase tracking-[0.06em] text-ink-3 h-8 border-b border-hairline', className)}>
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

const KpiCell = ({ label, value, valueClass = 'text-ink-0' }) => (
  <div className="flex flex-col items-center justify-center py-4 gap-1 border-r border-hairline last:border-r-0">
    <div className="text-[10px] uppercase tracking-[0.06em] text-ink-3">{label}</div>
    <div className={cn('font-mono text-[22px] font-semibold leading-none', valueClass)}>{value}</div>
  </div>
);

const ChainNode = ({ entry, isFirst }) => {
  if (!entry || !entry.id) return null;
  const meta = STATUS_META[(entry.status || '').toLowerCase()] || { tone: 'neutral', text: entry.status, Icon: Clock };
  const Icon = meta.Icon;

  const bubbleClass = {
    ok:      'bg-ok-soft border-ok/40',
    warn:    'bg-warn-soft border-warn/40',
    err:     'bg-err-soft border-err/40',
    accent:  'bg-accent-soft border-accent/40',
    info:    'bg-info-soft border-info/40',
    neutral: 'bg-bg-2 border-hairline',
  }[meta.tone] || 'bg-bg-2 border-hairline';

  const iconClass = {
    ok:      'text-ok',
    warn:    'text-warn',
    err:     'text-err',
    accent:  'text-accent',
    info:    'text-info',
    neutral: 'text-ink-3',
  }[meta.tone] || 'text-ink-3';

  return (
    <Link
      to={`/jobs/${entry.id}`}
      className={cn('group flex min-w-[110px] flex-col items-center gap-1', !isFirst && 'opacity-90')}
      title={`${meta.text} - ${fmtDate(entry.start_time)}`}
    >
      <div className={cn(
        'flex h-12 w-12 items-center justify-center rounded-full border-2 transition-colors group-hover:border-ink-0/40',
        bubbleClass
      )}>
        <Icon className={cn('h-5 w-5', iconClass)} />
      </div>
      <div className="max-w-[110px] truncate font-mono text-xs text-ink-0">
        <span title={String(entry.id || '')}>#{String(entry.id || '').slice(0, 10)}</span>
      </div>
      <div className="text-[10px] text-ink-3">
        {String(fmtDate(entry.start_time) || '').slice(0, 16)}
      </div>
      {entry.crawl_mode === 'update' && (
        <span className="rounded bg-accent-soft px-1 text-[9px] text-accent-ink">update</span>
      )}
      {entry.oom_restart_count > 0 && (
        <span className="rounded bg-warn-soft px-1 text-[9px] text-warn">
          {entry.oom_restart_count}x OOM
        </span>
      )}
    </Link>
  );
};

const DomainPage = ({ token }) => {
  const { domain } = useParams();
  const navigate = useNavigate();
  const [period, setPeriod] = useState('7d');
  const query = useDomainDetailQuery(token, domain, period);
  const data = query.data;

  const chain = data?.chain || [];
  const jobs = data?.jobs || [];

  const success = jobs.filter(j => ['finished', 'archived'].includes((j.status || '').toLowerCase())).length;
  const failure = jobs.filter(j => (j.status || '').toLowerCase() === 'failed').length;
  const running = jobs.filter(j => ['running', 'stopping', 'restarting_oom'].includes((j.status || '').toLowerCase())).length;
  const oomTotal = jobs.reduce((acc, j) => acc + (j.oom_restart_count || 0), 0);
  const completed = success + failure;
  const successRate = completed > 0 ? success / completed : null;

  const successRateClass =
    successRate == null ? 'text-ink-3'
    : successRate >= 0.9 ? 'text-ok'
    : successRate >= 0.7 ? 'text-warn'
    : 'text-err';

  const fmtPct = (v) => v == null ? '—' : `${(v * 100).toFixed(1)}%`;

  const goToJob = useCallback((j) => {
    navigate(`/jobs/${j.id}`);
  }, [navigate]);

  const onRowKeyDown = useCallback((e, j) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      goToJob(j);
    }
  }, [goToJob]);

  const overallPill = running > 0
    ? <Pill tone="ok" dot pulse>En cours</Pill>
    : failure > 0
    ? <Pill tone="err">Echecs recents</Pill>
    : <Pill tone="neutral">Inactif</Pill>;

  return (
    <div className="p-4 space-y-4">
      <div className="rounded-lg border border-hairline bg-surface overflow-hidden">

        {/* Hero */}
        <div className="px-5 pt-5 pb-0">
          <div className="flex items-center gap-3 mb-5">
            <button
              onClick={() => navigate('/domains')}
              className="p-1.5 rounded-md hover:bg-bg-2 text-ink-2"
              aria-label="Retour"
            >
              <ChevronLeft className="h-5 w-5" />
            </button>
            <Globe className="h-4 w-4 text-ink-2" />
            <h1 className="font-mono text-[26px] font-semibold tracking-[-0.025em] text-ink-0">{domain}</h1>
            {overallPill}
            <div className="ml-auto flex items-center gap-2">
              <div className="flex gap-0.5 rounded-md border border-hairline bg-bg-2 p-0.5">
                {WINDOW_OPTIONS.map(w => (
                  <button
                    key={w}
                    onClick={() => setPeriod(w)}
                    className={cn(
                      'rounded px-2.5 py-1 text-[11px] font-medium transition-colors',
                      w === period ? 'bg-surface text-ink-0 shadow-sm' : 'text-ink-2 hover:text-ink-1'
                    )}
                  >
                    {w}
                  </button>
                ))}
              </div>
              <button
                onClick={() => query.refetch()}
                disabled={query.isFetching}
                className="p-1.5 rounded-md hover:bg-bg-2 text-ink-2"
                title="Rafraichir"
                aria-label="Rafraîchir"
              >
                <RefreshCw className={cn('h-4 w-4', query.isFetching && 'animate-spin')} />
              </button>
            </div>
          </div>

          {/* KPI Strip */}
          <div className="grid grid-cols-2 sm:grid-cols-4 border border-hairline rounded-lg mb-5">
            <KpiCell label="Total jobs"    value={jobs.length}   valueClass="text-ink-0" />
            <KpiCell label="Success rate"  value={fmtPct(successRate)} valueClass={successRateClass} />
            <KpiCell label="En cours"      value={running}       valueClass={running > 0 ? 'text-info' : 'text-ink-3'} />
            <KpiCell label="OOM restarts"  value={oomTotal}      valueClass={oomTotal > 0 ? 'text-warn' : 'text-ink-3'} />
          </div>
        </div>

        {/* Error banner */}
        {query.isError && (
          <div className="flex items-center gap-2 px-4 py-2 text-[12px] text-err border-b border-err/20 bg-err-soft">
            <AlertCircle className="h-4 w-4" /> {query.error?.message || 'Erreur de chargement'}
          </div>
        )}

        {/* Run chain */}
        <div className="border-b border-hairline px-5 py-4">
          <div className="mb-3 text-[10px] font-semibold uppercase tracking-[0.06em] text-ink-3">
            Run chain (via previous_crawl_id)
          </div>
          {chain.length === 0 ? (
            <div className="text-[13px] italic text-ink-2">
              Pas de chaine - aucune relation previous_crawl_id detectee.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <div className="flex min-w-min items-start gap-2">
                {chain.map((entry, idx) => (
                  <div key={entry.id} className="flex items-center gap-2">
                    <ChainNode entry={entry} isFirst={idx === 0} />
                    {idx < chain.length - 1 && (
                      <ChevronLeft className="mt-6 h-4 w-4 text-ink-3" />
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
              <RefreshCw className="h-6 w-6 animate-spin text-ink-3" />
            </div>
          ) : jobs.length === 0 ? (
            <div className="py-16 text-center text-[13px] text-ink-2">
              Aucun job dans la fenetre.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <HeadWithTip tip={HEAD_TOOLTIPS.when}>When</HeadWithTip>
                  <HeadWithTip tip={HEAD_TOOLTIPS.job}>Job</HeadWithTip>
                  <HeadWithTip tip={HEAD_TOOLTIPS.status}>Status</HeadWithTip>
                  <HeadWithTip tip={HEAD_TOOLTIPS.mode}>Mode</HeadWithTip>
                  <HeadWithTip tip={HEAD_TOOLTIPS.oom} className="text-right">OOM</HeadWithTip>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.map(j => {
                  const meta = STATUS_META[(j.status || '').toLowerCase()] || { tone: 'neutral', text: j.status };
                  return (
                    <TableRow
                      key={j.id}
                      onClick={() => goToJob(j)}
                      onKeyDown={(e) => onRowKeyDown(e, j)}
                      role="button"
                      tabIndex={0}
                      className="hover:bg-bg-2 cursor-pointer border-b border-hairline focus:outline-none focus-visible:bg-bg-2"
                    >
                      <TableCell className="text-[12px] py-2 whitespace-nowrap font-mono text-[11px] text-ink-3">
                        {fmtDate(j.start_time)}
                      </TableCell>
                      <TableCell className="text-[12px] py-2 font-mono text-ink-0">
                        <span title={j.id}>{String(j.id || '').slice(0, 12)}</span>
                      </TableCell>
                      <TableCell className="text-[12px] py-2">
                        <Pill tone={meta.tone} dot={!!meta.dot} pulse={!!meta.pulse}>{meta.text}</Pill>
                      </TableCell>
                      <TableCell className="text-[12px] py-2">
                        {j.crawl_mode === 'update' && (
                          <span className="rounded bg-accent-soft px-1.5 py-0.5 text-[10px] text-accent-ink">update</span>
                        )}
                        {j.crawl_mode === 'standard' && (
                          <span className="text-[10px] text-ink-3">standard</span>
                        )}
                      </TableCell>
                      <TableCell className="text-[12px] py-2 text-right font-mono text-warn">
                        {j.oom_restart_count || ''}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </div>

      </div>
    </div>
  );
};

export default DomainPage;