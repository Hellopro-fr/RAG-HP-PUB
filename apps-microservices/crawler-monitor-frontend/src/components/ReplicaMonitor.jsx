import { useMemo, memo } from 'react';
import { Server, Cpu } from 'lucide-react';
import { ResponsiveContainer, LineChart, Line, YAxis, Tooltip } from 'recharts';
import { useJobsQuery, useReplicasHistoryQuery } from '../hooks/queries';
import { Card } from './ui/card';
import { cn } from '../lib/utils';
import { isReplicaLive, replicaAge } from '../lib/replicas';
import { CoherencePastille } from '../coherence/components/CoherencePastille';

/**
 * ReplicaMonitor
 *
 * Per-replica card showing:
 *  - Connection dot (green/yellow/red based on heartbeat age)
 *  - Mode badge (update / standard) cross-referenced from jobs list via jobId
 *  - Domain currently being crawled
 *  - CPU + RAM circular progress
 *  - Top RAM processes (sorted desc, top 5, color-coded)
 *  - 1h sparkline of CPU% (from /api/replicas/history)
 *
 * `replicas` is the live state pushed via WebSocket heartbeats (App.jsx).
 */
const ReplicaMonitor = ({ replicas, token }) => {
  const jobsQuery = useJobsQuery(token);
  const historyQuery = useReplicasHistoryQuery(token, '1h');
  const allJobs = jobsQuery.data || [];
  const historyByReplica = historyQuery.data?.replicas || {};

  const jobsById = useMemo(() => {
    const m = new Map();
    for (const j of allJobs) if (j.id) m.set(j.id, j);
    return m;
  }, [allJobs]);

  const formatBytes = (bytes) => {
    if (!bytes) return '0 MB';
    return `${(bytes / 1024 / 1024).toFixed(0)} MB`;
  };
  const formatCpu = (load) => (load ? `${(load * 100).toFixed(1)}%` : '0%');

  const getStatusClass = (replica) => {
    const age = replicaAge(replica);
    if (age < 5000)  return 'bg-ok animate-pulse';
    if (age < 15000) return 'bg-warn';
    return 'bg-err';
  };

  const CircularProgress = ({ cpu, ram, totalRam }) => {
    const size = 140;
    const strokeWidth = 12;
    const radius = (size - strokeWidth) / 2;
    const circumference = 2 * Math.PI * radius;

    const cpuPercent = Math.min((cpu || 0) * 100, 100);
    const ramLimit = totalRam || (6 * 1024 * 1024 * 1024);
    const ramPercent = Math.min((ram / ramLimit) * 100, 100);

    const cpuOffset = circumference - (cpuPercent / 100) * circumference;
    const ramOffset = circumference - (ramPercent / 100) * circumference;

    return (
      <svg width={size} height={size} className="-rotate-90 transform">
        <circle cx={size / 2} cy={size / 2} r={radius - 18} fill="none" stroke="hsl(var(--muted))" strokeWidth={strokeWidth} />
        <circle cx={size / 2} cy={size / 2} r={radius}      fill="none" stroke="hsl(var(--muted))" strokeWidth={strokeWidth} />
        <circle cx={size / 2} cy={size / 2} r={radius - 18} fill="none" stroke="hsl(var(--info))"    strokeWidth={strokeWidth}
          strokeDasharray={circumference} strokeDashoffset={cpuOffset} strokeLinecap="round" className="transition-all duration-500" />
        <circle cx={size / 2} cy={size / 2} r={radius}      fill="none" stroke="hsl(var(--primary))" strokeWidth={strokeWidth}
          strokeDasharray={circumference} strokeDashoffset={ramOffset} strokeLinecap="round" className="transition-all duration-500" />
      </svg>
    );
  };

  const activeReplicas = Object.values(replicas).filter(
    r => r && r.replicaId && isReplicaLive(r)
  );

  return (
    <Card className="p-4">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-ink-3">
          <Server className="h-4 w-4 text-accent" />
          Crawler Replicas
          <span className="font-mono text-xs normal-case text-ink-3 tracking-normal">
            ({activeReplicas.length} actifs)
          </span>
        </h2>
      </div>

      {activeReplicas.length === 0 ? (
        <div className="py-12 text-center text-ink-3">
          <Server className="mx-auto mb-3 h-12 w-12 opacity-40" />
          <p className="text-sm">Aucun replica actif</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {activeReplicas.map((replica) => {
            const statusClass = getStatusClass(replica);
            const linkedJob = replica.jobId ? jobsById.get(replica.jobId) : null;
            const crawlMode = linkedJob?.crawl_mode;
            const history = historyByReplica[replica.replicaId] || [];
            const cpuSeries = history.map(p => ({ ts: p.ts, cpu: (p.cpu || 0) * 100 }));

            return (
              <div
                key={replica.replicaId}
                className="rounded-md border border-hairline bg-bg-1 p-4 transition-colors hover:border-muted-foreground/40"
              >
                <div className="mb-3 flex items-center justify-between">
                  <div className="flex min-w-0 flex-1 items-center gap-2">
                    <div className={cn('h-2.5 w-2.5 shrink-0 rounded-full', statusClass)} />
                    <span className="truncate font-mono text-xs font-semibold text-ink-0">
                      {String(replica.replicaId || '').substring(0, 12)}
                    </span>
                    <CoherencePastille ruleId="replica_job_mapping" itemKey={replica.replicaId} />
                  </div>
                  <Cpu className="h-4 w-4 shrink-0 text-accent" />
                </div>

                <div className="mb-3 flex flex-col items-center">
                  <div className="relative">
                    <CircularProgress cpu={replica.cpu} ram={replica.ram} totalRam={replica.totalRam} />
                    <div className="absolute inset-0 flex items-center justify-center">
                      <div className="text-center">
                        <div className="text-[10px] uppercase tracking-wider text-ink-3">CPU</div>
                        <div className="font-mono text-lg font-bold text-info">{formatCpu(replica.cpu)}</div>
                        <div className="mt-1 text-[10px] uppercase tracking-wider text-ink-3">RAM</div>
                        <div className="font-mono text-sm font-semibold text-accent">{formatBytes(replica.ram)}</div>
                      </div>
                    </div>
                  </div>
                </div>

                {cpuSeries.length > 1 && (
                  <div className="mb-3 h-10">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={cpuSeries}>
                        <YAxis hide domain={[0, 100]} />
                        <Tooltip
                          contentStyle={{
                            background: 'hsl(var(--popover))',
                            border: '1px solid hsl(var(--border))',
                            borderRadius: 4,
                            fontSize: 11,
                            color: 'hsl(var(--popover-foreground))',
                          }}
                          labelStyle={{ display: 'none' }}
                          formatter={(v) => [`${v.toFixed(0)}% CPU`, '']}
                          separator=""
                        />
                        <Line type="monotone" dataKey="cpu" stroke="hsl(var(--info))" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}

                {(replica.domain || linkedJob) && (
                  <div className="mb-3 space-y-1 rounded border border-hairline bg-bg-2/40 p-2 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="shrink-0 text-ink-3">Job:</span>
                      {crawlMode === 'update' && (
                        <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[10px] text-accent">↻ update</span>
                      )}
                      {crawlMode === 'standard' && (
                        <span className="rounded bg-info/15 px-1.5 py-0.5 text-[10px] text-info">▶ standard</span>
                      )}
                    </div>
                    {replica.domain && (
                      <div className="truncate font-mono text-ink-0" title={replica.domain}>{replica.domain}</div>
                    )}
                    {replica.jobId && (
                      <div className="truncate font-mono text-[10px] text-ink-3" title={replica.jobId}>
                        #{String(replica.jobId).slice(0, 12)}
                      </div>
                    )}
                  </div>
                )}

                {replica.topProcesses && replica.topProcesses.length > 0 && (() => {
                  const totalRam = replica.totalRam || (6 * 1024 * 1024 * 1024);
                  const sorted = [...replica.topProcesses].sort((a, b) => (b.ram || 0) - (a.ram || 0)).slice(0, 5);
                  const measured = sorted.reduce((acc, p) => acc + (p.ram || 0), 0);
                  return (
                    <div className="mt-3 border-t border-hairline pt-3">
                      <div className="mb-2 text-[10px] uppercase tracking-wider text-ink-3">
                        Top RAM Processes:
                      </div>
                      <div className="space-y-1.5">
                        {sorted.map((proc, idx) => {
                          const procPct = totalRam > 0 ? Math.min(((proc.ram || 0) / totalRam) * 100, 100) : 0;
                          const isCritical = procPct > 75;
                          const isHigh = procPct > 50;
                          const nameClass = isCritical
                            ? 'text-err font-semibold'
                            : isHigh ? 'text-warn font-semibold' : 'text-ink-0';
                          const barClass = isCritical ? 'bg-err' : isHigh ? 'bg-warn' : 'bg-accent';
                          return (
                            <div key={idx}>
                              <div className="flex justify-between text-xs">
                                <span className={cn('flex-1 truncate font-mono', nameClass)}>
                                  {isCritical ? '⚠ ' : ''}{proc.name}
                                </span>
                                <span className="ml-2 font-mono text-accent">{formatBytes(proc.ram)}</span>
                              </div>
                              <div className="mt-0.5 h-0.5 overflow-hidden rounded-full bg-bg-2">
                                <div className={cn('h-full', barClass)} style={{ width: `${procPct}%` }} />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                      <div className="mt-2 space-y-0.5 text-[10px] text-ink-3">
                        <div>
                          Container: {formatBytes(replica.ram)} / {formatBytes(totalRam)} ({(totalRam > 0 ? Math.min((replica.ram || 0) / totalRam * 100, 100) : 0).toFixed(0)}%)
                        </div>
                        <div className="text-ink-3">
                          Top {sorted.length} process RSS: {formatBytes(measured)}{' '}
                          <span title="La somme des RSS process est souvent supérieure au total container car la mémoire partagée (libs, shared pages) est comptée dans chaque process.">ⓘ</span>
                        </div>
                      </div>
                    </div>
                  );
                })()}
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
};

export default memo(ReplicaMonitor);
