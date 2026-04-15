import {
  CheckCircle, XCircle, Clock, AlertTriangle, RefreshCw, Archive, RotateCcw
} from 'lucide-react';

const JobCard = ({ job, onClick, isSelected }) => {
  const getStatusInfo = (job) => {
    const status = job.status || 'pending';
    switch (status.toLowerCase()) {
      case 'running': return { color: 'blue', text: 'En cours', icon: RefreshCw, spin: true };
      case 'finished': return { color: 'green', text: 'Succès', icon: CheckCircle };
      case 'failed': return { color: 'red', text: 'Échec', icon: XCircle };
      case 'stopping': return { color: 'yellow', text: 'Arrêt...', icon: AlertTriangle };
      case 'archived': return { color: 'gray', text: 'Archivé', icon: Archive };
      case 'restarting_oom': return { color: 'orange', text: 'Restart OOM', icon: RotateCcw, spin: true };
      default: return { color: 'gray', text: status, icon: Clock };
    }
  };

  const status = getStatusInfo(job);
  const StatusIcon = status.icon;

  // Override left border to orange when job had OOM restarts (visual fragility cue)
  const oomCount = job.oom_restart_count || 0;
  const borderClass = isSelected
    ? 'border-blue-500 bg-gray-700 shadow-lg'
    : oomCount > 0
      ? 'border-orange-500'
      : `border-${status.color}-500`;

  const hasMeta = job.crawl_mode === 'update' || oomCount > 0 || job.previous_crawl_id;

  return (
    <div
      onClick={onClick}
      className={`bg-gray-800 rounded-lg p-4 cursor-pointer hover:bg-gray-700 border-l-4 transition-all ${borderClass}`}
    >
      <div className="flex justify-between items-start">
        <div className="min-w-0 flex-1">
          <p className="text-white font-semibold truncate">Job #{job.id}</p>
          <p className="text-gray-400 text-sm truncate">{job.domain}</p>
        </div>
        <div className="flex-shrink-0 flex items-center gap-2">
          <span className={`px-2 py-0.5 rounded text-xs font-medium bg-${status.color}-500/20 text-${status.color}-400`}>
            {status.text}
          </span>
          <StatusIcon className={`w-5 h-5 text-${status.color}-400 ${status.spin ? 'animate-spin' : ''}`} />
        </div>
      </div>
      {hasMeta && (
        <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
          {job.crawl_mode === 'update' && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-400" title="Crawl incrémental (update)">
              ↻ update
            </span>
          )}
          {oomCount > 0 && (
            <span
              className="text-[10px] px-1.5 py-0.5 rounded bg-orange-500/20 text-orange-400 font-semibold"
              title={`${oomCount} redémarrage${oomCount > 1 ? 's' : ''} après OOM`}
            >
              {oomCount}× OOM
            </span>
          )}
          {job.previous_crawl_id && (
            <span
              className="text-[10px] text-gray-500"
              title={`Retry de ${job.previous_crawl_id}`}
            >
              ↩
            </span>
          )}
        </div>
      )}
      <p className="mt-3 text-xs text-gray-500">{new Date(job.start_time).toLocaleString('fr-FR')}</p>
    </div>
  );
};

export default JobCard;