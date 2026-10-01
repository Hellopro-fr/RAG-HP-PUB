import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  XCircle, ChevronLeft,
  Globe, Server,
  Play, Download, ExternalLink, ListOrdered,
  Settings, Mail,
  Cpu,
} from 'lucide-react';
import AdvancedLogViewer from './AdvancedLogViewer';
import Pill from './ui/Pill';
import AreaChart from './ui/AreaChart';
import LogLine from './ui/LogLine';
import KV from './ui/KV';
import { Card, CardHeader, CardTitle, CardContent } from './ui/card';
import { useJobPerformanceQuery } from '../hooks/queries';
import { ACTIVE_JOB_STATUSES, statusTone, statusLabel, isTerminalStatus } from '../lib/constants';
import { formatApiDate } from '../lib/dates';

/* -- helpers ---------------------------------------------------------------- */

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

const TS_FMT = {
  day: '2-digit', month: '2-digit', year: 'numeric',
  hour: '2-digit', minute: '2-digit', second: '2-digit',
};

/** Formate un timestamp API en « JJ/MM/AAAA HH:mm:ss », ou « — ». */
const fmtTs = (ts) => formatApiDate(ts, TS_FMT);

/*
 * Configuration du crawl : `job.config` est la forme cible de
 * /api/jobs/:id/details. Tant que le backend renvoie encore le document brut,
 * on retombe sur une allowlist de `job.params` — jamais sur `params` en entier,
 * qui contient des chemins de stockage et des secrets d'appel.
 */
const PARAMS_ALLOWLIST = [
  'crawlMode', 'method', 'typecrawling', 'cms', 'perminute', 'camoufox', 'previousCrawlId',
];

function buildConfig(job) {
  const cfg = job.config ?? null;
  const params = job.params ?? null;
  const legacy = (key) => (params && PARAMS_ALLOWLIST.includes(key) ? params[key] : undefined);
  const pick = (key) => cfg?.[key] ?? legacy(key) ?? null;
  return {
    depth:           cfg?.depth ?? null,
    concurrency:     cfg?.concurrency ?? null,
    queuelimit:      cfg?.queuelimit ?? null,
    maxErrorRate:    cfg?.maxErrorRate ?? null,
    perminute:       pick('perminute'),
    method:          pick('method'),
    typecrawling:    pick('typecrawling'),
    cms:             pick('cms'),
    camoufox:        pick('camoufox'),
    previousCrawlId: pick('previousCrawlId'),
    // `config.strategy` EST le crawlMode : le backend mappe params.crawlMode →
    // strategy (configAllowlist, internal/httpapi/jobs.go). Les deux lignes
    // « Stratégie » et « Mode » affichaient donc la même valeur deux fois.
    crawlMode:       cfg?.strategy ?? legacy('crawlMode') ?? job.crawl_mode ?? null,
  };
}

/** Statut du callback : forme cible `pending|sent|failed`, repli sur l'ancien code HTTP. */
const CALLBACK_STATUS = {
  pending: { tone: 'warn', label: 'En attente' },
  sent:    { tone: 'ok',   label: 'Envoyé' },
  failed:  { tone: 'err',  label: 'Échec' },
};

/* -- KPI Strip -------------------------------------------------------------- */

