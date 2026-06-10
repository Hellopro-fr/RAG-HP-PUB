import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  XCircle, Clock, ChevronLeft,
  Globe, Server,
  Play, Download, ExternalLink, MoreVertical,
  Settings, Layers, Mail,
  Cpu, RefreshCw,
} from 'lucide-react';
import AdvancedLogViewer from './AdvancedLogViewer';
import { Button } from './ui/button';
import Pill from './ui/Pill';
import AreaChart from './ui/AreaChart';
import LogLine from './ui/LogLine';
import KV from './ui/KV';
import { Card, CardHeader, CardTitle, CardContent } from './ui/card';
import { useJobPerformanceQuery } from '../hooks/queries';

/* -- helpers ---------------------------------------------------------------- */

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

/** Format an ISO timestamp to "DD/MM/YYYY HH:mm:ss" (fr-style), or "—" */
function fmtTs(ts) {
  if (!ts) return '—';
  try {
    return new Date(ts).toLocaleString('fr-FR', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  } catch {
    return '—';
  }
}

/* -- KPI Strip -------------------------------------------------------------- */

function KpiCell({ label, value, tone }) {
  const valueClass = tone === 'warn' ? 'text-warn' : 'text-ink-0';
  return (
    <div className="px-4 py-3 border-r border-hairline last:border-r-0">
      <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-ink-3 mb-1">{label}</div>
      <div className={`text-[22px] font-semibold tracking-[-0.025em] tabular-nums font-display ${valueClass}`}>
        {value ?? '—'}
      </div>
    </div>
  );
}

/* -- Tab button ------------------------------------------------------------- */

function TabBtn({ label, count, active, onClick }) {
  return (
    <button
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={
        'px-3 py-2 text-[13px] cursor-pointer -mb-px flex items-center ' +
        (active
          ? 'border-b-2 border-accent text-ink-0 font-medium'
          : 'text-ink-2 hover:text-ink-1')
      }
    >
      {label}
      {count != null && (
        <span className="ml-1 text-[10px] font-mono text-ink-3">{count}</span>
      )}
    </button>
  );
}

/* -- Sidebar section card --------------------------------------------------- */

function SideCard({ icon: Icon, title, children }) {
  return (
    <Card className="border-hairline bg-surface">
      <CardHeader className="pb-2 pt-4 px-4">
        <CardTitle className="flex items-center gap-2 text-[12px] font-semibold uppercase tracking-[0.05em] text-ink-3">
          {Icon && <Icon size={13} className="text-ink-3" />}
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4 pt-0">
        {children}
      </CardContent>
    </Card>
  );
}

/* -- Pipeline step row ------------------------------------------------------ */

function PipelineRow({ label, duration, ratio }) {
  return (
    <div className="flex items-center gap-2 py-1.5 border-b border-hairline last:border-b-0">
      <span className="flex-1 text-[12px] text-ink-1">{label}</span>
      <span className="font-mono text-ink-2 text-[11px] w-14 text-right">{duration ?? '—'}</span>
      {ratio != null ? (
        <div className="w-12 h-1 bg-bg-2 rounded flex-shrink-0">
          <div
            className="h-full bg-accent rounded"
            style={{ width: `${Math.min(ratio * 100, 100)}%` }}
          />
        </div>
      ) : (
        <div className="w-12 h-1 bg-bg-2 rounded flex-shrink-0" />
      )}
    </div>
  );
}

/* -- Chart wrapper card ----------------------------------------------------- */

function ChartCard({ icon: Icon, title, subtitle, peak, color, data, refLine }) {
  return (
    <div className="border border-hairline rounded-lg bg-surface p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          {Icon && <Icon size={14} className="text-ink-3" />}
          <div>
            <div className="text-[12px] font-semibold text-ink-1">{title}</div>
            {subtitle && <div className="text-[10px] text-ink-3 mt-0.5">{subtitle}</div>}
          </div>
        </div>
        {peak && (
          <span className="font-mono text-[12px] font-semibold" style={{ color }}>
            {peak}
          </span>
        )}
      </div>
      <AreaChart data={data} color={color} refLine={refLine} h={100} />
    </div>
  );
}

/* -- Ghost button (small, inline) ------------------------------------------ */

function GhostBtn({ icon: Icon, children, onClick, disabled }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[12px] text-ink-2 hover:text-ink-0 hover:bg-bg-2 border border-hairline transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
    >
      {Icon && <Icon size={12} />}
      {children}
    </button>
  );
}

