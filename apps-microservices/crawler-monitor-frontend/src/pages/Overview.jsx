import { useState, useMemo, useRef, useEffect, useCallback, useDeferredValue } from 'react';
import { useParams } from 'react-router-dom';
import {
  RefreshCw, Server,
  Search, Filter, Calendar, ChevronLeft, ChevronRight, X,
  Activity, Cpu,
} from 'lucide-react';
import {
  JOBS_PER_PAGE, JOB_STATUS, JOB_STATUS_KEYS, statusTone, statusLabel,
} from '../lib/constants';
import { parseApiDateMs, formatApiDate } from '../lib/dates';
import {
  useJobsQuery,
  useCapacityQuery,
  useJobDetailsQuery,
  useAlertsQuery,
  useWsInvalidator,
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

/** Inline mini-stat for replica cards */
const MiniStat = ({ label, value }) => (
  <div className="flex flex-col gap-0.5">
    <span className="text-[9.5px] font-semibold text-ink-3 uppercase tracking-wider">{label}</span>
    <span className="font-mono text-[13px] font-semibold text-ink-0">{value}</span>
  </div>
);

/** Section card wrapper matching spec (icon + title + subtitle + action) */
const SectionCard = ({ icon: Icon, title, subtitle, action, children, padding = 'p-[18px]' }) => (
  <div className="bg-surface border border-hairline rounded-lg shadow-sm overflow-hidden min-w-0">
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

/** Legend dot + label + count */
const LegendItem = ({ color, label, count, title }) => (
  <div className="flex items-center gap-1.5" title={title}>
    <span className="w-2 h-2 rounded-[2px] flex-shrink-0" style={{ background: color }} />
    <span className="text-[11px] text-ink-2">{label}</span>
    <span className="font-mono text-[11px] font-semibold text-ink-0">{count}</span>
  </div>
);

/**
 * Overview page (`/` et `/jobs/:id`).
 *
 * Donnees via les hooks React Query ; aucun fetch manuel ici.
 * `replicas` vient toujours des props (WebSocket only, vit dans App.jsx).
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
  // Panneau inline : job sélectionné (état local, pas piloté par l'URL)
  const [selectedJobId, setSelectedJobId] = useState(routeJobId ?? null);

  // La frappe dans le champ de recherche ne doit pas bloquer le rendu de la
  // liste : on filtre sur une valeur différée.
  const deferredSearch = useDeferredValue(searchTerm);

  // Data layer
  const jobsQuery = useJobsQuery(token);
  const allJobs = useMemo(() => jobsQuery.data || [], [jobsQuery.data]);
  const loading = jobsQuery.isLoading;

  const capacityQuery = useCapacityQuery(token);
  const capacity = capacityQuery.data || null;
  const capacityLoading = capacityQuery.isPending ?? capacityQuery.isLoading;

  const alertsQuery = useAlertsQuery(token);
  const activeAlerts = useMemo(() => alertsQuery.data?.alerts || [], [alertsQuery.data]);
  const nbActiveAlerts = activeAlerts.length;
  const hasCritical = activeAlerts.some(a => a.severity === 'critical');

  // Job affiché dans le panneau détail : on le déclare à l'invalidateur WS pour
  // que ses détails/perf soient rafraîchis même avant que React Query n'ait
  // enregistré l'observer correspondant.
  const { setWatchedJobId } = useWsInvalidator();
  useEffect(() => {
    setWatchedJobId(selectedJobId);
    return () => setWatchedJobId(null);
  }, [selectedJobId, setWatchedJobId]);

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

  /*
   * Pré-calcul d'un timestamp numérique par job : le tri et le bucketing de la
   * timeline le réutilisent au lieu de reconstruire une Date par comparaison.
   * `start_time` illisible -> 0, ce qui envoie le job en fin de tri au lieu de
   * produire un NaN qui rendait l'ordre non déterministe.
   */
  const jobsWithTime = useMemo(
    () => allJobs
      .filter(job => job && job.id)
      .map(job => ({ job, startMs: parseApiDateMs(job.start_time) ?? 0 })),
    [allJobs],
  );

  const filteredJobs = useMemo(() => {
    // Bornes de date et recherche hissées hors de la boucle.
    //
    // Les deux bornes viennent d'un <input type="date"> : elles désignent des
    // journées dans le fuseau de l'OPÉRATEUR, pas en UTC. On ne passe donc pas
    // par parseApiDate, qui force l'UTC quand la chaîne n'a pas de fuseau — en
    // été (UTC+2) « du 28 au 28 » amputait la journée de ses 2 premières heures
    // et y ajoutait 2 h de la nuit suivante. `new Date('2026-08-28T00:00:00')`
    // (sans « Z ») est au contraire lu en heure locale par la spec ES.
    const localDayMs = (day, time) => {
      const d = new Date(`${day}T${time}`);
      return Number.isNaN(d.getTime()) ? null : d.getTime();
    };
    const startMsBound = startDate ? localDayMs(startDate, '00:00:00') : null;
    const endMsBound = endDate ? localDayMs(endDate, '23:59:59.999') : null;
    const hasDateBound = startMsBound != null || endMsBound != null;
    const searchLower = deferredSearch.trim().toLowerCase();

    return jobsWithTime
      .filter(({ job, startMs }) => {
        // start_time absent/illisible → startMs = 0. Un job non datable ne peut
        // satisfaire aucune borne : on l'écarte des DEUX côtés. Avant, il était
        // bien exclu par une borne de début (0 < borne) mais passait une borne
        // de fin seule (0 > borne est faux) — le filtre n'était pas symétrique.
        if (hasDateBound && !startMs) return false;
        if (startMsBound != null && startMs < startMsBound) return false;
        if (endMsBound != null && startMs > endMsBound) return false;
        if (statusFilter !== 'all' && job.status !== statusFilter) return false;
        if (searchLower) {
          const matches =
            String(job.id ?? '').toLowerCase().includes(searchLower) ||
            String(job.domain ?? '').toLowerCase().includes(searchLower);
          if (!matches) return false;
        }
        return true;
      })
      .sort((a, b) => b.startMs - a.startMs)
      .map(({ job }) => job);
  }, [jobsWithTime, deferredSearch, statusFilter, startDate, endDate]);

  const totalPages = Math.max(1, Math.ceil(filteredJobs.length / JOBS_PER_PAGE));
  // La liste peut rétrécir (filtre, refetch) sous une page courante trop haute :
  // on borne la page utilisée pour la tranche ET pour les boutons.
  const safePage = Math.min(currentPage, totalPages);

  const paginatedJobs = useMemo(() => {
    const startIndex = (safePage - 1) * JOBS_PER_PAGE;
    return filteredJobs.slice(startIndex, startIndex + JOBS_PER_PAGE);
  }, [filteredJobs, safePage]);

  const statusCounts = useMemo(() => {
    const counts = new Map();
    for (const job of allJobs) {
      const key = String(job?.status ?? '').toLowerCase();
      if (!key) continue;
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    return counts;
  }, [allJobs]);

  /* Options du filtre générées depuis la table de statuts, les statuts
     réellement présents dans la réponse en premier. */
  const statusOptions = useMemo(() => {
    const present = [];
    const absent = [];
    for (const key of JOB_STATUS_KEYS) {
      const count = statusCounts.get(key) || 0;
      const option = { value: key, label: JOB_STATUS[key].label, count };
      (count > 0 ? present : absent).push(option);
    }
    // Statuts inconnus de la table (nouveau statut backend) : ne pas les perdre.
    const unknown = [...statusCounts.keys()]
      .filter(key => !JOB_STATUS[key])
      .map(key => ({ value: key, label: key, count: statusCounts.get(key) }));
    return [...present, ...unknown, ...absent];
  }, [statusCounts]);

  const globalStats = useMemo(() => {
    const get = (key) => statusCounts.get(key) || 0;
    return {
      finished: get('finished'),
      failed: get('failed'),
      running: get('running'),
      archived: get('archived'),
      // Tout ce qui n'est ni termine, ni archive, ni en echec est encore en vol :
      // c'est le même regroupement que les barres « en cours » de la timeline.
      inFlight: allJobs.length - get('finished') - get('archived') - get('failed'),
      total: allJobs.length,
    };
  }, [statusCounts, allJobs.length]);

  /*
   * `capacity.running_jobs` est le compteur auto-réparé du crawler-service :
   * c'est la source de vérité. Le comptage client sur /api/jobs inclut des
   * documents `running` sans heartbeat récent (jobs zombies).
   */
  const runningDisplay = capacity?.running_jobs ?? globalStats.running;
  const stuckRunning = capacity?.running_jobs != null && globalStats.running > capacity.running_jobs
    ? globalStats.running - capacity.running_jobs
    : 0;

  // Total slots from capacity or replica count
  const totalSlots = capacity?.max_global_jobs ?? (replicas ? Object.keys(replicas).length : 0);

  // Build timeline data: aggregate jobs by hour (last 24 buckets)
  const timelineData = useMemo(() => {
    if (!jobsWithTime.length) return [];
    const now = Date.now();
    const buckets = Array.from({ length: 24 }, (_, i) => {
      const from = now - (23 - i) * 3600 * 1000;
      const to = from + 3600 * 1000;
      const hour = new Date(from).getHours();
      return { label: `${String(hour).padStart(2, '0')}h`, from, to, ok: 0, run: 0, fail: 0 };
    });
    jobsWithTime.forEach(({ job, startMs }) => {
      if (!startMs) return;
      const bucket = buckets.find(b => startMs >= b.from && startMs < b.to);
      if (!bucket) return;
      if (job.status === 'finished' || job.status === 'archived') bucket.ok++;
      else if (job.status === 'failed') bucket.fail++;
      else bucket.run++;
    });
    return buckets.map(({ label, ok, run, fail }) => ({ label, ok, run, fail }));
  }, [jobsWithTime]);

  const jobsListRef = useRef(null);
  const hasAutoSelectedRef = useRef(false);
  const userPickedRef = useRef(false);

  // Sélectionner un job dans le panneau inline (pas de navigation URL)
  const handleSelectJob = useCallback((id) => {
    if (!id || id === 'undefined' || id === 'null') return;
    userPickedRef.current = true;
    hasAutoSelectedRef.current = true;
    setSelectedJobId(id);
  }, []);

  // Synchroniser selectedJobId avec routeJobId (navigation directe via URL)
  useEffect(() => {
    if (!routeJobId) return;
    userPickedRef.current = true;
    hasAutoSelectedRef.current = true;
    setSelectedJobId(routeJobId);
  }, [routeJobId]);

  /* Arrivée par /jobs/:id : la vue d'ensemble reste montée, on amène juste la
     liste + le panneau détail dans le viewport (le <main> est le scroller). */
  useEffect(() => {
    if (!routeJobId) return;
    jobsListRef.current?.scrollIntoView?.({ block: 'start' });
  }, [routeJobId]);

  /*
   * Auto-sélection du premier job : une seule fois, au premier chargement de la
   * liste. Jamais après un clic utilisateur — sinon un refetch reprenait la main
   * et ramenait l'opérateur sur le job le plus récent.
   */
  useEffect(() => {
    if (hasAutoSelectedRef.current || selectedJobId || filteredJobs.length === 0) return;
    hasAutoSelectedRef.current = true;
    setSelectedJobId(filteredJobs[0].id);
  }, [filteredJobs, selectedJobId]);

  // Le job auto-sélectionné a disparu de la liste filtrée -> repointer sur le
  // premier. Si l'opérateur a cliqué, on ne touche à rien.
  useEffect(() => {
    if (userPickedRef.current || !selectedJobId || filteredJobs.length === 0) return;
    if (!filteredJobs.some(j => j.id === selectedJobId)) {
      setSelectedJobId(filteredJobs[0].id);
    }
  }, [filteredJobs, selectedJobId]);

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

  return (
    <div className="p-4 flex flex-col gap-6 max-w-[1400px]">
      <AlertsBanner token={token} />

      {/* Hero */}
      <div className="flex items-end justify-between gap-4">
        <div className="min-w-0">
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
            {loading ? '—' : `${globalStats.total} jobs au total`}
            {replicaList.length > 0 ? ` · ${replicaList.length} replicas actifs` : ''}
          </p>
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
        />

        {/* En cours — valeur = compteur serveur, pas le comptage des documents */}
        <div className="relative">
          <StatTile
            label="En cours"
            value={loading && capacityLoading ? null : String(runningDisplay)}
            accent="var(--accent)"
            sub={totalSlots > 0 ? `/ ${totalSlots} slots` : undefined}
            note={stuckRunning > 0 ? (
              <span
                title={`${stuckRunning} document(s) au statut « running » sans heartbeat récent — non compté(s) par le crawler-service`}
              >
                +{stuckRunning} présumé{stuckRunning > 1 ? 's' : ''} bloqué{stuckRunning > 1 ? 's' : ''}
              </span>
            ) : undefined}
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

        {/* Archivés — pas de fenêtre temporelle : c'est un cumul */}
        <StatTile
          label="Archivés"
          value={loading ? null : String(globalStats.archived)}
          accent="var(--hairline-strong)"
        />
      </div>

      {/* Timeline + Capacity */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_360px]">
        <SectionCard
          icon={Activity}
          title="Timeline d'activité"
          subtitle="Volume de jobs par heure · fenêtre glissante 24h"
        >
          <UiTimeline data={timelineData} />
          {/* Legend strip */}
          <div className="flex gap-4 mt-3.5 pt-3 border-t border-hairline items-center flex-wrap">
            <LegendItem color="var(--ok)"   label="Terminés" count={globalStats.finished} />
            <LegendItem
              color="var(--warn)"
              label="Actifs"
              count={globalStats.inFlight}
              title="Jobs dans un statut non terminal (running, starting, stopping…) — à ne pas confondre avec la tuile « En cours », qui affiche le compteur du crawler-service"
            />
            <LegendItem color="var(--err)"  label="Échecs"   count={globalStats.failed} />
          </div>
        </SectionCard>

        <SectionCard
          icon={Cpu}
          title="Capacité globale"
          subtitle={capacityLoading
            ? 'Chargement…'
            : `${capacity?.running_jobs ?? 0} / ${capacity?.max_global_jobs ?? totalSlots} slots utilisés`}
        >
          {capacityLoading ? (
            <div className="flex items-center justify-center">
              <div className="h-[160px] w-[160px] rounded-full animate-shimmer" />
            </div>
          ) : (
            <CapacityRing
              used={capacity?.running_jobs ?? 0}
              total={Math.max(1, capacity?.max_global_jobs || totalSlots || 1)}
              format="count"
            />
          )}
          {/* Replica list with mini progress bars */}
          <div className="mt-4 flex flex-col gap-2">
            {replicaList.length > 0 ? replicaList.map(r => (
              <div key={r.replicaId} className="flex items-center gap-2 text-[11.5px]">
                <Server size={12} className="text-ink-3 flex-shrink-0" />
                <span className="font-mono text-ink-1 shrink-0 truncate max-w-[120px]">
                  {r.replicaId?.substring(0, 8) ?? '—'}
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
            <Pill tone="accent" dot>
              {replicaList.length} actif{replicaList.length > 1 ? 's' : ''}
            </Pill>
          }
        >
          <div className="grid grid-cols-2 gap-2.5 md:grid-cols-4">
            {replicaList.map(r => {
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
                  className="rounded-md border border-hairline bg-bg-0 p-3.5 min-w-0"
                >
                  <div className="flex items-center justify-between gap-2 mb-2.5">
                    <span className="font-mono text-[11px] text-ink-2 truncate">
                      {String(r.replicaId ?? '').substring(0, 12)}
                    </span>
                    {/* Le heartbeat n'est émis que par un replica en marche :
                        tout autre statut serait une branche morte. */}
                    <Pill tone="accent" dot>actif</Pill>
                  </div>
                  {r.domain && (
                    <div className="text-[11px] text-ink-2 mb-2.5 truncate" title={r.domain}>
                      {r.domain}
                    </div>
                  )}
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
      <div ref={jobsListRef} className="grid grid-cols-1 lg:grid-cols-[440px_1fr] gap-4 scroll-mt-16">
        {/* Jobs list panel (440px) */}
        <div className="bg-surface rounded-lg border border-hairline shadow-sm overflow-hidden min-w-0">
          {/* Toolbar */}
          <div className="px-5 py-4 border-b border-hairline space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-[13px] font-semibold text-ink-0">
                Jobs ({loading ? '…' : filteredJobs.length})
              </p>
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
                  aria-label="Filtrer par statut"
                  className="h-9 appearance-none rounded-md border border-hairline bg-bg-1 pl-8 pr-8 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
                >
                  <option value="all">Tous les statuts</option>
                  {statusOptions.map(opt => (
                    <option key={opt.value} value={opt.value}>
                      {opt.count > 0 ? `${opt.label} (${opt.count})` : opt.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center gap-1.5">
                <Calendar className="h-4 w-4 text-ink-3" />
                <Input
                  type="date"
                  value={startDate}
                  onChange={e => { setStartDate(e.target.value); setCurrentPage(1); }}
                  className="w-[130px]"
                  aria-label="Date de début"
                />
                <span className="text-ink-3 text-sm">→</span>
                <Input
                  type="date"
                  value={endDate}
                  onChange={e => { setEndDate(e.target.value); setCurrentPage(1); }}
                  className="w-[130px]"
                  aria-label="Date de fin"
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
                    onClick={() => setCurrentPage(Math.max(1, safePage - 1))}
                    disabled={safePage <= 1}
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
                      value={safePage}
                      onChange={(e) => {
                        const val = parseInt(e.target.value, 10);
                        if (!isNaN(val) && val >= 1 && val <= totalPages) {
                          setCurrentPage(val);
                        }
                      }}
                      className="h-8 w-14 px-2 text-center font-mono"
                      aria-label="Numéro de page"
                    />
                    <span className="text-xs text-ink-3">/ {totalPages}</span>
                  </div>
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => setCurrentPage(Math.min(totalPages, safePage + 1))}
                    disabled={safePage >= totalPages}
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
                  <Pill tone={statusTone(job.status)}>{statusLabel(job.status)}</Pill>
                  <span className="flex-1 text-[13px] text-ink-0 truncate font-mono">{job.domain}</span>
                  <span className="text-[11px] text-ink-3 tabular-nums font-mono">
                    {formatApiDate(job.start_time)}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Job detail panel (1fr) */}
        <div
          className={cn(
            'bg-surface rounded-lg border border-hairline shadow-sm min-w-0 overflow-hidden',
            paginatedJobs.length === 0 && 'hidden lg:hidden',
            !selectedJob && !loadingDetails && paginatedJobs.length > 0 && 'flex items-center justify-center'
          )}
        >
          {loadingDetails ? (
            <div className="flex items-center justify-center py-20 p-5">
              <RefreshCw className="h-10 w-10 animate-spin text-accent" />
            </div>
          ) : paginatedJobs.length === 0 ? null : selectedJob ? (
            <div className="p-5 overflow-y-auto min-w-0">
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
    </div>
  );
};

export default Overview;
