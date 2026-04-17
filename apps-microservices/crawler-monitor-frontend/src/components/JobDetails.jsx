import { Link } from 'react-router-dom';
import {
  XCircle, Code, Server, Clock, CheckCircle, AlertCircle, Play
} from 'lucide-react';
import StatCard from './StatCard';
import ErrorVisualization from './ErrorVisualization';
import AdvancedLogViewer from './AdvancedLogViewer';
import JobPerformance from './JobPerformance';

/**
 * JobDetails — right panel of the Overview.
 *
 * Queue and Dataset are now sub-routes (/jobs/:id/queue, /jobs/:id/dataset)
 * rather than internal modals. Their <Outlet/> is rendered by Overview.
 */
const JobDetails = ({ job, onToggleRaw, showRaw, onSelectJob, token }) => {
  if (!job) return null;
  if (job.error) {
    return (
      <div className="text-center py-12">
        <XCircle className="w-16 h-16 mx-auto mb-4 text-red-400" />
        <p className="text-red-400 text-lg mb-2">Erreur lors du chargement des détails</p>
        <p className="text-gray-400 text-sm">{job.error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-start">
        <div>
          <h2 className="text-2xl font-bold text-white">Job #{job.id}</h2>
          <div className="flex items-center gap-3 mt-1 flex-wrap">
            {job.domain && <span className="text-sm text-gray-400">{job.domain}</span>}
            {job.crawl_mode && (
              <span className={`text-xs px-2 py-0.5 rounded ${
                job.crawl_mode === 'update' ? 'bg-purple-500/20 text-purple-400' : 'bg-blue-500/20 text-blue-400'
              }`}>
                {job.crawl_mode === 'update' ? 'Mode Update' : 'Mode Standard'}
              </span>
            )}
            {job.previous_crawl_id && (
              onSelectJob ? (
                <button
                  onClick={() => onSelectJob(job.previous_crawl_id)}
                  className="text-xs text-blue-400 hover:text-blue-300 underline decoration-dotted"
                  title="Voir le job précédent (chaîne de retries)"
                >
                  ← prev: {job.previous_crawl_id}
                </button>
              ) : (
                <span className="text-xs text-gray-500">prev: {job.previous_crawl_id}</span>
              )
            )}
            {job.oom_restart_count > 0 && (
              <span className="text-xs px-2 py-0.5 rounded bg-orange-500/20 text-orange-400">
                {job.oom_restart_count} OOM restart{job.oom_restart_count > 1 ? 's' : ''}
              </span>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          <Link
            to={`/jobs/${job.id}/queue`}
            className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors text-white"
          >
            <Code className="w-4 h-4" />
            Explorer la Queue
          </Link>
          <Link
            to={`/jobs/${job.id}/dataset`}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors text-white"
          >
            <Server className="w-4 h-4" />
            Analyser Dataset
          </Link>
          <Link
            to={`/jobs/${job.id}/replay`}
            className="flex items-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-700 rounded-lg transition-colors text-white"
            title="Rejouer l'évolution CPU/RAM du crawl"
          >
            <Play className="w-4 h-4" />
            Replay
          </Link>
          <button
            onClick={onToggleRaw}
            className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors text-white"
          >
            <Code className="w-4 h-4" />
            {showRaw ? 'Vue Avancée' : 'Logs Bruts'}
          </button>
        </div>
      </div>

      {/* Performance chart — ALWAYS visible regardless of log stats.
          Data comes from heartbeats (independent of CrawlingStats in the log).
          Polling stops once the job is terminal to save bandwidth + CPU. */}
      <JobPerformance
        token={token}
        jobId={job.id}
        isRunning={['running', 'stopping', 'restarting_oom'].includes((job.status || '').toLowerCase())}
      />

      {showRaw ? (
        <AdvancedLogViewer content={job.rawContent || "Contenu brut non disponible."} jobId={job.id} />
      ) : !job.hasStats && !job.stats ? (
        <div className="text-center py-12 text-gray-400">
          <Clock className="w-12 h-12 mx-auto mb-4 animate-spin" />
          <p className="text-lg mb-2">Les statistiques détaillées ne sont pas encore disponibles.</p>
          <p className="text-sm">Le job est peut-être en cours d'exécution ou le fichier de log n'est pas encore complet.</p>
          <button
            onClick={onToggleRaw}
            className="mt-4 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white"
          >
            Voir les logs avancés
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard title="Total Requêtes" value={job.stats.requestsTotal || 0} icon={Server} color="blue" />
            <StatCard title="Succès" value={job.stats.requestsFinished || 0} icon={CheckCircle} color="green" />
            <StatCard title="Échecs" value={job.stats.requestsFailed || 0} icon={XCircle} color="red" />
            <StatCard title="Durée" value={`${((job.stats.crawlerRuntimeMillis || 0) / 1000).toFixed(2)}s`} icon={Clock} color="purple" />
          </div>

          {job.errors && job.errors.length > 0 && (
            <>
              <ErrorVisualization errors={job.errors} warnings={job.warnings || []} />
              <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-4">
                <h3 className="text-red-400 font-semibold mb-2 flex items-center gap-2">
                  <AlertCircle className="w-5 h-5" />
                  Erreurs ({job.errors.length})
                </h3>
                <div className="max-h-40 overflow-y-auto space-y-2 font-mono text-sm text-red-300">
                  {job.errors.slice(0, 10).map((e, i) => <p key={i} className="p-2 bg-red-900/30 rounded">{e}</p>)}
                  {job.errors.length > 10 && (
                    <p className="text-gray-400 italic">... et {job.errors.length - 10} autres erreurs</p>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};

export default JobDetails;