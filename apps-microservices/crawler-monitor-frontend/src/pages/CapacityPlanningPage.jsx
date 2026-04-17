import { useState, useMemo } from 'react';
import {
  SlidersHorizontal, RefreshCw, AlertCircle, TrendingDown, TrendingUp, Server,
} from 'lucide-react';
import { useCapacityPlanningQuery } from '../hooks/queries';

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
  if (pct >= 0.85) return 'text-red-400';      // dangerously high — keep allocation
  if (pct >= 0.70) return 'text-orange-400';   // high — reducing risks OOM
  if (pct >= 0.40) return 'text-yellow-400';   // healthy
  return 'text-green-400';                      // very low — over-provisioned
};

const efficiencyBar = (pct) => {
  if (pct >= 0.85) return 'bg-red-500';
  if (pct >= 0.70) return 'bg-orange-500';
  if (pct >= 0.40) return 'bg-yellow-500';
  return 'bg-green-500';
};

/**
 * Capacity planning — answer "can we reduce RAM per replica?".
 */
const CapacityPlanningPage = ({ token }) => {
  const [windowKey, setWindowKey] = useState('1h');
  const [marginPct, setMarginPct] = useState(30); // safety margin on peak, %
  const query = useCapacityPlanningQuery(token, windowKey);
  const data = query.data;

  const replicas = data?.replicas || [];
  const totals = data?.totals || null;

  // "Target per-replica" = max peak observed across all replicas × (1 + margin)
  // This is the conservative per-replica RAM we'd need to match today's worst replica.
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
    // Assume homogeneous allocation — take the max allocated as the target
    return Math.max(...replicas.map(r => r.allocated || 0)) / GB;
  }, [replicas]);

  // Given same TOTAL RAM, how many replicas could we fit at the target per-replica?
  const totalAllocatedGB = totals ? totals.total_allocated / GB : 0;
  const simulatedReplicaCount = targetPerReplicaGB > 0
    ? Math.floor(totalAllocatedGB / targetPerReplicaGB)
    : 0;

  // Alternative: keep same replica count, what total RAM do we need?
  const simulatedTotalGB = targetPerReplicaGB * (replicas.length || 1);
  const simulatedSavingsGB = totalAllocatedGB - simulatedTotalGB;
  const simulatedSavingsPct = totalAllocatedGB > 0 ? simulatedSavingsGB / totalAllocatedGB : 0;

  // Which replicas are "at risk" if we downsize (peak > 70% of allocated)
  const atRiskReplicas = useMemo(
    () => replicas.filter(r => r.efficiency >= 0.7),
    [replicas]
  );

  return (
    <main className="container mx-auto p-4 space-y-4">
      <div className="bg-gray-800 rounded-lg shadow-xl">
        <div className="flex justify-between items-center p-4 border-b border-gray-700 flex-wrap gap-2">
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <SlidersHorizontal className="w-5 h-5 text-blue-400" />
            Capacity Planning — RAM
          </h2>
          <div className="flex items-center gap-2">
            <div className="flex gap-1 bg-gray-900 p-1 rounded">
              {WINDOW_OPTIONS.map(w => (
                <button
                  key={w.key}
                  onClick={() => setWindowKey(w.key)}
                  className={`px-2.5 py-1 text-xs rounded transition-colors ${
                    w.key === windowKey ? 'bg-blue-600 text-white' : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                  }`}
                  title={w.label}
                >
                  {w.key}
                </button>
              ))}
            </div>
            <button
              onClick={() => query.refetch()}
              disabled={query.isFetching}
              className="p-2 rounded hover:bg-gray-700 disabled:opacity-50"
              title="Rafraîchir"
            >
              <RefreshCw className={`w-4 h-4 ${query.isFetching ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {query.isError && (
          <div className="px-4 py-2 bg-red-900/40 border-b border-red-700/50 text-red-300 text-sm flex items-center gap-2">
            <AlertCircle className="w-4 h-4" /> {query.error?.message || 'Erreur de chargement'}
          </div>
        )}

        {query.isLoading && !data ? (
          <div className="flex items-center justify-center py-20">
            <RefreshCw className="w-8 h-8 animate-spin text-blue-400" />
          </div>
        ) : replicas.length === 0 ? (
          <div className="text-center py-16 text-gray-400">
            <Server className="w-12 h-12 mx-auto mb-3 opacity-40" />
            <p>Aucun sample de replica dans la fenêtre {windowKey}.</p>
            <p className="text-xs mt-1 text-gray-500">Attends quelques heartbeats et réessaie.</p>
          </div>
        ) : (
          <>
            {/* KPI row */}
            <div className="p-4 grid grid-cols-2 md:grid-cols-4 gap-3 border-b border-gray-700">
              <div className="bg-gray-900 p-3 rounded">
                <div className="text-[10px] text-gray-400">Alloué total</div>
                <div className="text-xl font-bold text-white">{fmtBytes(totals.total_allocated)}</div>
                <div className="text-[10px] text-gray-500 mt-0.5">
                  {replicas.length} × {fmtBytes(totals.total_allocated / replicas.length)}
                </div>
              </div>
              <div className="bg-gray-900 p-3 rounded">
                <div className="text-[10px] text-gray-400">Peak réel (pire cas simul.)</div>
                <div className="text-xl font-bold text-cyan-400">{fmtBytes(totals.total_peak_worst)}</div>
                <div className="text-[10px] text-gray-500 mt-0.5">Moyenne: {fmtBytes(totals.total_avg)}</div>
              </div>
              <div className="bg-gray-900 p-3 rounded">
                <div className="text-[10px] text-gray-400">Gaspillage</div>
                <div className="text-xl font-bold text-orange-400">{fmtBytes(totals.waste)}</div>
                <div className="text-[10px] text-gray-500 mt-0.5">{fmtPct(totals.waste_pct)} du total</div>
              </div>
              <div className="bg-gray-900 p-3 rounded">
                <div className="text-[10px] text-gray-400">Efficience globale</div>
                <div className={`text-xl font-bold ${efficiencyColor(totals.efficiency)}`}>
                  {fmtPct(totals.efficiency)}
                </div>
                <div className="text-[10px] text-gray-500 mt-0.5">peak / alloué</div>
              </div>
            </div>

            {/* Per-replica breakdown */}
            <div className="overflow-auto max-h-[45vh]">
              <table className="w-full text-sm">
                <thead className="bg-gray-900 sticky top-0">
                  <tr className="text-left text-gray-400 text-xs uppercase">
                    <th className="px-3 py-2">Replica</th>
                    <th className="px-3 py-2 text-right">Alloué</th>
                    <th className="px-3 py-2 text-right">Peak</th>
                    <th className="px-3 py-2 text-right">Moyenne</th>
                    <th className="px-3 py-2">Efficience</th>
                    <th className="px-3 py-2 text-right">Samples</th>
                    <th className="px-3 py-2">Dernier heartbeat</th>
                  </tr>
                </thead>
                <tbody>
                  {replicas.map(r => (
                    <tr key={r.replicaId} className="border-t border-gray-700 hover:bg-gray-700/30">
                      <td className="px-3 py-2 font-mono text-xs text-white truncate max-w-[200px]" title={r.replicaId}>
                        {r.replicaId.slice(0, 20)}
                      </td>
                      <td className="px-3 py-2 text-right text-gray-300">{fmtBytes(r.allocated)}</td>
                      <td className="px-3 py-2 text-right text-cyan-400">{fmtBytes(r.peak)}</td>
                      <td className="px-3 py-2 text-right text-gray-400">{fmtBytes(r.avg)}</td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden max-w-[120px]">
                            <div className={`h-full ${efficiencyBar(r.efficiency)}`} style={{ width: `${Math.min(r.efficiency * 100, 100)}%` }} />
                          </div>
                          <span className={`text-xs font-semibold ${efficiencyColor(r.efficiency)}`}>
                            {fmtPct(r.efficiency)}
                          </span>
                        </div>
                      </td>
                      <td className="px-3 py-2 text-right text-gray-500 text-xs">{r.sample_count}</td>
                      <td className="px-3 py-2 text-gray-500 text-xs whitespace-nowrap">{fmtDate(r.last_seen)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Simulation */}
            <div className="p-4 border-t border-gray-700 bg-gray-900/40">
              <div className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
                <TrendingDown className="w-4 h-4 text-green-400" />
                Simulation — réduire la RAM par replica
              </div>
              <div className="mb-4">
                <label className="flex items-center gap-3 text-sm text-gray-300">
                  <span className="whitespace-nowrap">Marge de sécurité sur peak :</span>
                  <input
                    type="range"
                    min={10}
                    max={100}
                    step={5}
                    value={marginPct}
                    onChange={e => setMarginPct(Number(e.target.value))}
                    className="flex-1 max-w-md accent-blue-500"
                  />
                  <span className="font-mono text-white w-12 text-right">{marginPct}%</span>
                </label>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="bg-gray-800 p-3 rounded">
                  <div className="text-[10px] text-gray-400 uppercase">Target par replica</div>
                  <div className="text-lg font-bold text-white">
                    {targetPerReplicaGB.toFixed(2)} GB
                  </div>
                  <div className="text-[10px] text-gray-500 mt-0.5">
                    peak global ({fmtBytes(globalPeak)}) × {(1 + marginPct / 100).toFixed(2)}
                  </div>
                  <div className="text-[10px] text-gray-400 mt-1">
                    vs actuel : <span className="text-cyan-400">{currentPerReplicaGB.toFixed(1)} GB</span>
                  </div>
                </div>

                <div className="bg-gray-800 p-3 rounded">
                  <div className="text-[10px] text-gray-400 uppercase">Sur même total RAM</div>
                  <div className="text-lg font-bold text-green-400">
                    {simulatedReplicaCount} replicas
                  </div>
                  <div className="text-[10px] text-gray-500 mt-0.5">
                    vs {replicas.length} actuels ({totalAllocatedGB.toFixed(0)} GB alloués)
                  </div>
                  {simulatedReplicaCount > replicas.length && (
                    <div className="text-[10px] text-green-400 mt-1 flex items-center gap-1">
                      <TrendingUp className="w-3 h-3" /> +{simulatedReplicaCount - replicas.length} replicas possibles
                    </div>
                  )}
                </div>

                <div className="bg-gray-800 p-3 rounded">
                  <div className="text-[10px] text-gray-400 uppercase">Avec même nb replicas</div>
                  <div className="text-lg font-bold text-green-400">
                    {simulatedSavingsGB > 0 ? '-' : '+'}{Math.abs(simulatedSavingsGB).toFixed(1)} GB
                  </div>
                  <div className="text-[10px] text-gray-500 mt-0.5">
                    nouveau total : {simulatedTotalGB.toFixed(1)} GB
                  </div>
                  {simulatedSavingsPct > 0 && (
                    <div className="text-[10px] text-green-400 mt-1 flex items-center gap-1">
                      <TrendingDown className="w-3 h-3" /> {fmtPct(simulatedSavingsPct)} d&apos;économie
                    </div>
                  )}
                </div>
              </div>

              {atRiskReplicas.length > 0 && (
                <div className="mt-4 bg-orange-900/30 border border-orange-500/40 rounded p-3">
                  <div className="text-xs text-orange-300 font-semibold flex items-center gap-2">
                    <AlertCircle className="w-4 h-4" />
                    {atRiskReplicas.length} replica{atRiskReplicas.length > 1 ? 's' : ''} proche{atRiskReplicas.length > 1 ? 's' : ''} de la limite
                  </div>
                  <div className="text-[11px] text-orange-200/80 mt-1">
                    Ces replicas dépassent 70% d&apos;utilisation — à surveiller avant toute réduction :
                  </div>
                  <ul className="text-[11px] text-orange-200 font-mono mt-1 space-y-0.5">
                    {atRiskReplicas.slice(0, 5).map(r => (
                      <li key={r.replicaId}>
                        · {r.replicaId.slice(0, 24)} &rarr; {fmtPct(r.efficiency)} de {fmtBytes(r.allocated)}
                      </li>
                    ))}
                    {atRiskReplicas.length > 5 && (
                      <li className="text-orange-400/70 italic">
                        · … et {atRiskReplicas.length - 5} autre{atRiskReplicas.length - 5 > 1 ? 's' : ''}
                      </li>
                    )}
                  </ul>
                </div>
              )}

              <div className="text-[10px] text-gray-500 mt-3 italic">
                Note : le peak affiché est sur la fenêtre {windowKey}. Pour une décision en prod,
                valide sur 7 jours et valide que la charge observée est représentative
                (saisonnalité, creux vs pics).
              </div>
            </div>
          </>
        )}
      </div>
    </main>
  );
};

export default CapacityPlanningPage;