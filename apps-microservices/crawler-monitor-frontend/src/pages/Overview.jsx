import { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate, Outlet } from 'react-router-dom';
import {
  RefreshCw, Server, CheckCircle, XCircle, Zap, Archive,
  Search, Filter, Calendar, ChevronLeft, ChevronRight, TrendingUp,
} from 'lucide-react';
import { JOBS_PER_PAGE } from '../lib/constants';
import StatCard from '../components/StatCard';
import ReplicaMonitor from '../components/ReplicaMonitor';
import JobCard from '../components/JobCard';
import JobDetails from '../components/JobDetails';
import CapacityBar from '../components/CapacityBar';

/**
 * Overview page (`/` and `/jobs/:id`).
 *
 * Renders the full dashboard:
 *  - 5 KPI cards
 *  - Capacity bar
 *  - Replica monitor
 *  - Filters
 *  - Split view: paginated job list (left) | selected job details (right)
 *
 * The currently-selected job is driven by the `:id` URL param:
 *   `/`                   → no job selected, right panel shows the empty placeholder
 *   `/jobs/c8f2`          → loads & shows job c8f2 in the right panel
 *
 * This is NOT yet React Query — that migration is W3.1. For now, props provide
 * the data fetched centrally by App.jsx so the WebSocket-driven refresh keeps
 * working unchanged.
 */
const Overview = ({
  token,
  allJobs,
  loading,
  capacity,
  replicas,
  selectedJob,
  loadingDetails,
  showRaw,
  setShowRaw,
  fetchJobDetails,
  clearSelectedJob,
}) => {
  const { id: routeJobId } = useParams();
  const navigate = useNavigate();

  // Local UI state (filters, pagination)
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [currentPage, setCurrentPage] = useState(1);

  // URL → state sync: load job details when the URL :id changes
  useEffect(() => {
    if (routeJobId) {
      fetchJobDetails(routeJobId);
    } else {
      clearSelectedJob();
    }
  }, [routeJobId, fetchJobDetails, clearSelectedJob]);

  const filteredJobs = useMemo(() => {
    return allJobs.filter(job => {
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
        job.id.includes(searchTerm) ||
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

  const handleSelectJob = (id) => navigate(`/jobs/${id}`);

  return (
    <main className="container mx-auto p-4 space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <StatCard title="Total" value={globalStats.total} icon={Server} color="gray" />
        <StatCard title="Succès" value={globalStats.finished} icon={CheckCircle} color="green" />
        <StatCard title="Échecs" value={globalStats.failed} icon={XCircle} color="red" />
        <StatCard title="En cours" value={globalStats.running} icon={Zap} color="blue" />
        <StatCard title="Archivés" value={globalStats.archived} icon={Archive} color="gray" />
      </div>

      <CapacityBar capacity={capacity} token={token} />

      <ReplicaMonitor replicas={replicas} />

      <div className="bg-gray-800 p-3 rounded-lg space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-grow min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
            <input
              type="text"
              placeholder="Filtrer par ID ou domaine..."
              value={searchTerm}
              onChange={e => { setSearchTerm(e.target.value); setCurrentPage(1); }}
              className="w-full bg-gray-900 border border-gray-700 rounded-md pl-10 pr-4 py-2 focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
          </div>
          <div className="relative">
            <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
            <select
              value={statusFilter}
              onChange={e => { setStatusFilter(e.target.value); setCurrentPage(1); }}
              className="bg-gray-900 border border-gray-700 rounded-md pl-10 pr-4 py-2 appearance-none focus:ring-2 focus:ring-blue-500 focus:outline-none"
            >
              <option value="all">Tous les statuts</option>
              <option value="finished">Succès</option>
              <option value="failed">Échec</option>
              <option value="running">En cours</option>
              <option value="stopping">Arrêt...</option>
              <option value="archived">Archivé</option>
              <option value="restarting_oom">Restart OOM</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <Calendar className="w-5 h-5 text-gray-500" />
            <input
              type="date"
              value={startDate}
              onChange={e => { setStartDate(e.target.value); setCurrentPage(1); }}
              className="bg-gray-900 border border-gray-700 rounded-md px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:outline-none text-sm"
            />
            <span className="text-gray-500">à</span>
            <input
              type="date"
              value={endDate}
              onChange={e => { setEndDate(e.target.value); setCurrentPage(1); }}
              className="bg-gray-900 border border-gray-700 rounded-md px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:outline-none text-sm"
            />
            {(startDate || endDate) && (
              <button
                onClick={() => { setStartDate(''); setEndDate(''); setCurrentPage(1); }}
                className="px-3 py-2 bg-red-600 hover:bg-red-700 rounded-md text-sm text-white transition-colors"
              >
                ✕
              </button>
            )}
          </div>
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-between text-sm text-gray-400 pt-2 border-t border-gray-700">
            <span>{filteredJobs.length} jobs trouvés</span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <div className="flex items-center gap-2">
                <span className="hidden sm:inline">Page</span>
                <input
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
                  className="w-16 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-center focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
                <span className="text-gray-500">/ {totalPages}</span>
              </div>
              <button
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="flex gap-4 items-start">
        <div className="w-1/3 space-y-3 max-h-[calc(100vh-20rem)] overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <RefreshCw className="w-8 h-8 animate-spin text-blue-400" />
            </div>
          ) : paginatedJobs.length === 0 ? (
            <div className="text-center py-12 text-gray-400">
              <Server className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>Aucun job trouvé</p>
            </div>
          ) : (
            paginatedJobs.map(job => (
              <JobCard
                key={job.id}
                job={job}
                onClick={() => handleSelectJob(job.id)}
                isSelected={selectedJob?.id === job.id || routeJobId === job.id}
              />
            ))
          )}
        </div>

        <div className="flex-1 bg-gray-800 rounded-lg p-6">
          {loadingDetails ? (
            <div className="flex items-center justify-center py-20">
              <RefreshCw className="w-12 h-12 animate-spin text-blue-400" />
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
            <div className="text-center py-20 text-gray-400">
              <TrendingUp className="w-16 h-16 mx-auto mb-4 opacity-50" />
              <p className="text-lg">Sélectionnez un job pour voir les détails</p>
              <p className="text-sm mt-2">Cliquez sur un job dans la liste de gauche</p>
            </div>
          )}
        </div>
      </div>

      {/* Sub-routes (queue/dataset) render here as full-screen overlays */}
      <Outlet />
    </main>
  );
};

export default Overview;