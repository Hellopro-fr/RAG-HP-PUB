import { Link } from 'react-router-dom';
import {
  XCircle, Code, Server, Clock, CheckCircle, AlertCircle, Play,
} from 'lucide-react';
import StatCard from './StatCard';
import ErrorVisualization from './ErrorVisualization';
import AdvancedLogViewer from './AdvancedLogViewer';
import JobPerformance from './JobPerformance';
import { Button } from './ui/button';
import { cn } from '../lib/utils';

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
      <div className="py-12 text-center">
        <XCircle className="mx-auto mb-3 h-12 w-12 text-destructive" />
        <p className="mb-2 text-base text-destructive">Erreur lors du chargement des détails</p>
        <p className="text-sm text-muted-foreground">{job.error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-mono text-xl font-bold tracking-tight text-foreground">#{job.id}</h2>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            {job.domain && <span className="text-sm text-muted-foreground">{job.domain}</span>}
            {job.crawl_mode && (
              <span
                className={cn(
                  'rounded px-1.5 py-0.5 text-[10px] font-medium',
                  job.crawl_mode === 'update' ? 'bg-primary/15 text-primary' : 'bg-info/15 text-info'
                )}
              >
                {job.crawl_mode === 'update' ? 'Mode Update' : 'Mode Standard'}
              </span>
            )}
            {job.previous_crawl_id && (
              onSelectJob ? (
                <button
                  onClick={() => onSelectJob(job.previous_crawl_id)}
                  className="font-mono text-xs text-primary underline decoration-dotted hover:text-primary/80"
                  title="Voir le job précédent (chaîne de retries)"
                >
                  ← prev: {job.previous_crawl_id}
                </button>
              ) : (
                <span className="font-mono text-xs text-muted-foreground">prev: {job.previous_crawl_id}</span>
              )
            )}
            {job.oom_restart_count > 0 && (
              <span className="rounded bg-warning/15 px-1.5 py-0.5 text-[10px] font-medium text-warning">
                {job.oom_restart_count} OOM restart{job.oom_restart_count > 1 ? 's' : ''}
              </span>
            )}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" asChild>
            <Link to={`/jobs/${job.id}/queue`}>
              <Code className="h-4 w-4" />
              Queue
            </Link>
          </Button>
          <Button variant="outline" size="sm" asChild>
            <Link to={`/jobs/${job.id}/dataset`}>
              <Server className="h-4 w-4" />
              Dataset
            </Link>
          </Button>
          <Button variant="outline" size="sm" asChild>
            <Link to={`/jobs/${job.id}/replay`} title="Rejouer l'évolution CPU/RAM du crawl">
              <Play className="h-4 w-4" />
              Replay
            </Link>
          </Button>
          <Button variant="secondary" size="sm" onClick={onToggleRaw}>
            <Code className="h-4 w-4" />
            {showRaw ? 'Vue Avancée' : 'Logs Bruts'}
          </Button>
        </div>
      </div>

      <JobPerformance
        token={token}
        jobId={job.id}
        isRunning={['running', 'stopping', 'restarting_oom'].includes((job.status || '').toLowerCase())}
      />

      {showRaw ? (
        <AdvancedLogViewer content={job.rawContent || 'Contenu brut non disponible.'} jobId={job.id} />
      ) : !job.hasStats && !job.stats ? (
        <div className="py-12 text-center text-muted-foreground">
          <Clock className="mx-auto mb-3 h-10 w-10 animate-spin" />
          <p className="mb-1 text-base">Les statistiques détaillées ne sont pas encore disponibles.</p>
          <p className="text-sm">Le job est peut-être en cours d'exécution ou le fichier de log n'est pas encore complet.</p>
          <Button className="mt-4" onClick={onToggleRaw}>
            Voir les logs avancés
          </Button>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatCard title="Total Requêtes" value={job.stats.requestsTotal || 0}    icon={Server}      variant="info" />
            <StatCard title="Succès"         value={job.stats.requestsFinished || 0} icon={CheckCircle} variant="success" />
            <StatCard title="Échecs"         value={job.stats.requestsFailed || 0}   icon={XCircle}     variant="destructive" />
            <StatCard
              title="Durée"
              value={`${((job.stats.crawlerRuntimeMillis || 0) / 1000).toFixed(2)}s`}
              icon={Clock}
              variant="default"
            />
          </div>

          {job.errors && job.errors.length > 0 && (
            <>
              <ErrorVisualization errors={job.errors} />
              <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3">
                <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-destructive">
                  <AlertCircle className="h-4 w-4" />
                  Erreurs ({job.errors.length})
                </h3>
                <div className="max-h-40 space-y-1.5 overflow-y-auto font-mono text-xs text-destructive/90">
                  {job.errors.slice(0, 10).map((e, i) => (
                    <p key={i} className="rounded bg-destructive/10 p-2">{e}</p>
                  ))}
                  {job.errors.length > 10 && (
                    <p className="italic text-muted-foreground">
                      … et {job.errors.length - 10} autres erreurs
                    </p>
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
