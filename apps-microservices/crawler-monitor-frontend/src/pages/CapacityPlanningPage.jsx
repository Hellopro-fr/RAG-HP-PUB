import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  SlidersHorizontal, RefreshCw, AlertCircle, TrendingDown, Cpu,
} from 'lucide-react';
import { useCapacityPlanningQuery, useJobsQuery, useCapacityHistoryQuery } from '../hooks/queries';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '../components/ui/table';
import {
  Tooltip, TooltipTrigger, TooltipContent,
} from '../components/ui/tooltip';
import { cn } from '../lib/utils';
import { CoherencePastille } from '../coherence/components/CoherencePastille';
import Pill from '../components/ui/Pill';
import StatTile from '../components/ui/StatTile';
import AreaChart from '../components/ui/AreaChart';
import ProjCard from '../components/ui/ProjCard';

const GB = 1024 * 1024 * 1024;

const fmtBytes = (b) => {
  if (b === null || b === undefined) return '—';
  if (b >= GB) return `${(b / GB).toFixed(2)} GB`;
  if (b >= 1024 * 1024) return `${(b / 1024 / 1024).toFixed(0)} MB`;
  return `${b} B`;
};

const fmtPct = (v) => v == null ? '—' : `${(v * 100).toFixed(1)}%`;
const fmtDate = (ts) => ts ? new Date(ts).toLocaleString('fr-FR') : '—';

const shortJobId = (id) => {
  if (!id) return '';
  const s = String(id);
  return s.length > 8 ? s.slice(0, 8) : s;
};

const efficiencyColor = (pct) => {
  if (pct >= 0.85) return 'text-err';
  if (pct >= 0.70) return 'text-warn';
  if (pct >= 0.40) return 'text-info';
  return 'text-ok';
};

const efficiencyBar = (pct) => {
  if (pct >= 0.85) return 'bg-err';
  if (pct >= 0.70) return 'bg-warn';
  if (pct >= 0.40) return 'bg-info';
  return 'bg-ok';
};

/**
 * Capacity planning — answer "can we reduce RAM per replica?".
 */
