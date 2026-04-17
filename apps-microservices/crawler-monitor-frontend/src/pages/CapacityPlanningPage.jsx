import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  SlidersHorizontal, RefreshCw, AlertCircle, TrendingDown, TrendingUp, Server,
} from 'lucide-react';
import { useCapacityPlanningQuery, useJobsQuery } from '../hooks/queries';
import { Card } from '../components/ui/card';
import { Button } from '../components/ui/button';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '../components/ui/table';
import {
  Tooltip, TooltipTrigger, TooltipContent,
} from '../components/ui/tooltip';
import { cn } from '../lib/utils';

const GB = 1024 * 1024 * 1024;

const fmtBytes = (b) => {
  if (b === null || b === undefined) return '—';
  if (b >= GB) return `${(b / GB).toFixed(2)} GB`;
  if (b >= 1024 * 1024) return `${(b / 1024 / 1024).toFixed(0)} MB`;
  return `${b} B`;
};

const fmtPct = (v) => `${(v * 100).toFixed(1)}%`;
const fmtDate = (ts) => ts ? new Date(ts).toLocaleString('fr-FR') : '—';

const WINDOW_OPTIONS = [
  { key: '1h',  label: 'Dernière heure' },
  { key: '24h', label: 'Dernières 24h' },
  { key: '7d',  label: '7 derniers jours' },
];

const efficiencyColor = (pct) => {
  if (pct >= 0.85) return 'text-destructive';
  if (pct >= 0.70) return 'text-warning';
  if (pct >= 0.40) return 'text-info';
  return 'text-success';
};

const efficiencyBar = (pct) => {
  if (pct >= 0.85) return 'bg-destructive';
  if (pct >= 0.70) return 'bg-warning';
  if (pct >= 0.40) return 'bg-info';
  return 'bg-success';
};

const shortJobId = (id) => {
  if (!id) return '';
  const s = String(id);
  return s.length > 8 ? s.slice(0, 8) : s;
};

/**
 * Capacity planning — answer "can we reduce RAM per replica?".
 */
