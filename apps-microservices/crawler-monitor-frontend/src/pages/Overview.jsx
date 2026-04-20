import { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Outlet } from 'react-router-dom';
import {
  RefreshCw, Server, CheckCircle, XCircle, Zap, Archive,
  Search, Filter, Calendar, ChevronLeft, ChevronRight, TrendingUp, X,
} from 'lucide-react';
import { JOBS_PER_PAGE } from '../lib/constants';
import { useJobsQuery, useCapacityQuery, useJobDetailsQuery } from '../hooks/queries';
import StatCard from '../components/StatCard';
import ReplicaMonitor from '../components/ReplicaMonitor';
import JobCard from '../components/JobCard';
import JobDetails from '../components/JobDetails';
import CapacityBar from '../components/CapacityBar';
import Timeline from '../components/Timeline';
import AlertsBanner from '../components/AlertsBanner';
import { Card } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Button } from '../components/ui/button';
import { cn } from '../lib/utils';

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

  const detailsPanelRef = useRef(null);
  const jobsListRef = useRef(null);

  // Stable callbacks — important for React.memo on Timeline / CapacityBar /
  // JobCard list. A new function identity each render would defeat memo and
  // force downstream Recharts re-renders.
  const handleSelectJob = useCallback((id) => {
    if (!id || id === 'undefined' || id === 'null') return;
    navigate(`/jobs/${id}`);
  }, [navigate]);

  // Auto-scroll to the details panel when a job is selected.
  // `block: 'start'` aligne le haut du panneau avec le top du viewport — sur
  // mobile où la liste et le détail sont empilés, `nearest` pouvait laisser
  // l'utilisateur regarder une zone vide. On force un scroll utile.
  useEffect(() => {
    if (routeJobId && detailsPanelRef.current) {
      detailsPanelRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [routeJobId]);

  // Click sur un bucket Timeline : filtre par date ET scroll vers la liste
  // jobs filtrée — sinon l'utilisateur voit que la Timeline et doit scroller
  // pour voir le résultat du filtrage.
  const handleTimelineBucketClick = useCallback(({ from, to }) => {
    const fromDate = new Date(from);
    const toDate = new Date(to - 1);
    const yyyymmdd = (d) => `${d.getFullYear()}-${(d.getMonth()+1).toString().padStart(2,'0')}-${d.getDate().toString().padStart(2,'0')}`;
    setStartDate(yyyymmdd(fromDate));
    setEndDate(yyyymmdd(toDate));
    setCurrentPage(1);
    // Defer le scroll au prochain tick pour que la liste filtrée soit rendue
    setTimeout(() => {
      jobsListRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 0);
  }, []);

  const hasDateFilter = !!(startDate || endDate);

  return (
    <div className="p-4 space-y-4">
      <AlertsBanner token={token} />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <StatCard title="Total"    value={globalStats.total}    icon={Server}      variant="default" />
        <StatCard title="Succès"   value={globalStats.finished} icon={CheckCircle} variant="success" />
        <StatCard title="Échecs"   value={globalStats.failed}   icon={XCircle}     variant="destructive" />
        <StatCard title="En cours" value={globalStats.running}  icon={Zap}         variant="info" />
        <StatCard title="Archivés" value={globalStats.archived} icon={Archive}     variant="default" />
      </div>

      <Timeline token={token} onBucketClick={handleTimelineBucketClick} />

      <CapacityBar capacity={capacity} token={token} />

      <ReplicaMonitor replicas={replicas} token={token} />

      {/* Filters + pagination */}
      <Card className="p-3 space-y-3">
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
          <div className="flex items-center justify-between border-t border-border pt-2 text-sm text-muted-foreground">
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
      </Card>

      {/* Jobs list + details */}
      <div ref={jobsListRef} className="grid gap-4 lg:grid-cols-[minmax(280px,1fr)_2fr]">
        <Card className="p-2 space-y-2 max-h-[calc(100vh-22rem)] overflow-y-auto">
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
              <JobCard
                key={job.id}
                job={job}
                onClick={() => handleSelectJob(job.id)}
                isSelected={routeJobId === job.id}
              />
            ))
          )}
        </Card>

        <Card ref={detailsPanelRef} className={cn('p-5', !selectedJob && !loadingDetails && 'flex items-center justify-center')}>
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
        </Card>
      </div>

      <Outlet />
    </div>
  );
};

export default Overview;