const CapacityPlanningPage = ({ token }) => {
  const [windowKey, setWindowKey] = useState('1h');
  const [marginPct, setMarginPct] = useState(30);
  const query = useCapacityPlanningQuery(token, windowKey);
  const jobsQuery = useJobsQuery(token);
  const historyQuery = useCapacityHistoryQuery(token, windowKey);
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

  // AreaChart data
  const historyPoints = historyQuery.data?.points || [];
  const ramMbData = historyPoints.map(p => (p.ram_bytes ?? p.ram ?? 0) / 1024 / 1024);
  const allocatedMb = totals ? totals.total_allocated / 1024 / 1024 : undefined;

  return (
    <div className="p-5">
      {/* Hero */}
      <div className="flex items-center gap-3 mb-5">
        <SlidersHorizontal className="h-5 w-5 text-ink-2" />
        <h1 className="text-[26px] font-semibold tracking-[-0.025em] text-ink-0 font-display">Capacity Planning</h1>
        <Pill tone="info" dot>simulation prête</Pill>
        <div className="ml-auto flex items-center gap-3">
          <div className="flex gap-0.5 rounded-md border border-hairline bg-bg-2 p-0.5">
            {['1h', '24h', '7d'].map(w => (
              <button
                key={w}
                onClick={() => setWindowKey(w)}
                className={cn('rounded px-2.5 py-1 text-[11px] font-medium transition-colors',
                  w === windowKey ? 'bg-surface text-ink-0 shadow-sm' : 'text-ink-2 hover:text-ink-1'
                )}
              >
                {w}
              </button>
            ))}
          </div>
          <button
            onClick={() => query.refetch()}
            disabled={query.isFetching}
            aria-label="Rafraîchir"
            className="p-1.5 rounded-md hover:bg-bg-2 text-ink-2"
          >
            <RefreshCw className={cn('h-4 w-4', query.isFetching && 'animate-spin')} />
          </button>
        </div>
      </div>

      {query.isError && (
        <div className="flex items-center gap-2 mb-5 rounded-lg border border-err/20 bg-err-soft px-4 py-2 text-sm text-err">
          <AlertCircle className="h-4 w-4" /> {query.error?.message || 'Erreur de chargement'}
        </div>
      )}

      {query.isLoading && !data ? (
        <div className="flex items-center justify-center py-20">
          <RefreshCw className="h-6 w-6 animate-spin text-ink-3" />
        </div>
      ) : replicas.length === 0 ? (
        <div className="py-16 text-center text-ink-2">
          <p className="text-sm">Aucun sample de replica dans la fenêtre {windowKey}.</p>
          <p className="mt-1 text-xs">Attends quelques heartbeats et réessaie.</p>
        </div>
      ) : !totals ? (
        <div className="py-16 text-center text-ink-2">
          <AlertCircle className="mx-auto mb-3 h-10 w-10 opacity-40" />
          <p className="text-sm">Totaux indisponibles — retente dans quelques secondes.</p>
        </div>
      ) : (
        <>
          {/* KPI Strip — StatTile */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
            <StatTile
              label="Alloué total"
              value={fmtBytes(totals.total_allocated)}
              sub="GB"
              accent="var(--ink-1)"
            />
            <StatTile
              label="Peak réel"
              value={fmtBytes(totals.total_peak_worst)}
              sub="GB"
              accent="var(--ok)"
            />
            <StatTile
              label="Gaspillage"
              value={fmtBytes(totals.waste)}
              sub={`${fmtPct(totals.waste_pct)}`}
              accent="var(--err)"
            />
            <StatTile
              label="Efficience"
              value={fmtPct(totals.efficiency)}
              accent="var(--accent)"
            />
          </div>

          {/* AreaChart RAM — wrapped in card */}
          <div className="mb-5 rounded-lg border border-hairline bg-surface overflow-hidden">
            {/* Card header */}
            <div className="flex items-center gap-2 px-4 py-3 border-b border-hairline">
              <Cpu className="h-4 w-4 text-ink-3 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="text-[13px] font-semibold text-ink-0">RAM usage — 1h</div>
                <div className="text-[11px] text-ink-3">fenêtre {windowKey}</div>
              </div>
              {/* Legend */}
              <div className="flex items-center gap-4 text-[11px]">
                <span className="flex items-center gap-1.5">
                  <span className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: 'var(--accent)' }} />
                  <span className="text-ink-2">Utilisation</span>
                  {allocatedMb != null && (
                    <span className="font-mono text-ink-1">{(allocatedMb > 1024 ? (allocatedMb / 1024).toFixed(2) + 'G' : Math.round(allocatedMb) + 'M')}</span>
                  )}
                </span>
                {allocatedMb != null && (
                  <span className="flex items-center gap-1.5">
                    <span className="inline-block w-2.5 h-[2px] flex-shrink-0 border-t-2 border-dashed" style={{ borderColor: 'var(--err)' }} />
                    <span className="text-ink-2">Capacité</span>
                    <span className="font-mono text-ink-1">{(allocatedMb > 1024 ? (allocatedMb / 1024).toFixed(2) + 'G' : Math.round(allocatedMb) + 'M')}</span>
                  </span>
                )}
              </div>
            </div>
            <div className="p-4">
              {historyQuery.isError && (
                <p className="text-[11px] italic text-ink-3 mb-2">Historique indisponible.</p>
              )}
              <AreaChart
                data={ramMbData}
                w={900}
                h={120}
                color="var(--accent)"
                refLine={allocatedMb}
              />
            </div>
          </div>

          {/* Per-replica table */}
          <div className="mb-5 rounded-lg border border-hairline overflow-hidden">
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
                  {replicas.map((r, idx) => {
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
                      <TableRow key={r.replicaId ?? idx}>
                        <TableCell className="max-w-[200px] truncate font-mono text-xs text-ink-0" title={r.replicaId}>
                          {(r.replicaId ?? '').slice(0, 20)}
                        </TableCell>
                        <TableCell className="text-right font-mono text-ink-3">{fmtBytes(r.allocated)}</TableCell>
                        <TableCell className="text-right">
                          <span className="inline-flex items-center gap-1">
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
                                      <div className="font-mono text-ink-3">
                                        job #{shortJobId(r.peak_job_id)}
                                      </div>
                                    ) : null}
                                  </div>
                                </TooltipContent>
                              </Tooltip>
                            ) : peakNode}
                            <CoherencePastille
                              ruleId="peak_ram_exceeds_allocated"
                              itemKey={r.replicaId}
                            />
                          </span>
                        </TableCell>
                        <TableCell className="text-right font-mono text-ink-3">{fmtBytes(r.avg)}</TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <div className="h-1.5 max-w-[120px] flex-1 overflow-hidden rounded-full bg-bg-2">
                              <div className={cn('h-full', efficiencyBar(r.efficiency))} style={{ width: `${Math.min(r.efficiency * 100, 100)}%` }} />
                            </div>
                            <span className={cn('font-mono text-xs font-semibold', efficiencyColor(r.efficiency))}>
                              {fmtPct(r.efficiency)}
                            </span>
                          </div>
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs text-ink-3">{r.sample_count}</TableCell>
                        <TableCell className="whitespace-nowrap font-mono text-xs text-ink-3">{fmtDate(r.last_seen)}</TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </div>

          {/* Simulator */}
          <div className="rounded-lg border border-hairline bg-bg-1 overflow-hidden">
            <div className="p-5">
              <div className="flex items-center gap-2 mb-4">
                <TrendingDown className="h-4 w-4 text-ok" />
                <span className="text-[13px] font-semibold text-ink-0">Simulateur — réduire la RAM par replica</span>
              </div>

              {/* Slider */}
              <label className="flex items-center gap-3 mb-5">
                <span className="text-[12px] text-ink-2 whitespace-nowrap">Marge de sécurité :</span>
                <input
                  type="range" min={10} max={100} step={5}
                  value={marginPct}
                  onChange={e => setMarginPct(Number(e.target.value))}
                  className="flex-1 max-w-[320px] accent-[var(--accent)]"
                />
                <span className="font-mono text-[13px] text-ink-0 w-10 text-right">{marginPct}%</span>
              </label>

              {/* 3 ProjCards */}
              <div className="grid grid-cols-3 gap-4 mb-4">
                <ProjCard
                  tone="accent"
                  label="Target par replica"
                  value={`${targetPerReplicaGB.toFixed(2)} GB`}
                  sub={`peak global × ${(1 + marginPct / 100).toFixed(2)} — actuel ${currentPerReplicaGB.toFixed(1)} GB`}
                />
                <ProjCard
                  tone="ok"
                  label="Replicas possibles (même RAM totale)"
                  value={`${simulatedReplicaCount}`}
                  sub={`vs ${replicas.length} actuels · ${totalAllocatedGB.toFixed(0)} GB alloués`}
                />
                <ProjCard
                  tone="warn"
                  label="Économie (même nb replicas)"
                  value={`${simulatedSavingsGB >= 0 ? '-' : '+'}${Math.abs(simulatedSavingsGB).toFixed(1)} GB`}
                  sub={`nouveau total : ${simulatedTotalGB.toFixed(1)} GB · ${fmtPct(Math.abs(simulatedSavingsPct))}`}
                />
              </div>

              {/* At-risk replicas */}
              {atRiskReplicas.length > 0 && (
                <div className="rounded-lg border border-warn/25 bg-warn-soft p-3 mb-3">
                  <div className="flex items-center gap-2 text-[12px] font-semibold text-warn mb-1">
                    <AlertCircle className="h-4 w-4" />
                    {atRiskReplicas.length} replica{atRiskReplicas.length > 1 ? 's' : ''} proche{atRiskReplicas.length > 1 ? 's' : ''} de la limite
                  </div>
                  <ul className="font-mono text-[11px] text-warn space-y-0.5">
                    {atRiskReplicas.slice(0, 5).map((r, idx) => (
                      <li key={r.replicaId ?? idx}>· {(r.replicaId ?? '').slice(0, 24)} → {fmtPct(r.efficiency)} de {fmtBytes(r.allocated)}</li>
                    ))}
                    {atRiskReplicas.length > 5 && <li className="italic text-warn/70">… et {atRiskReplicas.length - 5} autre{atRiskReplicas.length - 5 > 1 ? 's' : ''}</li>}
                  </ul>
                </div>
              )}

              <p className="text-[11px] italic text-ink-3">
                Note : le peak affiché est sur la fenêtre {windowKey}. Pour une décision en prod, valide sur 7 jours.
              </p>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default CapacityPlanningPage;
