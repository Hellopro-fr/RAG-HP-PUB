import { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import { useParams, Outlet } from 'react-router-dom';
import {
  RefreshCw, Server,
  Search, Filter, Calendar, ChevronLeft, ChevronRight, X,
  Download, RefreshCcw, Plus, Activity, Cpu,
} from 'lucide-react';
import { JOBS_PER_PAGE } from '../lib/constants';
import {
  useJobsQuery,
  useCapacityQuery,
  useJobDetailsQuery,
  useAlertsQuery,
} from '../hooks/queries';
import JobDetails from '../components/JobDetails';
import AlertsBanner from '../components/AlertsBanner';
import { Input } from '../components/ui/input';
import { Button } from '../components/ui/button';
import { cn } from '../lib/utils';
import { CoherencePastille } from '../coherence/components/CoherencePastille';
import Pill from '../components/ui/Pill';
import StatTile from '../components/ui/StatTile';
import UiTimeline from '../components/ui/Timeline';
import CapacityRing from '../components/ui/CapacityRing';

const JOB_TONE = {
  running:  'accent',
  finished: 'ok',
  failed:   'err',
  archived: 'neutral',
};

/** Inline mini-stat for replica cards */
const MiniStat = ({ label, value }) => (
  <div className="flex flex-col gap-0.5">
    <span className="text-[9.5px] font-semibold text-ink-3 uppercase tracking-wider">{label}</span>
    <span className="font-mono text-[13px] font-semibold text-ink-0">{value}</span>
  </div>
);

/** Section card wrapper matching spec (icon + title + subtitle + action) */
const SectionCard = ({ icon: Icon, title, subtitle, action, children, padding = 'p-[18px]' }) => (
  <div className="bg-surface border border-hairline rounded-lg shadow-sm overflow-hidden">
    <div className="px-[18px] py-[14px] border-b border-hairline flex items-center gap-2.5">
      {Icon && (
        <div className="w-[26px] h-[26px] rounded-md bg-bg-2 flex items-center justify-center text-ink-1 flex-shrink-0">
          <Icon size={14} />
        </div>
      )}
      <div className="flex-1 min-w-0">
        {title && <div className="text-[13px] font-semibold text-ink-0">{title}</div>}
        {subtitle && <div className="text-[11.5px] text-ink-2 mt-0.5">{subtitle}</div>}
      </div>
      {action}
    </div>
    <div className={padding}>{children}</div>
  </div>
);

/** Period toggle for timeline */
const PERIODS = ['1h', '24h', '7j', '30j'];
const PeriodToggle = ({ value, onChange }) => (
  <div className="flex gap-1 p-0.5 bg-bg-1 rounded-md border border-hairline">
    {PERIODS.map(t => (
      <button
        key={t}
        onClick={() => onChange(t)}
        className={cn(
          'px-2.5 py-[3px] text-[11px] font-medium rounded cursor-pointer border-none',
          t === value
            ? 'bg-surface font-semibold text-ink-0 shadow-sm'
            : 'bg-transparent text-ink-2 hover:text-ink-1',
        )}
      >
        {t}
      </button>
    ))}
  </div>
);

/** Legend dot + label + count */
const LegendItem = ({ color, label, count }) => (
  <div className="flex items-center gap-1.5">
    <span className="w-2 h-2 rounded-[2px] flex-shrink-0" style={{ background: color }} />
    <span className="text-[11px] text-ink-2">{label}</span>
    <span className="font-mono text-[11px] font-semibold text-ink-0">{count}</span>
  </div>
);

/**
 * Overview page (`/` and `/jobs/:id`).
 *
 * Data via React Query hooks; no manual fetching here.
 * `replicas` still comes from props (it is WebSocket-only, lives in App.jsx).
 */
const Overview = ({ token, replicas }) => {
  const { id: routeJobId } = useParams();
  // Local UI state
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [showRaw, setShowRaw] = useState(false);
  const [timelinePeriod, setTimelinePeriod] = useState('24h');
  // Panneau inline : job sélectionné (état local, pas piloté par l'URL)
  const [selectedJobId, setSelectedJobId] = useState(routeJobId ?? null);

  // Data layer
  const jobsQuery = useJobsQuery(token);
  const allJobs = jobsQuery.data || [];
  const loading = jobsQuery.isLoading;

  const capacityQuery = useCapacityQuery(token);
  const capacity = capacityQuery.data || null;

  const alertsQuery = useAlertsQuery(token);
  const activeAlerts = (alertsQuery.data?.alerts || []).filter(a => !a.dismissed);
  const nbActiveAlerts = activeAlerts.length;
  const hasCritical = activeAlerts.some(a => a.severity === 'critical');

  const detailsQuery = useJobDetailsQuery(token, selectedJobId);
  const selectedJob = selectedJobId
    ? (detailsQuery.data ?? (detailsQuery.error ? { id: selectedJobId, error: detailsQuery.error.message } : null))
    : null;
  const loadingDetails = !!selectedJobId && detailsQuery.isLoading;

  // Relative time since last data update
  const dataUpdatedAt = jobsQuery.dataUpdatedAt;
  const syncLabel = useMemo(() => {
    if (!dataUpdatedAt) return null;
    const diffS = Math.round((Date.now() - dataUpdatedAt) / 1000);
    if (diffS < 5) return 'il y a <5s';
    if (diffS < 60) return `il y a ${diffS}s`;
    return `il y a ${Math.round(diffS / 60)}min`;
  }, [dataUpdatedAt]);

  const filteredJobs = useMemo(() => {
    return allJobs.filter(job => {
      if (!job || !job.id) return false;
      const jobDate = new Date(job.start_time);
      const start = startDate ? new Date(startDate) : null;
      const end = endDate ? new Date(endDate) : null;

      if (start && jobDate < start) return false;
      if (end) {
        const endOfDay = new Date(end);
        endOfDay.setHours(23, 59, 59, 999);
        if (jobDate > endOfDay) return false;
      }

      const matchesStatus = statusFilter === 'all' || job.status === statusFilter;
      const matchesSearch = searchTerm === '' ||
        (job.id && String(job.id).includes(searchTerm)) ||
        (job.domain && job.domain.toLowerCase().includes(searchTerm.toLowerCase()));

      return matchesStatus && matchesSearch;
    }).sort((a, b) => new Date(b.start_time) - new Date(a.start_time));
  }, [allJobs, searchTerm, statusFilter, startDate, endDate]);

  const paginatedJobs = useMemo(() => {
    const startIndex = (currentPage - 1) * JOBS_PER_PAGE;
    return filteredJobs.slice(startIndex, startIndex + JOBS_PER_PAGE);
  }, [filteredJobs, currentPage]);

  const totalPages = Math.ceil(filteredJobs.length / JOBS_PER_PAGE);

  const globalStats = useMemo(() => {
    const finished = allJobs.filter(j => j.status === 'finished').length;
    const failed = allJobs.filter(j => j.status === 'failed').length;
    const running = allJobs.filter(j => j.status === 'running').length;
    const archived = allJobs.filter(j => j.status === 'archived').length;
    return { finished, failed, running, archived, total: allJobs.length };
  }, [allJobs]);

  // Total slots from capacity or replica count
  const totalSlots = capacity?.total ?? (replicas ? Object.keys(replicas).length : 0);

  // Build timeline data: aggregate jobs by hour (last 24 buckets)
  const timelineData = useMemo(() => {
    if (!allJobs.length) return [];
    const now = Date.now();
    const buckets = Array.from({ length: 24 }, (_, i) => {
      const from = now - (23 - i) * 3600 * 1000;
      const to = from + 3600 * 1000;
      const hour = new Date(from).getHours();
      return { label: `${String(hour).padStart(2, '0')}h`, from, to, ok: 0, run: 0, fail: 0 };
    });
    allJobs.forEach(job => {
      const t = new Date(job.start_time).getTime();
      const bucket = buckets.find(b => t >= b.from && t < b.to);
      if (!bucket) return;
      if (job.status === 'finished' || job.status === 'archived') bucket.ok++;
      else if (job.status === 'running') bucket.run++;
      else if (job.status === 'failed') bucket.fail++;
    });
    return buckets.map(({ label, ok, run, fail }) => ({ label, ok, run, fail }));
  }, [allJobs]);

  const jobsListRef = useRef(null);

  // Sélectionner un job dans le panneau inline (pas de navigation URL)
  const handleSelectJob = useCallback((id) => {
    if (!id || id === 'undefined' || id === 'null') return;
    setSelectedJobId(id);
  }, []);

  // Synchroniser selectedJobId avec routeJobId (navigation directe via URL)
  useEffect(() => {
    if (routeJobId) setSelectedJobId(routeJobId);
  }, [routeJobId]);

  // Auto-sélectionner le premier job quand la liste se charge (si pas de sélection)
  useEffect(() => {
    if (!selectedJobId && filteredJobs.length > 0) {
      setSelectedJobId(filteredJobs[0].id);
    }
    // Si le job sélectionné n'existe plus dans la liste filtrée, passer au premier
    if (selectedJobId && filteredJobs.length > 0) {
      const stillExists = filteredJobs.some(j => j.id === selectedJobId);
      if (!stillExists) setSelectedJobId(filteredJobs[0].id);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filteredJobs]);

  const hasDateFilter = !!(startDate || endDate);

  // Hero status pill
  const statusPill = hasCritical
    ? <Pill tone="err" dot>critique</Pill>
    : nbActiveAlerts > 0
      ? <Pill tone="warn" dot>{nbActiveAlerts} alerte{nbActiveAlerts > 1 ? 's' : ''}</Pill>
      : <Pill tone="ok" dot>opérationnel</Pill>;

  // Replica list derived from WS prop (object keyed by replicaId or array)
  const replicaList = useMemo(() => {
    if (!replicas) return [];
    if (Array.isArray(replicas)) return replicas.filter(r => r && r.replicaId);
    return Object.values(replicas).filter(r => r && r.replicaId);
  }, [replicas]);

  const nbRegions = useMemo(() => {
    const regions = new Set(replicaList.map(r => r.region).filter(Boolean));
    return regions.size;
  }, [replicaList]);

  return (
    <div className="p-4 flex flex-col gap-6 max-w-[1400px]">
      <AlertsBanner token={token} />

      {/* Hero */}
      <div className="flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            {statusPill}
            {syncLabel && (
              <span className="font-mono text-[11px] text-ink-2">
                dernière sync · {syncLabel}
              </span>
            )}
          </div>
          <h1 className="font-display text-[26px] font-semibold text-ink-0 tracking-[-0.025em]">
            Vue d&apos;ensemble
          </h1>
          <p className="text-[13px] text-ink-2 mt-1">
            {globalStats.total} jobs sur 24h
            {replicaList.length > 0
              ? nbRegions > 0
                ? ` · ${replicaList.length} replicas répartis sur ${nbRegions} région${nbRegions > 1 ? 's' : ''}`
                : ` · ${replicaList.length} replicas actifs`
              : ''}
          </p>
        </div>
        <div className="flex gap-1.5 items-center">
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5 text-ink-1 border-hairline"
            onClick={() => console.log('export')}
          >
            <Download size={13} />
            Exporter
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5 text-ink-1 border-hairline"
            onClick={() => jobsQuery.refetch()}
          >
            <RefreshCcw size={13} />
            Rafraîchir
          </Button>
          <Button
            size="sm"
            className="gap-1.5 bg-ink-0 text-white hover:bg-ink-1"
            onClick={() => console.log('nouveau job')}
          >
            <Plus size={13} />
            Nouveau job
          </Button>
        </div>
      </div>

      {/* 5 StatTiles — KPI row */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        {/* Total — no delta data source (no prev-24h endpoint), no spark data source */}
        <StatTile
          label="Total"
          value={loading ? null : String(globalStats.total)}
          accent="var(--ink-1)"
        />

        {/* Succès */}
        <StatTile
          label="Succès"
          value={loading ? null : String(globalStats.finished)}
          accent="var(--ok)"
          deltaTone="ok"
          sub={!loading && globalStats.total > 0
            ? `${(globalStats.finished / globalStats.total * 100).toFixed(1)}%`
            : undefined}
          // no delta data source (no prev-24h endpoint)
          // no spark data source (no time-series per-status from backend)
        />

        {/* Échecs */}
        <StatTile
          label="Échecs"
          value={loading ? null : String(globalStats.failed)}
          accent="var(--err)"
          deltaTone={globalStats.failed > 0 ? 'err' : 'ok'}
          sub={!loading && globalStats.total > 0
            ? `${(globalStats.failed / globalStats.total * 100).toFixed(1)}%`
            : undefined}
          // no delta data source
          // no spark data source
        />

        {/* En cours — bar chart from timeline data (last 7 hours) */}
        <div className="relative">
          <StatTile
            label="En cours"
            value={loading ? null : String(globalStats.running)}
            accent="var(--accent)"
            sub={!loading && totalSlots > 0 ? `/ ${totalSlots} slots` : undefined}
            spark={!loading && timelineData.length > 0 ? (
              <div className="flex gap-0.5 items-end h-7">
                {timelineData.slice(-7).map((d, i) => {
                  const maxRun = Math.max(1, ...timelineData.map(x => x.run));
                  return (
                    <div
                      key={i}
                      className="flex-1 rounded-[1px]"
                      style={{
                        height: Math.max(4, (d.run / maxRun) * 28),
                        background: 'var(--accent)',
                        opacity: 0.7,
                      }}
                    />
                  );
                })}
              </div>
            ) : undefined}
          />
          <div className="absolute right-2 top-2">
            <CoherencePastille ruleId="running_count_parity" />
          </div>
        </div>

        {/* Archivés — no delta, no spark data source */}
        <StatTile
          label="Archivés"
          value={loading ? null : String(globalStats.archived)}
          accent="var(--hairline-strong)"
          sub={!loading ? '24h' : undefined}
        />
      </div>

      {/* Timeline + Capacity */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_360px]">
        <SectionCard
          icon={Activity}
          title="Timeline d'activité"
          subtitle="Volume de jobs par heure · fenêtre glissante 24h"
          action={<PeriodToggle value={timelinePeriod} onChange={setTimelinePeriod} />}
        >
          <UiTimeline data={timelineData} />
          {/* Legend strip + latency stats */}
          <div className="flex gap-4 mt-3.5 pt-3 border-t border-hairline items-center flex-wrap">
            <LegendItem color="var(--ok)"     label="Terminés" count={globalStats.finished} />
            <LegendItem color="var(--accent)" label="En cours" count={globalStats.running} />
            <LegendItem color="var(--err)"    label="Échecs"   count={globalStats.failed} />
            {/* P50/P95/Throughput — no backend data source */}
          </div>
        </SectionCard>

        <SectionCard
          icon={Cpu}
          title="Capacité globale"
          subtitle={`${capacity?.used ?? 0} / ${capacity?.total ?? totalSlots} slots utilisés`}
        >
          <CapacityRing
            used={capacity?.used ?? 0}
            total={capacity?.total ?? Math.max(1, totalSlots)}
            format="count"
          />
          {/* Replica list with mini progress bars */}
          <div className="mt-4 flex flex-col gap-2">
            {replicaList.length > 0 ? replicaList.map(r => (
              <div key={r.replicaId} className="flex items-center gap-2 text-[11.5px]">
                <Server size={12} className="text-ink-3 flex-shrink-0" />
                <span className="font-mono text-ink-1 shrink-0">
                  {r.region ?? r.replicaId?.substring(0, 8) ?? '—'}
                </span>
                <div className="flex-1 h-1 bg-bg-2 rounded overflow-hidden">
                  {/* per-replica used/total slots not available — use CPU% as proxy */}
                  <div
                    className="h-full bg-ink-3 rounded"
                    style={{ width: `${Math.max(4, (r.cpu ?? 0) * 100)}%` }}
                  />
                </div>
                <span className="font-mono text-[11px] text-ink-2 shrink-0">
                  {r.cpu != null ? `${(r.cpu * 100).toFixed(0)}%` : '—'}
                </span>
              </div>
            )) : (
              <p className="text-[11.5px] text-ink-3 text-center py-2">Aucun replica actif</p>
            )}
          </div>
        </SectionCard>
      </div>

      {/* Crawler replicas grid */}
      {replicaList.length > 0 && (
        <SectionCard
          icon={Server}
          title="Crawler replicas"
          subtitle="Workers actifs · santé temps-réel"
          action={
            <Pill
              tone={replicaList.some(r => r.status === 'running' || r.status === 'busy') ? 'accent' : 'warn'}
              dot
            >
              {replicaList.filter(r => r.status === 'running' || r.status === 'busy').length} actif
            </Pill>
          }
        >
          <div className="grid grid-cols-2 gap-2.5 md:grid-cols-4">
            {replicaList.map(r => {
              const status = r.status ?? 'idle';
              const tone =
                status === 'running' || status === 'busy' ? 'accent'
                : status === 'error' ? 'err'
                : status === 'draining' ? 'warn'
                : 'neutral';
              // cpu is 0-1 fraction from WS heartbeat; ram is bytes
              const cpuPct = r.cpu != null ? `${(r.cpu * 100).toFixed(1)}%` : '—';
              const ramG = r.ram != null
                ? `${(r.ram / 1024 / 1024 / 1024).toFixed(2)}G`
                : '—';
              // jobs: 1 if replica has an active jobId, else 0
              const jobs = r.jobId ? 1 : 0;
              return (
                <div
                  key={r.replicaId}
                  className="rounded-md border border-hairline bg-bg-0 p-3.5"
                >
                  <div className="flex items-center justify-between mb-2.5">
                    <span className="font-mono text-[11px] text-ink-2 truncate">
                      {String(r.replicaId ?? '').substring(0, 12)}
                    </span>
                    <Pill tone={tone} dot>{status}</Pill>
                  </div>
                  <div className="text-[11px] text-ink-2 mb-2.5">{r.region ?? '—'}</div>
                  <div className="grid grid-cols-3 gap-2">
                    <MiniStat label="CPU" value={cpuPct} />
                    <MiniStat label="RAM" value={ramG} />
                    <MiniStat label="Jobs" value={jobs} />
                  </div>
                </div>
              );
            })}
          </div>
        </SectionCard>
      )}

      {/* Jobs list + detail panel split (440px / 1fr) */}
      <div ref={jobsListRef} className="grid grid-cols-1 md:grid-cols-[440px_1fr] gap-4 scroll-mt-16">
        {/* ── Jobs list panel (440px) ── */}
        <div className="bg-surface rounded-lg border border-hairline shadow-sm overflow-hidden">
          {/* Toolbar */}
          <div className="px-5 py-4 border-b border-hairline space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-[13px] font-semibold text-ink-0">Jobs ({filteredJobs.length})</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative flex-grow min-w-[160px]">
                <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" />
                <Input
                  type="text"
                  placeholder="Filtrer par ID ou domaine…"
                  value={searchTerm}
                  onChange={e => { setSearchTerm(e.target.value); setCurrentPage(1); }}
                  className="pl-8"
                />
              </div>

              <div className="relative">
                <Filter className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3 pointer-events-none" />
                <select
                  value={statusFilter}
                  onChange={e => { setStatusFilter(e.target.value); setCurrentPage(1); }}
                  className="h-9 appearance-none rounded-md border border-hairline bg-bg-1 pl-8 pr-8 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
                >
                  <option value="all">Tous les statuts</option>
                  <option value="finished">Succès</option>
                  <option value="failed">Échec</option>
                  <option value="running">En cours</option>
                  <option value="stopping">Arrêt…</option>
                  <option value="archived">Archivé</option>
                  <option value="restarting_oom">Restart OOM</option>
                </select>
              </div>

              <div className="flex items-center gap-1.5">
                <Calendar className="h-4 w-4 text-ink-3" />
                <Input
                  type="date"
                  value={startDate}
                  onChange={e => { setStartDate(e.target.value); setCurrentPage(1); }}
                  className="w-[130px]"
                />
                <span className="text-ink-3 text-sm">→</span>
                <Input
                  type="date"
                  value={endDate}
                  onChange={e => { setEndDate(e.target.value); setCurrentPage(1); }}
                  className="w-[130px]"
                />
                {hasDateFilter && (
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => { setStartDate(''); setEndDate(''); setCurrentPage(1); }}
                    aria-label="Effacer les dates"
                    title="Effacer les dates"
                  >
                    <X className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </div>

            {totalPages > 1 && (
              <div className="flex items-center justify-between border-t border-hairline pt-2 text-sm text-ink-3">
                <span className="font-mono">{filteredJobs.length} jobs</span>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                    aria-label="Page précédente"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <div className="flex items-center gap-1.5">
                    <span className="hidden sm:inline text-xs">Page</span>
                    <Input
                      type="number"
                      min="1"
                      max={totalPages}
                      value={currentPage}
                      onChange={(e) => {
                        const val = parseInt(e.target.value);
                        if (!isNaN(val) && val >= 1 && val <= totalPages) {
                          setCurrentPage(val);
                        }
                      }}
                      className="h-8 w-14 px-2 text-center font-mono"
                    />
                    <span className="text-xs text-ink-3">/ {totalPages}</span>
                  </div>
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                    aria-label="Page suivante"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </div>

          {/* Jobs rows */}
          <div className="divide-y divide-hairline max-h-[600px] overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <RefreshCw className="h-6 w-6 animate-spin text-accent" />
              </div>
            ) : paginatedJobs.length === 0 ? (
              <div className="p-8 text-center text-ink-2 text-sm">
                Aucun job à afficher.
              </div>
            ) : (
              paginatedJobs.map(job => (
                <div
                  key={job.id}
                  onClick={() => handleSelectJob(job.id)}
                  className={cn(
                    'flex items-center gap-4 px-5 py-3 hover:bg-bg-2 transition-colors cursor-pointer border-l-2',
                    selectedJobId === job.id
                      ? 'bg-accent-soft border-accent'
                      : 'border-transparent'
                  )}
                >
                  <Pill tone={JOB_TONE[job.status] ?? 'neutral'}>{job.status}</Pill>
                  <span className="flex-1 text-[13px] text-ink-0 truncate font-mono">{job.domain}</span>
                  <span className="text-[11px] text-ink-3 tabular-nums font-mono">
                    {job.start_time
                      ? new Date(job.start_time).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' })
                      : '—'}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* ── Job detail panel (1fr) ── */}
        <div
          className={cn(
            'bg-surface rounded-lg border border-hairline shadow-sm',
            paginatedJobs.length === 0 && 'hidden md:hidden',
            !selectedJob && !loadingDetails && paginatedJobs.length > 0 && 'flex items-center justify-center'
          )}
        >
          {loadingDetails ? (
            <div className="flex items-center justify-center py-20 p-5">
              <RefreshCw className="h-10 w-10 animate-spin text-accent" />
            </div>
          ) : paginatedJobs.length === 0 ? null : selectedJob ? (
            <div className="p-5 overflow-y-auto">
              <JobDetails
                job={selectedJob}
                onToggleRaw={() => setShowRaw(!showRaw)}
                showRaw={showRaw}
                token={token}
                onSelectJob={handleSelectJob}
                inline
              />
            </div>
          ) : (
            <div className="flex items-center justify-center h-full p-8 text-ink-2 text-sm">
              Sélectionnez un job pour voir les détails
            </div>
          )}
        </div>
      </div>

      <Outlet />
    </div>
  );
};

export default Overview;