/* -- Main component --------------------------------------------------------- */

const TABS = ['Logs', 'Queue', 'Dataset', 'Replay', 'Metrics', 'Callbacks'];

const JobDetails = ({ job, onToggleRaw, showRaw, onSelectJob, token, inline = false }) => {
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

  /* Peak labels */
  const peakRam = maxRamMb ? `peak ${maxRamMb.toFixed(1)} MB` : null;
  const peakCpu = perfData?.summary?.avg_cpu != null
    ? `avg ${(perfData.summary.avg_cpu * 100).toFixed(0)}%`
    : null;

  /*
   * Fix 1 — Callback pill condition.
   * job.callback?.dispatched (future API shape) or job.callback_status === '200'
   * (alternate shape). If neither is present, the pill is omitted.
   */
  const callbackDispatched =
    job.callback?.dispatched === true || job.callback_status === '200';

  /*
   * Fix 3 — Hero sub-line.
   * replica: job.replica (object) or job.replica_id (string).
   * region:  job.replica?.region or job.region.
   * timestamps: start_time / end_time (jobs list) or started_at / finished_at.
   */
  const replicaId = job.replica?.id ?? job.replica_id ?? null;
  const replicaRegion = job.replica?.region ?? job.region ?? null;
  const startedAt = fmtTs(job.start_time ?? job.started_at);
  const finishedAt = fmtTs(job.end_time ?? job.finished_at);

  /*
   * Fix 5 — Tab count badges.
   * Sources from actual job data; omit badge when count is unknown.
   */
  const tabCounts = {
    Logs:      job.errors?.length ?? null,
    Queue:     stats?.requestsTotal ?? null,
    Dataset:   stats?.requestsFinished ?? null,
    Replay:    null,
    Metrics:   null,
    Callbacks: job.callback ? 1 : null,
  };

  /*
   * Fix 8 — Sidebar configuration.
   * job.config holds crawler configuration when available.
   */
  const cfg = job.config ?? {};

  /*
   * Fix 8 — Pipeline data.
   * job.pipeline not yet in API; render placeholder rows when absent.
   */
  const pipeline = job.pipeline ?? null;
  const PIPELINE_STEPS = ['fetch', 'parse', 'deduplicate', 'validate', 'callback'];

  /*
   * Fix 8 — Callback card.
   * job.callback expected future shape; job.callback_status is alternate.
   */
  const cb = job.callback ?? null;
  const cbStatus = cb?.status ?? job.callback_status ?? null;
  const cbLatency = cb?.latency_ms != null ? `${cb.latency_ms}ms` : null;
  const cbUrl = cb?.url ?? null;
  const cbOk = cbStatus === '200' || cbStatus === 200;

  /*
   * Visibilité des sections — une section est masquée tant que TOUTES ses
   * valeurs sont absentes ; elle réapparaîtra dès que l'API les fournira.
   */
  const hasAnyKpi = [
    stats?.requestsTotal,
    stats?.requestsFinished,
    stats?.requestsFailed,
    formatDuration(stats?.crawlerRuntimeMillis),
    throughput,
    formatBytes(stats?.totalBytes),
  ].some((v) => v != null);
  const hasConfig = [cfg.strategy, cfg.depth, cfg.concurrency, cfg.user_agent ?? cfg.userAgent, cfg.respect_robots, cfg.timeout_ms ?? cfg.timeout, cfg.retries, cfg.cron ?? job.cron].some((v) => v != null);
  const hasCallbackInfo = cbStatus != null || cbUrl != null || cbLatency != null;

  /* -- render --------------------------------------------------------------- */
  return (
    <div>
      {/* HERO */}
      <div className="mb-5">
        {/* Row 1: back button + status pills */}
        <div className="flex items-center gap-3 mb-2">
          {!inline && (
            <button
              onClick={() => onSelectJob?.(null)}
              className="flex items-center justify-center w-8 h-8 rounded-md border border-hairline text-ink-2 hover:text-ink-0 hover:bg-bg-2 transition-colors flex-shrink-0"
              title="Retour"
              aria-label="Retour"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
          )}

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

          {/* Fix 1: callback dispatched pill — shown only when API confirms dispatch */}
          {callbackDispatched && (
            <Pill tone="neutral">callback dispatched</Pill>
          )}
        </div>

        {/* Row 2: full job ID + action buttons */}
        {/* Fix 2: full ID with # in ink-3; Fix 4: right-aligned actions */}
        <div className="flex items-start justify-between gap-4 flex-wrap sm:flex-nowrap">
          {/* Fix 2 */}
          <h2 className="font-mono text-[30px] font-semibold tracking-[-0.03em] leading-tight">
            <span className="text-ink-3 font-normal">#</span>
            <span className="text-ink-0">{job.id}</span>
          </h2>

          {/* Fix 4: action buttons */}
          <div className="flex items-center gap-1.5 flex-shrink-0 mt-1">
            {inline && (
              <Link
                to={`/jobs/${job.id}`}
                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[12px] text-ink-2 hover:text-ink-0 hover:bg-bg-2 border border-hairline transition-colors"
              >
                <ExternalLink size={12} />
                Détail complet
              </Link>
            )}
            <GhostBtn icon={Play} onClick={() => console.log('Replay', job.id)}>
              Replay
            </GhostBtn>
            <GhostBtn icon={Download} onClick={() => console.log('Dataset', job.id)}>
              Dataset
            </GhostBtn>
            <GhostBtn
              icon={ExternalLink}
              onClick={() => onToggleRaw ? onToggleRaw() : console.log('Logs bruts', job.id)}
            >
              Logs bruts
            </GhostBtn>
            <button
              onClick={() => console.log('More', job.id)}
              className="inline-flex items-center justify-center w-8 h-8 rounded-md text-ink-2 hover:text-ink-0 hover:bg-bg-2 border border-hairline transition-colors"
              aria-label="Plus d'actions"
            >
              <MoreVertical size={14} />
            </button>
          </div>
        </div>

        {/* Fix 3: sub-line — domain · replica · region · timestamps */}
        <div className="text-[12px] text-ink-2 mt-2 flex items-center gap-2 flex-wrap font-mono">
          {job.domain && (
            <>
              <Globe size={12} className="text-ink-3 flex-shrink-0" />
              <span className="text-ink-1">{job.domain}</span>
              <span className="text-ink-3">·</span>
            </>
          )}
          {(replicaId || replicaRegion) && (
            <>
              <Server size={12} className="text-ink-3 flex-shrink-0" />
              {replicaId && <span>{replicaId}</span>}
              {replicaRegion && (
                <>
                  {replicaId && <span className="text-ink-3">—</span>}
                  <span>{replicaRegion}</span>
                </>
              )}
              <span className="text-ink-3">·</span>
            </>
          )}
          <span>{startedAt} → {finishedAt}</span>
        </div>
      </div>

      {/* KPI STRIP — masqué tant que l'API ne fournit aucune statistique */}
      {hasAnyKpi && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 border border-hairline rounded-lg mb-5">
          <KpiCell label="URLs crawlées"  value={stats?.requestsTotal ?? null} />
          <KpiCell label="Items extraits" value={stats?.requestsFinished ?? null} />
          <KpiCell
            label="Erreurs HTTP"
            value={stats?.requestsFailed ?? null}
            tone={stats?.requestsFailed > 0 ? 'warn' : undefined}
          />
          <KpiCell label="Durée totale"   value={formatDuration(stats?.crawlerRuntimeMillis)} />
          <KpiCell label="Throughput"     value={throughput} />
          <KpiCell label="Bandwidth"      value={formatBytes(stats?.totalBytes)} />
        </div>
      )}

      {/* TABS + SIDEBAR */}
      <div className="grid gap-5 grid-cols-1 md:grid-cols-[1fr_360px]">

        {/* Left: tabs */}
        <div>
          {/* Fix 5: tab labels with count badges */}
          <div role="tablist" className="flex border-b border-hairline mb-4 gap-0">
            {TABS.map((tab) => (
              <TabBtn
                key={tab}
                label={tab}
                count={tabCounts[tab]}
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
              ) : (
                <>
                  {!job.hasStats && !job.stats ? (
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
                  )}
                </>
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

            {/* Fix 7: Metrics — charts wrapped in ChartCard */}
            {activeTab === 'Metrics' && (
              perfQuery.isLoading ? (
                <div className="py-12 text-center text-ink-2 text-[13px]">Chargement des métriques…</div>
              ) : perfQuery.isError ? (
                <div className="py-12 text-center text-err text-[13px]">Impossible de charger les métriques.</div>
              ) : (
                <div className="space-y-4">
                  <ChartCard
                    icon={Cpu}
                    title="Mémoire RAM"
                    subtitle="Replica · last hour"
                    peak={peakRam}
                    color="var(--accent)"
                    data={ramData}
                    refLine={maxRamMb}
                  />
                  <ChartCard
                    icon={Cpu}
                    title="CPU"
                    subtitle="Replica · last hour"
                    peak={peakCpu}
                    color="var(--info)"
                    data={cpuData}
                  />
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

        {/* Right: sidebar — Fix 8: 3 dedicated cards */}
        <div className="flex flex-col gap-4">

          {/* Card A: Configuration — masquée tant que l'API ne fournit aucune valeur */}
          {hasConfig && (
            <SideCard icon={Settings} title="Configuration">
              <KV k="Strategy"       v={cfg.strategy ?? null}            mono />
              <KV k="Depth"          v={cfg.depth != null ? String(cfg.depth) : null} />
              <KV k="Concurrency"    v={cfg.concurrency != null ? `${cfg.concurrency} parallel` : null} />
              <KV k="User-agent"     v={cfg.user_agent ?? cfg.userAgent ?? null}  mono />
              <KV k="Respect robots" v={cfg.respect_robots != null ? (cfg.respect_robots ? 'oui' : 'non') : null} tone={cfg.respect_robots ? 'ok' : undefined} />
              <KV k="Timeout"        v={cfg.timeout_ms != null ? `${cfg.timeout_ms / 1000}s` : cfg.timeout ?? null} />
              <KV k="Retries"        v={cfg.retries != null ? `${cfg.retries} max` : null} />
              <KV k="Cron"           v={cfg.cron ?? job.cron ?? null}    mono />
            </SideCard>
          )}

          {/* Card B: Pipeline — masquée tant que job.pipeline est absent de l'API */}
          {pipeline && (
            <SideCard icon={Layers} title="Pipeline">
              {PIPELINE_STEPS.map((step) => {
                const s = pipeline ? (pipeline[step] ?? {}) : {};
                return (
                  <PipelineRow
                    key={step}
                    label={step}
                    duration={s.duration ?? null}
                    ratio={s.ratio ?? null}
                  />
                );
              })}
            </SideCard>
          )}

          {/* Card C: Callback — masquée sans info callback (le bouton Rejouer est disabled sans cb, donc inutile seul) */}
          {hasCallbackInfo && (
            <SideCard icon={Mail} title="Callback">
              <div className="flex flex-col gap-3">
                <div className="flex items-center gap-2">
                  {cbStatus ? (
                    <>
                      <Pill tone={cbOk ? 'ok' : 'err'} dot>
                        {cbOk ? '200 OK' : `Échec${cbStatus ? ` (${cbStatus})` : ''}`}
                      </Pill>
                      {cbLatency && (
                        <span className="font-mono text-[11px] text-ink-2">{cbLatency}</span>
                      )}
                    </>
                  ) : (
                    <span className="text-[12px] text-ink-3 font-mono">—</span>
                  )}
                </div>

                <div className="font-mono text-[11px] text-ink-1 p-2.5 bg-bg-1 rounded-md border border-hairline break-all min-h-[32px]">
                  {cbUrl ?? '—'}
                </div>

                <Button
                  variant="outline"
                  size="sm"
                  disabled={!cb}
                  onClick={() => console.log('Rejouer callback', job.id)}
                  className="w-full justify-center gap-1.5 text-[12px]"
                >
                  <RefreshCw size={12} />
                  Rejouer le callback
                </Button>
              </div>
            </SideCard>
          )}

          {/* Fallback discret quand aucune métadonnée latérale n'est disponible */}
          {!hasConfig && !pipeline && !hasCallbackInfo && (
            <p className="text-[12px] text-ink-3 text-center py-4">Métadonnées de configuration non disponibles pour ce job.</p>
          )}

        </div>
      </div>
    </div>
  );
};

export default JobDetails;