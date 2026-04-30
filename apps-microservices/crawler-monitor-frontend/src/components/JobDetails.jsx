import { useState } from 'react';
import { Link } from 'react-router-dom';
import { XCircle, Clock, ChevronLeft } from 'lucide-react';
import AdvancedLogViewer from './AdvancedLogViewer';
import { Button } from './ui/button';
import Pill from './ui/Pill';
import AreaChart from './ui/AreaChart';
import LogLine from './ui/LogLine';
import KV from './ui/KV';
import { useJobPerformanceQuery } from '../hooks/queries';

/* ── helpers ──────────────────────────────────────────────────────────────── */

const RUNNING_STATUSES = ['running', 'stopping', 'restarting_oom'];

function statusTone(status) {
  const s = (status || '').toLowerCase();
  if (RUNNING_STATUSES.includes(s) || s === 'finished') return 'ok';
  if (s === 'failed') return 'err';
  return 'neutral';
}

function formatDuration(ms) {
  if (ms == null) return null;
  const totalSec = Math.floor(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function formatBytes(bytes) {
  if (bytes == null) return null;
  return (bytes / 1024 / 1024).toFixed(1) + ' MB';
}

/* ── KPI Strip ────────────────────────────────────────────────────────────── */

function KpiCell({ label, value }) {
  return (
    <div className="px-4 py-3 border-r border-hairline last:border-r-0">
      <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-ink-3 mb-1">{label}</div>
      <div className="text-[22px] font-semibold tracking-[-0.025em] tabular-nums text-ink-0 font-display">
        {value ?? '—'}
      </div>
    </div>
  );
}

/* ── Tab button ───────────────────────────────────────────────────────────── */

function TabBtn({ label, active, onClick }) {
  return (
    <button
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={
        'px-3 py-2 text-[13px] cursor-pointer -mb-px ' +
        (active
          ? 'border-b-2 border-accent text-ink-0 font-medium'
          : 'text-ink-2 hover:text-ink-1')
      }
    >
      {label}
    </button>
  );
}

/* ── Main component ───────────────────────────────────────────────────────── */

const TABS = ['Logs', 'Queue', 'Dataset', 'Replay', 'Metrics', 'Callbacks'];

const JobDetails = ({ job, onToggleRaw, showRaw, onSelectJob, token }) => {
  const [activeTab, setActiveTab] = useState('Logs');

  /* Performance data — always call hook (Rules of Hooks) */
  const isRunning = RUNNING_STATUSES.includes((job?.status || '').toLowerCase());
  const perfQuery = useJobPerformanceQuery(token, job?.id, {
    refetchInterval: isRunning ? 15000 : false,
  });

  if (!job) return null;

  /* error state */
  if (job.error) {
    return (
      <div className="py-12 text-center">
        <XCircle className="mx-auto mb-3 h-12 w-12 text-err" />
        <p className="mb-2 text-[13px] text-err">Erreur lors du chargement des détails</p>
        <p className="text-[13px] text-ink-2">{job.error}</p>
      </div>
    );
  }

  const tone = statusTone(job.status);

  /* KPI values */
  const stats = job.stats;
  const throughput =
    stats && stats.crawlerRuntimeMillis > 0
      ? (stats.requestsFinished / (stats.crawlerRuntimeMillis / 1000)).toFixed(1) + '/s'
      : null;

  /* Performance chart data */
  const perfData = perfQuery.data;
  const ramData = perfData?.points?.map((p) => p.ram / 1024 / 1024) ?? [];
  const cpuData = perfData?.points?.map((p) => p.cpu * 100) ?? [];
  const maxRamMb = perfData?.summary?.total_ram
    ? perfData.summary.total_ram / 1024 / 1024
    : undefined;

  /* ── render ──────────────────────────────────────────────────────────── */
  return (
    <div>
      {/* HERO */}
      <div className="flex items-center gap-3 mb-5">
        <button
          onClick={() => onSelectJob?.(null)}
          className="flex items-center justify-center w-8 h-8 rounded-md border border-hairline text-ink-2 hover:text-ink-0 hover:bg-bg-2 transition-colors"
          title="Retour"
          aria-label="Retour"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>

        <Pill tone={tone} dot={isRunning} pulse={isRunning}>
          {job.status}
        </Pill>

        {job.crawl_mode && (
          <Pill tone="accent">
            {job.crawl_mode === 'update' ? 'Update' : 'Standard'}
          </Pill>
        )}

        {job.oom_restart_count > 0 && (
          <Pill tone="warn">{job.oom_restart_count} OOM</Pill>
        )}

        <h2 className="font-mono text-[30px] font-semibold tracking-[-0.03em] text-ink-0 ml-auto">
          #{job.id?.slice(-8)}
        </h2>
      </div>

      {/* KPI STRIP */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 border border-hairline rounded-lg mb-5">
        <KpiCell label="URLs"       value={stats?.requestsTotal ?? null} />
        <KpiCell label="Items"      value={stats?.requestsFinished ?? null} />
        <KpiCell label="Errors"     value={stats?.requestsFailed ?? null} />
        <KpiCell label="Duration"   value={formatDuration(stats?.crawlerRuntimeMillis)} />
        <KpiCell label="Throughput" value={throughput} />
        <KpiCell label="Bandwidth"  value={formatBytes(stats?.totalBytes)} />
      </div>

      {/* TABS + SIDEBAR */}
      <div className="grid gap-5 grid-cols-1 md:grid-cols-[1fr_360px]">
        {/* Left: tabs */}
        <div>
          <div role="tablist" className="flex border-b border-hairline mb-4 gap-0">
            {TABS.map((tab) => (
              <TabBtn
                key={tab}
                label={tab}
                active={activeTab === tab}
                onClick={() => setActiveTab(tab)}
              />
            ))}
          </div>

          <div role="tabpanel" className="min-h-[300px]">
            {/* Logs */}
            {activeTab === 'Logs' && (
              showRaw ? (
                <AdvancedLogViewer content={job.rawContent || 'Contenu brut non disponible.'} jobId={job.id} />
              ) : !job.hasStats && !job.stats ? (
                <div className="py-12 text-center text-ink-2">
                  <Clock className={`mx-auto mb-3 h-10 w-10 ${isRunning ? 'animate-spin' : 'text-ink-3'}`} />
                  <p className="mb-1 text-[13px]">Les statistiques ne sont pas encore disponibles.</p>
                </div>
              ) : job.errors?.length > 0 ? (
                <div className="space-y-1">
                  {job.errors.slice(0, 50).map((e, i) => (
                    <LogLine key={i} lvl="err" msg={e} />
                  ))}
                  {job.errors.length > 50 && (
                    <p className="text-[12px] text-ink-3 italic mt-2">
                      … et {job.errors.length - 50} autres erreurs
                    </p>
                  )}
                </div>
              ) : (
                <div className="py-12 text-center text-ink-2">
                  <p className="text-[13px]">Aucune donnée de log disponible.</p>
                </div>
              )
            )}

            {/* Queue */}
            {activeTab === 'Queue' && (
              <div className="py-6">
                <Button asChild variant="outline">
                  <Link to={`/jobs/${job.id}/queue`}>Voir la Queue</Link>
                </Button>
              </div>
            )}

            {/* Dataset */}
            {activeTab === 'Dataset' && (
              <div className="py-6">
                <Button asChild variant="outline">
                  <Link to={`/jobs/${job.id}/dataset`}>Voir le Dataset</Link>
                </Button>
              </div>
            )}

            {/* Replay */}
            {activeTab === 'Replay' && (
              <div className="py-6">
                <Button asChild variant="outline">
                  <Link to={`/jobs/${job.id}/replay`}>Voir le Replay</Link>
                </Button>
              </div>
            )}

            {/* Metrics */}
            {activeTab === 'Metrics' && (
              perfQuery.isLoading ? (
                <div className="py-12 text-center text-ink-2 text-[13px]">Chargement des métriques…</div>
              ) : perfQuery.isError ? (
                <div className="py-12 text-center text-err text-[13px]">Impossible de charger les métriques.</div>
              ) : (
                <div className="space-y-4">
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-3 mb-2">RAM (MB)</div>
                    <AreaChart data={ramData} color="var(--accent)" refLine={maxRamMb} h={100} />
                  </div>
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-3 mb-2">CPU (%)</div>
                    <AreaChart data={cpuData} color="var(--info)" h={100} />
                  </div>
                </div>
              )
            )}

            {/* Callbacks */}
            {activeTab === 'Callbacks' && (
              <div className="py-12 text-center text-ink-2">
                <p className="text-[13px]">Callbacks panel</p>
              </div>
            )}
          </div>
        </div>

        {/* Right: sidebar KV */}
        <div>
          <div className="bg-surface rounded-lg border border-hairline p-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-3 mb-3">Détails</div>
            <div>
              <KV k="Domain" v={job.domain} />
              <KV k="Job ID" v={job.id} mono />
              <KV k="Mode" v={job.crawl_mode || '—'} />
              <KV k="Status" v={job.status} tone={statusTone(job.status)} />
              {job.previous_crawl_id && (
                <KV k="Prev Job" v={job.previous_crawl_id} mono />
              )}
              {job.oom_restart_count > 0 && (
                <KV k="OOM Restarts" v={job.oom_restart_count} tone="warn" />
              )}
            </div>

            <button
              onClick={() => onToggleRaw?.()}
              className="mt-4 w-full text-[12px] text-ink-2 hover:text-ink-0 border border-hairline rounded-md px-3 py-2"
            >
              {showRaw ? 'Vue Avancée' : 'Logs Bruts'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default JobDetails;
