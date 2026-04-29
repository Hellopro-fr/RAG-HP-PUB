import { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Outlet } from 'react-router-dom';
import {
  RefreshCw, Server, TrendingUp,
  Search, Filter, Calendar, ChevronLeft, ChevronRight, X,
} from 'lucide-react';
import { JOBS_PER_PAGE } from '../lib/constants';
import { useJobsQuery, useCapacityQuery, useJobDetailsQuery } from '../hooks/queries';
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

/**
 * Overview page (`/` and `/jobs/:id`).
 *
 * Data via React Query hooks; no manual fetching here.
 * `replicas` still comes from props (it is WebSocket-only, lives in App.jsx).
 */
const Overview = ({ token, replicas }) => {
  const { id: routeJobId } = useParams();
  const navigate = useNavigate();

  // Local UI state (filters, pagination, raw-log toggle)
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [showRaw, setShowRaw] = useState(false);

  // Data layer
  const jobsQuery = useJobsQuery(token);
  const allJobs = jobsQuery.data || [];
  const loading = jobsQuery.isLoading;

  const capacityQuery = useCapacityQuery(token);
  const capacity = capacityQuery.data || null;

  const detailsQuery = useJobDetailsQuery(token, routeJobId);
  const selectedJob = routeJobId
    ? (detailsQuery.data ?? (detailsQuery.error ? { id: routeJobId, error: detailsQuery.error.message } : null))
    : null;
  const loadingDetails = !!routeJobId && detailsQuery.isLoading;

  const filteredJobs = useMemo(() => {
    return allJobs.filter(job => {
      // Skip malformed entries — protects every onClick / Link from emitting
      // /jobs/undefined navigations.
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
    const finished = filteredJobs.filter(j => j.status === 'finished').length;
    const failed = filteredJobs.filter(j => j.status === 'failed').length;
    const running = filteredJobs.filter(j => j.status === 'running').length;
    const archived = filteredJobs.filter(j => j.status === 'archived').length;
    return { finished, failed, running, archived, total: filteredJobs.length };
  }, [filteredJobs]);

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

  const detailsPanelRef = useRef(null);
  const jobsListRef = useRef(null);

  // Stable callbacks — important for React.memo on child components.
  // A new function identity each render would defeat memo.
  const handleSelectJob = useCallback((id) => {
    if (!id || id === 'undefined' || id === 'null') return;
    navigate(`/jobs/${id}`);
  }, [navigate]);

  // Auto-scroll to the details panel when a job is selected.
  useEffect(() => {
    if (routeJobId && detailsPanelRef.current) {
      detailsPanelRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [routeJobId]);

  const hasDateFilter = !!(startDate || endDate);

  return (
    <div className="p-4 flex flex-col gap-6 max-w-[1400px]">
      <AlertsBanner token={token} />

      {/* Hero */}
      <div>
        <h1 className="font-display text-[26px] font-semibold text-ink-0 tracking-[-0.025em]">Vue d&apos;ensemble</h1>
      </div>

      {/* 5 StatTiles */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        <StatTile label="Total"    value={loading ? null : String(globalStats.total)} />
        <StatTile label="Succès"   value={loading ? null : String(globalStats.finished)} deltaTone="ok" />
        <StatTile
          label="Échecs"
          value={loading ? null : String(globalStats.failed)}
          deltaTone={globalStats.failed > 0 ? 'err' : 'ok'}
        />
        <div className="relative">
          <StatTile label="En cours" value={loading ? null : String(globalStats.running)} />
          <div className="absolute right-2 top-2">
            <CoherencePastille ruleId="running_count_parity" />
          </div>
        </div>
        <StatTile label="Archivés" value={loading ? null : String(globalStats.archived)} />
      </div>

      {/* Timeline + Capacity */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_200px]">
        <div className="bg-surface rounded-lg border border-hairline p-5 shadow-sm">
          <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-2 mb-4">Activité</p>
          <UiTimeline data={timelineData} />
        </div>
        <div className="bg-surface rounded-lg border border-hairline p-5 shadow-sm flex flex-col items-center gap-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-2">Capacité</p>
          <CapacityRing
            used={capacity?.ram_used ?? capacity?.used ?? 0}
            total={capacity?.ram_total ?? capacity?.total ?? 1}
            label="RAM"
          />
        </div>
      </div>

      {/* Replicas grid */}
      {replicas?.length > 0 && (
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-2 mb-3">
            Réplicas ({replicas.length})
          </p>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {replicas.map(r => (
              <div key={r.id ?? r.name} className="bg-surface rounded-lg border border-hairline p-4 shadow-sm">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[12px] font-medium text-ink-0 font-mono truncate">{r.name ?? r.id}</span>
                  <Pill
                    tone={
                      r.status === 'idle' ? 'neutral'
                      : r.status === 'busy' || r.status === 'running' ? 'accent'
                      : r.status === 'error' ? 'err'
                      : 'ok'
                    }
                    dot
                  >
                    {r.status}
                  </Pill>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Jobs list + filters */}
      {/* scroll-mt-16 = marge de 64px pour que scrollIntoView ne cache pas
          le haut du bloc sous la Topbar sticky (h-14 = 56px). */}
      <div ref={jobsListRef} className="bg-surface rounded-lg border border-hairline shadow-sm overflow-hidden scroll-mt-16">
        {/* Toolbar */}
        <div className="px-5 py-4 border-b border-hairline space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-[13px] font-semibold text-ink-0">Jobs ({filteredJobs.length})</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative flex-grow min-w-[200px]">
              <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                type="text"
                placeholder="Filtrer par ID ou domaine…"
                value={searchTerm}
                onChange={e => { setSearchTerm(e.target.value); setCurrentPage(1); }}
                className="pl-8"
              />
            </div>

            <div className="relative">
              <Filter className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground pointer-events-none" />
              <select
                value={statusFilter}
                onChange={e => { setStatusFilter(e.target.value); setCurrentPage(1); }}
                className="h-9 appearance-none rounded-md border border-input bg-background pl-8 pr-8 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
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
              <Calendar className="h-4 w-4 text-muted-foreground" />
              <Input
                type="date"
                value={startDate}
                onChange={e => { setStartDate(e.target.value); setCurrentPage(1); }}
                className="w-[150px]"
              />
              <span className="text-muted-foreground text-sm">→</span>
              <Input
                type="date"
                value={endDate}
                onChange={e => { setEndDate(e.target.value); setCurrentPage(1); }}
                className="w-[150px]"
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
            <div className="flex items-center justify-between border-t border-hairline pt-2 text-sm text-muted-foreground">
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
                  <span className="text-xs text-muted-foreground">/ {totalPages}</span>
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
        <div className="divide-y divide-hairline">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <RefreshCw className="h-6 w-6 animate-spin text-primary" />
            </div>
          ) : paginatedJobs.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground">
              <Server className="mx-auto mb-3 h-10 w-10 opacity-50" />
              <p className="text-sm">Aucun job trouvé</p>
            </div>
          ) : (
            paginatedJobs.map(job => (
              <div
                key={job.id}
                onClick={() => handleSelectJob(job.id)}
                className={cn(
                  'flex items-center gap-4 px-5 py-3 hover:bg-bg-2 transition-colors cursor-pointer',
                  routeJobId === job.id && 'bg-bg-2'
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

      {/* Job detail panel — s'ouvre quand un job est sélectionné */}
      {routeJobId && (
        <div
          ref={detailsPanelRef}
          className={cn(
            'bg-surface rounded-lg border border-hairline shadow-sm p-5 scroll-mt-16',
            !selectedJob && !loadingDetails && 'flex items-center justify-center'
          )}
        >
          {loadingDetails ? (
            <div className="flex items-center justify-center py-20">
              <RefreshCw className="h-10 w-10 animate-spin text-primary" />
            </div>
          ) : selectedJob ? (
            <JobDetails
              job={selectedJob}
              onToggleRaw={() => setShowRaw(!showRaw)}
              showRaw={showRaw}
              token={token}
              onSelectJob={handleSelectJob}
            />
          ) : (
            <div className="text-center text-muted-foreground py-16">
              <TrendingUp className="mx-auto mb-3 h-12 w-12 opacity-50" />
              <p className="text-base">Sélectionnez un job pour voir les détails</p>
              <p className="text-xs mt-1.5">Cliquez sur un job dans la liste</p>
            </div>
          )}
        </div>
      )}

      <Outlet />
    </div>
  );
};

export default Overview;