function KpiCell({ label, value, tone }) {
  const valueClass = tone === 'warn' ? 'text-warn' : 'text-ink-0';
  return (
    <div className="px-4 py-3 border-r border-hairline last:border-r-0 min-w-0">
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

/* -- Chart wrapper card ----------------------------------------------------- */

function ChartCard({ icon: Icon, title, subtitle, peak, color, data, refLine }) {
  return (
    <div className="border border-hairline rounded-lg bg-surface p-4 min-w-0">
      <div className="flex items-center justify-between mb-3 gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {Icon && <Icon size={14} className="text-ink-3 flex-shrink-0" />}
          <div className="min-w-0">
            <div className="text-[12px] font-semibold text-ink-1">{title}</div>
            {subtitle && <div className="text-[10px] text-ink-3 mt-0.5">{subtitle}</div>}
          </div>
        </div>
        {peak && (
          <span className="font-mono text-[12px] font-semibold flex-shrink-0" style={{ color }}>
            {peak}
          </span>
        )}
      </div>
      <AreaChart data={data} color={color} refLine={refLine} h={100} />
    </div>
  );
}

/* -- Toolbar link (small, inline) ------------------------------------------ */

const TOOLBAR_CLS =
  'inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[12px] text-ink-2 hover:text-ink-0 hover:bg-bg-2 border border-hairline transition-colors';

function ToolbarLink({ icon: Icon, to, children }) {
  return (
    <Link to={to} className={TOOLBAR_CLS}>
      {Icon && <Icon size={12} />}
      {children}
    </Link>
  );
}

function ToolbarBtn({ icon: Icon, children, onClick }) {
  return (
    <button onClick={onClick} className={TOOLBAR_CLS}>
      {Icon && <Icon size={12} />}
      {children}
    </button>
  );
}

/* -- Main component --------------------------------------------------------- */

const TABS = ['Logs', 'Métriques'];

const JobDetails = ({ job, onToggleRaw, showRaw, onSelectJob, token, inline = false }) => {
  const [activeTab, setActiveTab] = useState('Logs');

  /* Performance data — always call hook (Rules of Hooks) */
  const isRunning = ACTIVE_JOB_STATUSES.includes((job?.status || '').toLowerCase());
  // Les métriques ne sont chargées (et pollées) que lorsque l'onglet est ouvert :
  // /jobs/:id/performance déroule tout l'historique de heartbeats du replica.
  const perfQuery = useJobPerformanceQuery(token, job?.id, {
    jobStatus: job?.status,
    enabled: activeTab === 'Métriques',
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
  const terminal = isTerminalStatus(job.status);

  /* KPI values */
  const stats = job.stats;
  const throughput =
    stats && stats.crawlerRuntimeMillis > 0
      ? (stats.requestsFinished / (stats.crawlerRuntimeMillis / 1000)).toFixed(1) + '/s'
      : null;

  /* Performance chart data */
  const perfData = perfQuery.data;
  const perfPoints = perfData?.points ?? [];
  const ramData = perfPoints.map((p) => p.ram / 1024 / 1024);
  const cpuData = perfPoints.map((p) => p.cpu * 100);
  const maxRamMb = perfData?.summary?.total_ram
    ? perfData.summary.total_ram / 1024 / 1024
    : undefined;

  /* Peak labels */
  const peakRam = maxRamMb ? `pic ${maxRamMb.toFixed(1)} MB` : null;
  const peakCpu = perfData?.summary?.avg_cpu != null
    ? `moy. ${(perfData.summary.avg_cpu * 100).toFixed(0)}%`
    : null;

  /* Callback — forme cible { url, failure_url, status }, repli sur l'ancien contrat */
  const cb = job.callback ?? null;
  const cbUrl = cb?.url ?? job.callback_url ?? null;
  const cbFailureUrl = cb?.failure_url ?? null;
  const cbStatusKey = cb?.status ?? null;
  const cbMeta = cbStatusKey ? CALLBACK_STATUS[cbStatusKey] : null;
  const legacyCbOk = job.callback_status === '200' || job.callback_status === 200;
  const callbackDispatched = cbStatusKey === 'sent' || cb?.dispatched === true || legacyCbOk;

  /* Hero sub-line — replica + horodatage */
  const replicaId = job.replica?.id ?? job.replica_id ?? null;
  const startedAt = fmtTs(job.start_time ?? job.started_at);
  const finishedAt = fmtTs(job.finished_at ?? job.end_time);

  const tabCounts = {
    Logs: job.errors?.length ?? null,
    Métriques: null,
  };

  const cfg = buildConfig(job);
  /* On ne rend que les lignes réellement renseignées : une carte de 12 tirets
     n'apprend rien et masque les 2 valeurs qui comptent. */
  const configRows = [
    ['Mode de crawl',    cfg.crawlMode, true],
    ['Profondeur',       cfg.depth != null ? String(cfg.depth) : null],
    ['Concurrence',      cfg.concurrency != null ? `${cfg.concurrency} en parallèle` : null],
    ['Débit max',        cfg.perminute != null ? `${cfg.perminute}/min` : null],
    ['Méthode',          cfg.method, true],
    ['Type de crawl',    cfg.typecrawling, true],
    ['CMS',              cfg.cms, true],
    ['Camoufox',         cfg.camoufox != null ? (cfg.camoufox ? 'oui' : 'non') : null],
    ['Limite queue',     cfg.queuelimit != null ? String(cfg.queuelimit) : null],
    ['Taux erreur max',  cfg.maxErrorRate != null ? String(cfg.maxErrorRate) : null],
    ['Crawl précédent',  cfg.previousCrawlId, true],
  ].filter(([, value]) => value != null && value !== '');

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
  const hasCallbackInfo = cbUrl != null || cbFailureUrl != null || cbMeta != null || legacyCbOk;

  /* -- render --------------------------------------------------------------- */
  return (
    <div className="min-w-0">
      {/* HERO */}
      <div className="mb-5 min-w-0">
        {/* Row 1: back button + status pills */}
        <div className="flex items-center gap-3 mb-2 flex-wrap">
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
            {statusLabel(job.status)}
          </Pill>

          {job.crawl_mode && (
            <Pill tone="info">
              {job.crawl_mode === 'update' ? 'Update' : 'Standard'}
            </Pill>
          )}

          {job.oom_restart_count > 0 && (
            <Pill tone="warn">{job.oom_restart_count} OOM</Pill>
          )}

          {callbackDispatched && (
            <Pill tone="neutral">callback envoyé</Pill>
          )}
        </div>

        {/* Row 2: job ID + toolbar */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <h2 className="font-mono text-[20px] font-semibold tracking-[-0.02em] leading-tight break-all min-w-0">
            <span className="text-ink-3 font-normal">#</span>
            <span className="text-ink-0">{job.id}</span>
          </h2>

          {/* Vues dediees + bascule logs bruts */}
          <div className="flex items-center gap-1.5 flex-wrap mt-1">
            <ToolbarLink icon={ListOrdered} to={`/jobs/${job.id}/queue`}>Queue</ToolbarLink>
            <ToolbarLink icon={Download} to={`/jobs/${job.id}/dataset`}>Dataset</ToolbarLink>
            <ToolbarLink icon={Play} to={`/jobs/${job.id}/replay`}>Replay</ToolbarLink>
            {onToggleRaw && (
              <ToolbarBtn icon={ExternalLink} onClick={onToggleRaw}>
                {showRaw ? 'Vue synthèse' : 'Logs bruts'}
              </ToolbarBtn>
            )}
          </div>
        </div>

        {/* Sub-line — domain · replica · horodatage */}
        <div className="text-[12px] text-ink-2 mt-2 flex items-center gap-2 flex-wrap font-mono min-w-0">
          {job.domain && (
            <>
              <Globe size={12} className="text-ink-3 flex-shrink-0" />
              <span className="text-ink-1 break-all">{job.domain}</span>
              <span className="text-ink-3">·</span>
            </>
          )}
          {replicaId && (
            <>
              <Server size={12} className="text-ink-3 flex-shrink-0" />
              <span className="break-all">{replicaId}</span>
              <span className="text-ink-3">·</span>
            </>
          )}
          <span>{startedAt} → {finishedAt}</span>
        </div>
      </div>

      {/* KPI STRIP — masqué tant que l'API ne fournit aucune statistique */}
      {hasAnyKpi && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 border border-hairline rounded-lg mb-5">
          <KpiCell label="URLs crawlées"  value={stats?.requestsTotal ?? null} />
          <KpiCell label="Items extraits" value={stats?.requestsFinished ?? null} />
          <KpiCell
            label="Erreurs HTTP"
            value={stats?.requestsFailed ?? null}
            tone={stats?.requestsFailed > 0 ? 'warn' : undefined}
          />
          <KpiCell label="Durée totale"   value={formatDuration(stats?.crawlerRuntimeMillis)} />
          <KpiCell label="Débit"          value={throughput} />
          <KpiCell label="Volume"         value={formatBytes(stats?.totalBytes)} />
        </div>
      )}

      {/* TABS + SIDEBAR */}
      <div className="grid gap-5 grid-cols-1 2xl:grid-cols-[1fr_360px]">

        {/* Left: tabs */}
        <div className="min-w-0">
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

          <div role="tabpanel" className="min-h-[300px] min-w-0">

            {/* Logs */}
            {activeTab === 'Logs' && (
              showRaw ? (
                <AdvancedLogViewer content={job.rawContent || 'Contenu brut non disponible.'} jobId={job.id} />
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
              ) : job.rawContent ? (
                <div className="py-12 text-center text-ink-2">
                  <p className="text-[13px] mb-3">Aucune erreur détectée dans le log de ce crawl.</p>
                  {onToggleRaw && (
                    <ToolbarBtn icon={ExternalLink} onClick={onToggleRaw}>Logs bruts</ToolbarBtn>
                  )}
                </div>
              ) : (
                <div className="py-12 text-center text-ink-2">
                  <p className="text-[13px]">
                    {isRunning
                      ? 'Log en cours d’écriture…'
                      : terminal
                        ? 'Log du crawl indisponible (job archivé ou stockage purgé).'
                        : 'Log du crawl indisponible.'}
                  </p>
                </div>
              )
            )}

            {/* Métriques */}
            {activeTab === 'Métriques' && (
              perfQuery.isLoading ? (
                <div className="py-12 text-center text-ink-2 text-[13px]">Chargement des métriques…</div>
              ) : perfQuery.isError ? (
                <div className="py-12 text-center text-err text-[13px]">Impossible de charger les métriques.</div>
              ) : perfPoints.length === 0 ? (
                <div className="py-12 text-center text-ink-2 text-[13px]">
                  Aucun échantillon de performance pour ce job.
                </div>
              ) : (
                <div className="space-y-4">
                  <ChartCard
                    icon={Cpu}
                    title="Mémoire RAM"
                    subtitle="Replica · dernière heure"
                    peak={peakRam}
                    color="var(--accent)"
                    data={ramData}
                    refLine={maxRamMb}
                  />
                  <ChartCard
                    icon={Cpu}
                    title="CPU"
                    subtitle="Replica · dernière heure"
                    peak={peakCpu}
                    color="var(--info)"
                    data={cpuData}
                  />
                </div>
              )
            )}
          </div>
        </div>

        {/* Right: sidebar */}
        <div className="flex flex-col gap-4 min-w-0">

          {/* Card A: Configuration — masquée tant que l'API ne fournit aucune valeur */}
          {configRows.length > 0 && (
            <SideCard icon={Settings} title="Configuration">
              {configRows.map(([label, value, mono]) => (
                <KV key={label} k={label} v={value} mono={!!mono} />
              ))}
            </SideCard>
          )}

          {/* Card B: Callback */}
          {hasCallbackInfo && (
            <SideCard icon={Mail} title="Callback">
              <div className="flex flex-col gap-3">
                <div className="flex items-center gap-2">
                  {cbMeta ? (
                    <Pill tone={cbMeta.tone} dot>{cbMeta.label}</Pill>
                  ) : legacyCbOk ? (
                    <Pill tone="ok" dot>200 OK</Pill>
                  ) : (
                    <span className="text-[12px] text-ink-3 font-mono">—</span>
                  )}
                </div>

                {cbUrl && (
                  <div>
                    <div className="text-[10px] uppercase tracking-[0.05em] text-ink-3 mb-1">Succès</div>
                    <div className="font-mono text-[11px] text-ink-1 p-2.5 bg-bg-1 rounded-md border border-hairline break-all">
                      {cbUrl}
                    </div>
                  </div>
                )}

                {cbFailureUrl && (
                  <div>
                    <div className="text-[10px] uppercase tracking-[0.05em] text-ink-3 mb-1">Échec</div>
                    <div className="font-mono text-[11px] text-ink-1 p-2.5 bg-bg-1 rounded-md border border-hairline break-all">
                      {cbFailureUrl}
                    </div>
                  </div>
                )}
              </div>
            </SideCard>
          )}

          {/* Repli discret quand aucune métadonnée latérale n'est disponible */}
          {configRows.length === 0 && !hasCallbackInfo && (
            <p className="text-[12px] text-ink-3 text-center py-4">
              Métadonnées de configuration non disponibles pour ce job.
            </p>
          )}

        </div>
      </div>
    </div>
  );
};

export default JobDetails;
