import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Globe, RefreshCw, AlertCircle, Search,
} from 'lucide-react';
import { useDomainsQuery } from '../hooks/queries';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '../components/ui/table';
import {
  Tooltip, TooltipTrigger, TooltipContent,
} from '../components/ui/tooltip';
import Sparkline from '../components/ui/Sparkline';
import { cn } from '../lib/utils';

const WINDOW_OPTIONS = ['24h', '7d', '30d'];

const HEAD_TOOLTIPS = {
  jobs:    'Nombre total de jobs sur la periode',
  spark:   'Activite sur 7 jours (donnees non disponibles par domaine)',
  ok:      'Succes (jobs finished/archived)',
  ko:      'Echec (failed)',
  oom:     'Out Of Memory - nombre de redemarrages suite a un depassement memoire',
  succ:    'Taux de succes sur les jobs termines (finished+archived) / (finished+archived+failed)',
  lastrun: 'Date et heure du dernier job demarre',
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

const DomainsPage = ({ token }) => {
  const navigate = useNavigate();
  const [period, setPeriod] = useState('7d');
  const [search, setSearch] = useState('');
  const query = useDomainsQuery(token, period);

  const all = query.data?.domains || [];
  const filtered = search
    ? all.filter(d => d.domain.toLowerCase().includes(search.toLowerCase()))
    : all;

  const fmtPct = (v) => v == null ? '—' : `${(v * 100).toFixed(1)}%`;
  const fmtDate = (s) => s ? new Date(s).toLocaleString('fr-FR') : '—';

  const successColor = (rate) => {
    if (rate == null) return 'text-ink-3';
    if (rate >= 0.9) return 'text-ok';
    if (rate >= 0.7) return 'text-warn';
    return 'text-err';
  };

  const totalSuccess = all.reduce((s, d) => s + (d.success || 0), 0);
  const totalFailed  = all.reduce((s, d) => s + (d.failure || 0), 0);
  const totalRunning = all.reduce((s, d) => s + (d.running || 0), 0);

  const goToDomain = useCallback((d) => {
    navigate(`/domains/${encodeURIComponent(d.domain)}`);
  }, [navigate]);

  const onRowKeyDown = useCallback((e, d) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      goToDomain(d);
    }
  }, [goToDomain]);

  return (
    <div className="p-4">
      <div className="rounded-lg border border-hairline bg-surface overflow-hidden">

        {/* Hero */}
        <div className="px-5 pt-5 pb-0">
          <div className="flex items-center gap-3 mb-5">
            <Globe className="h-5 w-5 text-ink-2" />
            <h1 className="text-[26px] font-semibold tracking-[-0.025em] text-ink-0 font-display">Domains</h1>
            <span className="font-mono text-[12px] text-ink-3">
              ({filtered.length}{filtered.length !== all.length ? ` / ${all.length}` : ''})
            </span>
            <div className="ml-auto">
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
            <KpiCell label="Total"   value={all.length}   valueClass="text-ink-0" />
            <KpiCell label="Success" value={totalSuccess} valueClass="text-ok" />
            <KpiCell label="Failed"  value={totalFailed}  valueClass="text-err" />
            <KpiCell label="Running" value={totalRunning} valueClass="text-info" />
          </div>

          {/* Toolbar */}
          <div className="flex items-center gap-3 mb-4">
            <div className="relative flex-1 max-w-[280px]">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-ink-3" />
              <input
                type="text"
                placeholder="Filtrer domaines..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="w-full h-8 pl-8 pr-3 rounded-md border border-hairline bg-bg-1 text-[12px] text-ink-0 placeholder:text-ink-3 focus:outline-none focus:border-accent"
              />
            </div>
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
          </div>
        </div>

        {/* Error banner */}
        {query.isError && (
          <div className="flex items-center gap-2 px-4 py-2 text-[12px] text-err border-b border-err/20 bg-err-soft">
            <AlertCircle className="h-4 w-4" /> {query.error?.message || 'Erreur de chargement'}
          </div>
        )}

        {/* Table */}
        <div className="max-h-[65vh] overflow-auto">
          {query.isLoading && all.length === 0 ? (
            <div className="flex items-center justify-center py-16">
              <RefreshCw className="h-6 w-6 animate-spin text-ink-3" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="py-16 text-center">
              <Globe className="mx-auto mb-3 h-10 w-10 text-ink-3 opacity-40" />
              <p className="text-[13px] text-ink-2">
                {search ? `Aucun domaine ne correspond a "${search}".` : 'Aucun domaine sur la periode.'}
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-[10px] font-semibold uppercase tracking-[0.06em] text-ink-3 h-8 border-b border-hairline">Domain</TableHead>
                  <HeadWithTip tip={HEAD_TOOLTIPS.jobs}    className="text-right">Jobs</HeadWithTip>
                  <HeadWithTip tip={HEAD_TOOLTIPS.spark}>Activite</HeadWithTip>
                  <HeadWithTip tip={HEAD_TOOLTIPS.ok}      className="text-right">OK</HeadWithTip>
                  <HeadWithTip tip={HEAD_TOOLTIPS.ko}      className="text-right">KO</HeadWithTip>
                  <HeadWithTip tip={HEAD_TOOLTIPS.oom}     className="text-right">OOM</HeadWithTip>
                  <HeadWithTip tip={HEAD_TOOLTIPS.succ}    className="text-right">%</HeadWithTip>
                  <HeadWithTip tip={HEAD_TOOLTIPS.lastrun}>Last run</HeadWithTip>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map(d => (
                  <TableRow
                    key={d.domain}
                    onClick={() => goToDomain(d)}
                    onKeyDown={(e) => onRowKeyDown(e, d)}
                    role="button"
                    tabIndex={0}
                    className="hover:bg-bg-2 cursor-pointer border-b border-hairline focus:outline-none focus-visible:bg-bg-2"
                  >
                    <TableCell className="text-[12px] py-2 font-mono text-ink-0">{d.domain}</TableCell>
                    <TableCell className="text-[12px] py-2 text-right font-mono text-ink-2">{d.total_jobs ?? '—'}</TableCell>
                    <TableCell className="text-[12px] py-2">
                      <Sparkline data={[]} w={80} h={24} color="var(--ink-3)" />
                    </TableCell>
                    <TableCell className="text-[12px] py-2 text-right font-mono text-ok">{d.success || ''}</TableCell>
                    <TableCell className="text-[12px] py-2 text-right font-mono text-err">{d.failure || ''}</TableCell>
                    <TableCell className="text-[12px] py-2 text-right font-mono text-warn">{d.oom_total || ''}</TableCell>
                    <TableCell className={cn('text-[12px] py-2 text-right font-mono font-semibold', successColor(d.success_rate))}>
                      {fmtPct(d.success_rate)}
                    </TableCell>
                    <TableCell className="text-[12px] py-2 font-mono text-[11px] text-ink-3 whitespace-nowrap">
                      {fmtDate(d.last_run_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-hairline px-4 py-2.5 flex items-center justify-between">
          <span className="font-mono text-[11px] text-ink-3">
            {filtered.length} domaine{filtered.length > 1 ? 's' : ''}
            {filtered.length !== all.length ? ` sur ${all.length}` : ''}
          </span>
        </div>

      </div>
    </div>
  );
};

export default DomainsPage;