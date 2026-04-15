import { useMemo } from 'react';
import { Server, Cpu } from 'lucide-react';
import { ResponsiveContainer, LineChart, Line, YAxis, Tooltip } from 'recharts';
import { useJobsQuery, useReplicasHistoryQuery } from '../hooks/queries';

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

  // jobId -> job map for fast cross-reference (Mode badge needs job.crawl_mode)
  const jobsById = useMemo(() => {
    const m = new Map();
    for (const j of allJobs) if (j.id) m.set(j.id, j);
    return m;
  }, [allJobs]);

  const formatBytes = (bytes) => {
    if (!bytes) return '0 MB';
    const mb = bytes / 1024 / 1024;
    return `${mb.toFixed(0)} MB`;
  };

  const formatCpu = (load) => {
    if (!load) return '0%';
    return `${(load * 100).toFixed(1)}%`;
  };

  const getStatusColor = (timestamp) => {
    const age = Date.now() - timestamp;
    if (age < 5000) return 'green';
    if (age < 15000) return 'yellow';
    return 'red';
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
      <svg width={size} height={size} className="transform -rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius - 18} fill="none" stroke="#374151" strokeWidth={strokeWidth} />
        <circle cx={size / 2} cy={size / 2} r={radius}      fill="none" stroke="#374151" strokeWidth={strokeWidth} />
        <circle cx={size / 2} cy={size / 2} r={radius - 18} fill="none" stroke="url(#cpuGradient)" strokeWidth={strokeWidth}
          strokeDasharray={circumference} strokeDashoffset={cpuOffset} strokeLinecap="round" className="transition-all duration-500" />
        <circle cx={size / 2} cy={size / 2} r={radius}      fill="none" stroke="url(#ramGradient)" strokeWidth={strokeWidth}
          strokeDasharray={circumference} strokeDashoffset={ramOffset} strokeLinecap="round" className="transition-all duration-500" />
        <defs>
          <linearGradient id="cpuGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#3b82f6" />
            <stop offset="100%" stopColor="#06b6d4" />
          </linearGradient>
          <linearGradient id="ramGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#a855f7" />
            <stop offset="100%" stopColor="#ec4899" />
          </linearGradient>
        </defs>
      </svg>
    );
  };

  // Defensive: drop replicas without a replicaId (partial heartbeats) so we never
  // crash when calling .substring/.slice on undefined later in the render.
  const activeReplicas = Object.values(replicas).filter(
    r => r && r.replicaId && Date.now() - (r.timestamp || 0) < 30000
  );

  return (
    <div className="bg-gray-800 rounded-lg p-6 shadow-xl">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <Server className="w-6 h-6 text-blue-400" />
          Crawler Replicas
          <span className="text-sm font-normal text-gray-400 ml-2">
            ({activeReplicas.length} active)
          </span>
        </h2>
      </div>

      {activeReplicas.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <Server className="w-16 h-16 mx-auto mb-4 opacity-30" />
          <p>Aucun replica actif</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {activeReplicas.map((replica) => {
            const statusColor = getStatusColor(replica.timestamp);
            const linkedJob = replica.jobId ? jobsById.get(replica.jobId) : null;
            const crawlMode = linkedJob?.crawl_mode;
            const history = historyByReplica[replica.replicaId] || [];
            // Map history to sparkline points {ts, cpuPct}
            const cpuSeries = history.map(p => ({ ts: p.ts, cpu: (p.cpu || 0) * 100 }));

            return (
              <div
                key={replica.replicaId}
                className="bg-gray-900 rounded-lg p-5 border border-gray-700 hover:border-gray-600 transition-all"
              >
                {/* Header */}
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <div className={`w-3 h-3 rounded-full shrink-0 ${statusColor === 'green' ? 'bg-green-500 animate-pulse' :
                      statusColor === 'yellow' ? 'bg-yellow-500' : 'bg-red-500'
                      }`} />
                    <span className="text-white font-semibold text-sm truncate">
                      {String(replica.replicaId || '').substring(0, 12)}
                    </span>
                  </div>
                  <Cpu className="w-4 h-4 text-blue-400 shrink-0" />
                </div>

                {/* Circular Progress */}
                <div className="flex flex-col items-center mb-4">
                  <div className="relative">
                    <CircularProgress cpu={replica.cpu} ram={replica.ram} totalRam={replica.totalRam} />
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                      <div className="text-center">
                        <div className="text-xs text-gray-400">CPU</div>
                        <div className="text-lg font-bold text-cyan-400">{formatCpu(replica.cpu)}</div>
                        <div className="text-xs text-gray-400 mt-1">RAM</div>
                        <div className="text-sm font-semibold text-pink-400">{formatBytes(replica.ram)}</div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* CPU sparkline (1h history) */}
                {cpuSeries.length > 1 && (
                  <div className="mb-3 h-10">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={cpuSeries}>
                        <YAxis hide domain={[0, 100]} />
                        <Tooltip
                          contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 4, fontSize: 11 }}
                          labelStyle={{ display: 'none' }}
                          formatter={(v) => [`${v.toFixed(0)}% CPU`, '']}
                          separator=""
                        />
                        <Line type="monotone" dataKey="cpu" stroke="#06b6d4" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}

                {/* Job + Mode info */}
                {(replica.domain || linkedJob) && (
                  <div className="mb-3 p-2 bg-gray-800 rounded text-xs space-y-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-gray-400 shrink-0">Job:</span>
                      {crawlMode === 'update' && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-400">↻ update</span>
                      )}
                      {crawlMode === 'standard' && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-400">▶ standard</span>
                      )}
                    </div>
                    {replica.domain && (
                      <div className="text-white font-mono truncate" title={replica.domain}>{replica.domain}</div>
                    )}
                    {replica.jobId && (
                      <div className="text-gray-500 font-mono text-[10px] truncate" title={replica.jobId}>
                        #{String(replica.jobId).slice(0, 12)}
                      </div>
                    )}
                  </div>
                )}

                {/* Top Processes (sorted desc by RAM, top 5, with proportion bars) */}
                {replica.topProcesses && replica.topProcesses.length > 0 && (() => {
                  const totalRam = replica.totalRam || (6 * 1024 * 1024 * 1024);
                  const sorted = [...replica.topProcesses].sort((a, b) => (b.ram || 0) - (a.ram || 0)).slice(0, 5);
                  const measured = sorted.reduce((acc, p) => acc + (p.ram || 0), 0);
                  const measuredPct = totalRam > 0 ? Math.min((measured / totalRam) * 100, 100) : 0;
                  return (
                    <div className="mt-3 pt-3 border-t border-gray-700">
                      <div className="text-xs text-gray-400 mb-2">Top RAM Processes:</div>
                      <div className="space-y-1.5">
                        {sorted.map((proc, idx) => {
                          const procPct = totalRam > 0 ? Math.min(((proc.ram || 0) / totalRam) * 100, 100) : 0;
                          const isCritical = procPct > 75;
                          const isHigh = procPct > 50;
                          const nameClass = isCritical ? 'text-red-400 font-semibold'
                            : isHigh ? 'text-orange-400 font-semibold' : 'text-gray-300';
                          const barClass = isCritical ? 'bg-red-500' : isHigh ? 'bg-orange-500' : 'bg-purple-500';
                          return (
                            <div key={idx}>
                              <div className="flex justify-between text-xs">
                                <span className={`truncate flex-1 font-mono ${nameClass}`}>
                                  {isCritical ? '⚠ ' : ''}{proc.name}
                                </span>
                                <span className="text-purple-400 ml-2">{formatBytes(proc.ram)}</span>
                              </div>
                              <div className="h-0.5 mt-0.5 bg-gray-700 rounded-full overflow-hidden">
                                <div className={`h-full ${barClass}`} style={{ width: `${procPct}%` }} />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                      <div className="text-[10px] text-gray-500 mt-2">
                        Total mesuré: {formatBytes(measured)} / {formatBytes(totalRam)} ({measuredPct.toFixed(0)}%)
                      </div>
                    </div>
                  );
                })()}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default ReplicaMonitor;