const CapacityPlanningPage = ({ token }) => {
  const [windowKey, setWindowKey] = useState('1h');
  const [marginPct, setMarginPct] = useState(30);
  const query = useCapacityPlanningQuery(token, windowKey);
  // Pour joindre peak_job_id → domaine (évite de re-fetch par job)
  const jobsQuery = useJobsQuery(token);
  const data = query.data;

  const replicas = data?.replicas || [];
  const totals = data?.totals || null;

  const jobsById = useMemo(() => {
    const jobs = jobsQuery.data || [];
    return new Map(jobs.map(j => [j.id, j]));
  }, [jobsQuery.data]);

  const globalPeak = useMemo(() => {
    if (!replicas.length) return 0;
    return Math.max(...replicas.map(r => r.peak || 0));
  }, [replicas]);

  const targetPerReplicaGB = useMemo(() => {
    const target = globalPeak * (1 + marginPct / 100);
    return target / GB;
  }, [globalPeak, marginPct]);

  const currentPerReplicaGB = useMemo(() => {
    if (!replicas.length) return 0;
    return Math.max(...replicas.map(r => r.allocated || 0)) / GB;
  }, [replicas]);

  const totalAllocatedGB = totals ? (totals.total_allocated ?? 0) / GB : 0;
  const simulatedReplicaCount = targetPerReplicaGB > 0
    ? Math.floor(totalAllocatedGB / targetPerReplicaGB)
    : 0;

  const simulatedTotalGB = targetPerReplicaGB * (replicas.length || 1);
  const simulatedSavingsGB = totalAllocatedGB - simulatedTotalGB;
  const simulatedSavingsPct = totalAllocatedGB > 0 ? simulatedSavingsGB / totalAllocatedGB : 0;

  const atRiskReplicas = useMemo(
    () => replicas.filter(r => r.efficiency >= 0.7),
    [replicas]
  );

  return (
    <div className="p-4">
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border p-4">
          <h2 className="flex items-center gap-2 text-base font-semibold">
            <SlidersHorizontal className="h-4 w-4 text-primary" />
            Capacity Planning — RAM
          </h2>
          <div className="flex items-center gap-2">
            <div className="flex gap-0.5 rounded-md border border-border bg-muted p-0.5">
              {WINDOW_OPTIONS.map(w => (
                <button
                  key={w.key}
                  onClick={() => setWindowKey(w.key)}
                  className={cn(
                    'rounded px-2.5 py-0.5 text-xs transition-colors',
                    w.key === windowKey
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                  )}
                  title={w.label}
                >
                  {w.key}
                </button>
              ))}
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => query.refetch()}
              disabled={query.isFetching}
              title="Rafraîchir"
            >
              <RefreshCw className={cn('h-4 w-4', query.isFetching && 'animate-spin')} />
            </Button>
          </div>
        </div>

        {query.isError && (
          <div className="flex items-center gap-2 border-b border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" /> {query.error?.message || 'Erreur de chargement'}
          </div>
        )}

        {query.isLoading && !data ? (
          <div className="flex items-center justify-center py-20">
            <RefreshCw className="h-6 w-6 animate-spin text-primary" />
          </div>
        ) : replicas.length === 0 ? (
          <div className="py-16 text-center text-muted-foreground">
            <Server className="mx-auto mb-3 h-10 w-10 opacity-40" />
            <p className="text-sm">Aucun sample de replica dans la fenêtre {windowKey}.</p>
            <p className="mt-1 text-xs">Attends quelques heartbeats et réessaie.</p>
          </div>
        ) : !totals ? (
          // Fix 2a : guarde sur totals (backend peut renvoyer null si erreur agrégat)
          <div className="py-16 text-center text-muted-foreground">
            <AlertCircle className="mx-auto mb-3 h-10 w-10 opacity-40" />
            <p className="text-sm">Totaux indisponibles — retente dans quelques secondes.</p>
          </div>
        ) : (
          <>
            {/* KPI row */}
            <div className="grid grid-cols-2 gap-3 border-b border-border p-4 md:grid-cols-4">
              <KpiTile
                label="Alloué total"
                value={fmtBytes(totals.total_allocated)}
                sub={`${replicas.length} × ${fmtBytes(totals.total_allocated / replicas.length)}`}
              />
              <KpiTile
                label="Peak réel (pire cas simul.)"
                value={fmtBytes(totals.total_peak_worst)}
                valueClass="text-info"
                sub={`Moyenne: ${fmtBytes(totals.total_avg)}`}
              />
              <KpiTile
                label="Gaspillage"
                value={fmtBytes(totals.waste)}
                valueClass="text-warning"
                sub={`${fmtPct(totals.waste_pct)} du total`}
              />
              <KpiTile
                label="Efficience globale"
                value={fmtPct(totals.efficiency)}
                valueClass={efficiencyColor(totals.efficiency)}
                sub="peak / alloué"
              />
            </div>

            {/* Per-replica breakdown */}
            <div className="max-h-[45vh] overflow-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Replica</TableHead>
                    <TableHead className="text-right">Alloué</TableHead>
                    <TableHead className="text-right">Peak</TableHead>
                    <TableHead className="text-right">Moyenne</TableHead>
                    <TableHead>Efficience</TableHead>
                    <TableHead className="text-right">Samples</TableHead>
                    <TableHead>Dernier heartbeat</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {replicas.map(r => {
                    // Fix 2b : join peak_job_id → domaine pour le tooltip
                    const peakJob = r.peak_job_id ? jobsById.get(r.peak_job_id) : null;
                    const canLink = Boolean(r.peak_job_id);
                    const peakLabel = fmtBytes(r.peak);
                    const peakNode = canLink ? (
                      <Link
                        to={`/jobs/${r.peak_job_id}`}
                        className="font-mono text-info underline-offset-2 hover:underline"
                      >
                        {peakLabel}
                      </Link>
                    ) : (
                      <span className="font-mono text-info">{peakLabel}</span>
                    );
                    const canTooltip = canLink || !!r.peak_ts;
                    return (
                      <TableRow key={r.replicaId}>
                        <TableCell className="max-w-[200px] truncate font-mono text-xs text-foreground" title={r.replicaId}>
                          {r.replicaId.slice(0, 20)}
                        </TableCell>
                        <TableCell className="text-right font-mono text-muted-foreground">{fmtBytes(r.allocated)}</TableCell>
                        <TableCell className="text-right">
                          {canTooltip ? (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span className="inline-block">{peakNode}</span>
                              </TooltipTrigger>
                              <TooltipContent>
                                <div className="space-y-0.5 text-xs">
                                  {peakJob?.domain && (
                                    <div className="font-semibold">{peakJob.domain}</div>
                                  )}
                                  {r.peak_ts ? <div>{fmtDate(r.peak_ts)}</div> : null}
                                  {r.peak_job_id ? (
                                    <div className="font-mono text-muted-foreground">
                                      job #{shortJobId(r.peak_job_id)}
                                    </div>
                                  ) : null}
                                </div>
                              </TooltipContent>
                            </Tooltip>
                          ) : peakNode}
                        </TableCell>
                        <TableCell className="text-right font-mono text-muted-foreground">{fmtBytes(r.avg)}</TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <div className="h-1.5 max-w-[120px] flex-1 overflow-hidden rounded-full bg-muted">
                              <div className={cn('h-full', efficiencyBar(r.efficiency))} style={{ width: `${Math.min(r.efficiency * 100, 100)}%` }} />
                            </div>
                            <span className={cn('font-mono text-xs font-semibold', efficiencyColor(r.efficiency))}>
                              {fmtPct(r.efficiency)}
                            </span>
                          </div>
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs text-muted-foreground">{r.sample_count}</TableCell>
                        <TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">{fmtDate(r.last_seen)}</TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>

            {/* Simulation */}
            <div className="border-t border-border bg-muted/20 p-4">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
                <TrendingDown className="h-4 w-4 text-success" />
                Simulation — réduire la RAM par replica
              </div>
              <div className="mb-4">
                <label className="flex items-center gap-3 text-sm text-foreground">
                  <span className="whitespace-nowrap text-muted-foreground">Marge de sécurité sur peak :</span>
                  <input
                    type="range"
                    min={10}
                    max={100}
                    step={5}
                    value={marginPct}
                    onChange={e => setMarginPct(Number(e.target.value))}
                    className="max-w-md flex-1 accent-primary"
                  />
                  <span className="w-12 text-right font-mono">{marginPct}%</span>
                </label>
              </div>

              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                <SimTile
                  label="Target par replica"
                  value={`${targetPerReplicaGB.toFixed(2)} GB`}
                  sub={`peak global (${fmtBytes(globalPeak)}) × ${(1 + marginPct / 100).toFixed(2)}`}
                  extra={<>vs actuel : <span className="text-info">{currentPerReplicaGB.toFixed(1)} GB</span></>}
                />
                <SimTile
                  label="Sur même total RAM"
                  value={`${simulatedReplicaCount} replicas`}
                  valueClass="text-success"
                  sub={`vs ${replicas.length} actuels (${totalAllocatedGB.toFixed(0)} GB alloués)`}
                  extra={simulatedReplicaCount > replicas.length && (
                    <span className="flex items-center gap-1 text-success">
                      <TrendingUp className="h-3 w-3" /> +{simulatedReplicaCount - replicas.length} replicas possibles
                    </span>
                  )}
                />
                <SimTile
                  label="Avec même nb replicas"
                  value={`${simulatedSavingsGB > 0 ? '-' : '+'}${Math.abs(simulatedSavingsGB).toFixed(1)} GB`}
                  valueClass="text-success"
                  sub={`nouveau total : ${simulatedTotalGB.toFixed(1)} GB`}
                  extra={simulatedSavingsPct > 0 && (
                    <span className="flex items-center gap-1 text-success">
                      <TrendingDown className="h-3 w-3" /> {fmtPct(simulatedSavingsPct)} d&apos;économie
                    </span>
                  )}
                />
              </div>

              {atRiskReplicas.length > 0 && (
                <div className="mt-4 rounded-md border border-warning/40 bg-warning/10 p-3">
                  <div className="flex items-center gap-2 text-xs font-semibold text-warning">
                    <AlertCircle className="h-4 w-4" />
                    {atRiskReplicas.length} replica{atRiskReplicas.length > 1 ? 's' : ''} proche{atRiskReplicas.length > 1 ? 's' : ''} de la limite
                  </div>
                  <div className="mt-1 text-[11px] text-warning/80">
                    Ces replicas dépassent 70% d&apos;utilisation — à surveiller avant toute réduction :
                  </div>
                  <ul className="mt-1 space-y-0.5 font-mono text-[11px] text-warning">
                    {atRiskReplicas.slice(0, 5).map(r => (
                      <li key={r.replicaId}>
                        · {r.replicaId.slice(0, 24)} → {fmtPct(r.efficiency)} de {fmtBytes(r.allocated)}
                      </li>
                    ))}
                    {atRiskReplicas.length > 5 && (
                      <li className="italic text-warning/70">
                        · … et {atRiskReplicas.length - 5} autre{atRiskReplicas.length - 5 > 1 ? 's' : ''}
                      </li>
                    )}
                  </ul>
                </div>
              )}

              <div className="mt-3 text-[10px] italic text-muted-foreground">
                Note : le peak affiché est sur la fenêtre {windowKey}. Pour une décision en prod,
                valide sur 7 jours et valide que la charge observée est représentative
                (saisonnalité, creux vs pics).
              </div>
            </div>
          </>
        )}
      </Card>
    </div>
  );
};

const KpiTile = ({ label, value, valueClass = 'text-foreground', sub }) => (
  <div className="rounded-md border border-border bg-muted/30 p-3">
    <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
    <div className={cn('font-mono text-xl font-bold tracking-tight', valueClass)}>{value}</div>
    {sub && <div className="mt-0.5 text-[10px] text-muted-foreground">{sub}</div>}
  </div>
);

const SimTile = ({ label, value, valueClass = 'text-foreground', sub, extra }) => (
  <div className="rounded-md border border-border bg-background p-3">
    <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
    <div className={cn('font-mono text-lg font-bold', valueClass)}>{value}</div>
    {sub && <div className="mt-0.5 text-[10px] text-muted-foreground">{sub}</div>}
    {extra && <div className="mt-1 text-[10px]">{extra}</div>}
  </div>
);

export default CapacityPlanningPage;
