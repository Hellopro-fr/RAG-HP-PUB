import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
  ReferenceLine, ReferenceArea,
} from 'recharts';
import {
  Play, Pause, SkipBack, SkipForward, XCircle, RefreshCw,
  AlertTriangle, AlertCircle, Activity, Cpu,
} from 'lucide-react';
import { useJobReplayQuery } from '../hooks/queries';

const fmtTime = (ts) => {
  if (!ts) return '';
  const d = new Date(ts);
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`;
};

const fmtDate = (ts) => {
  if (!ts) return '';
  return new Date(ts).toLocaleString('fr-FR');
};

const fmtBytes = (b) => {
  if (!b) return '0 MB';
  return `${(b / 1024 / 1024).toFixed(0)} MB`;
};

const SPEED_OPTIONS = [1, 2, 5, 10];

/**
 * Find the perf point closest to (and <=) the given timestamp.
 */
function pointAt(points, ts) {
  if (!points || points.length === 0) return null;
  // Binary search for last index where point.ts <= ts
  let lo = 0, hi = points.length - 1, best = 0;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (points[mid].ts <= ts) { best = mid; lo = mid + 1; }
    else { hi = mid - 1; }
  }
  return points[best];
}

const EVENT_STYLES = {
  info:     { bg: 'bg-blue-500/10',   border: 'border-blue-500/30',   text: 'text-blue-300',   Icon: Activity },
  warn:     { bg: 'bg-orange-500/10', border: 'border-orange-500/30', text: 'text-orange-300', Icon: AlertTriangle },
  critical: { bg: 'bg-red-500/10',    border: 'border-red-500/30',    text: 'text-red-300',    Icon: AlertCircle },
};

const ReplayPage = ({ token }) => {
  const { id } = useParams();
  const navigate = useNavigate();
  const close = () => navigate(`/jobs/${id}`);

  const query = useJobReplayQuery(token, id);
  const data = query.data;

  const points = data?.points || [];
  const hasPoints = points.length > 1;
  const events = data?.events || [];
  const hotZones = data?.hot_zones || [];
  const totalRamBytes = data?.summary?.total_ram || 0;

  // Timeline bounds
  const tsStart = hasPoints ? points[0].ts : 0;
  const tsEnd = hasPoints ? points[points.length - 1].ts : 0;

  // Player state
  const [currentTs, setCurrentTs] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState(2);
  const indexRef = useRef(0);

  // Initialize currentTs when data loads
  useEffect(() => {
    if (hasPoints && currentTs === 0) {
      setCurrentTs(tsStart);
      indexRef.current = 0;
    }
  }, [hasPoints, tsStart, currentTs]);

  // Player tick: advance by 1 data point every (2000/speed) ms
  useEffect(() => {
    if (!isPlaying || !hasPoints) return undefined;
    const tickMs = Math.max(50, 2000 / speed);
    const interval = setInterval(() => {
      indexRef.current = Math.min(indexRef.current + 1, points.length - 1);
      setCurrentTs(points[indexRef.current].ts);
      if (indexRef.current >= points.length - 1) setIsPlaying(false);
    }, tickMs);
    return () => clearInterval(interval);
  }, [isPlaying, speed, hasPoints, points]);

  // Scrubber onChange → update index + currentTs
  const onScrub = useCallback((e) => {
    const ts = parseInt(e.target.value, 10);
    if (!Number.isFinite(ts)) return;
    setCurrentTs(ts);
    // Find nearest index
    let idx = 0;
    for (let i = 0; i < points.length; i++) {
      if (points[i].ts <= ts) idx = i;
      else break;
    }
    indexRef.current = idx;
  }, [points]);

  const togglePlay = () => {
    if (!hasPoints) return;
    // Restart from beginning if at end
    if (indexRef.current >= points.length - 1) {
      indexRef.current = 0;
      setCurrentTs(tsStart);
    }
    setIsPlaying(p => !p);
  };

  const stepBack = () => {
    if (!hasPoints) return;
    setIsPlaying(false);
    indexRef.current = Math.max(0, indexRef.current - 1);
    setCurrentTs(points[indexRef.current].ts);
  };
  const stepForward = () => {
    if (!hasPoints) return;
    setIsPlaying(false);
    indexRef.current = Math.min(points.length - 1, indexRef.current + 1);
    setCurrentTs(points[indexRef.current].ts);
  };
  const jumpStart = () => {
    if (!hasPoints) return;
    setIsPlaying(false);
    indexRef.current = 0;
    setCurrentTs(tsStart);
  };
  const jumpEnd = () => {
    if (!hasPoints) return;
    setIsPlaying(false);
    indexRef.current = points.length - 1;
    setCurrentTs(tsEnd);
  };

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e) => {
      if (e.target.tagName === 'INPUT') return;
      if (e.key === ' ') { e.preventDefault(); togglePlay(); }
      else if (e.key === 'ArrowLeft') stepBack();
      else if (e.key === 'ArrowRight') stepForward();
      else if (e.key === 'Escape') close();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasPoints, points]);

  // Chart data with ramMb derived
  const chartData = useMemo(() => {
    return points.map(p => ({
      ts: p.ts,
      time: fmtTime(p.ts),
      cpu: (p.cpu || 0) * 100,
      ramMb: (p.ram || 0) / 1024 / 1024,
    }));
  }, [points]);

  const currentPoint = useMemo(() => pointAt(points, currentTs), [points, currentTs]);

  // Events in a ±1min window around currentTs
  const nearbyEvents = useMemo(() => {
    const window = 60_000;
    return events
      .map(ev => ({ ...ev, _delta: Math.abs(ev.ts - currentTs) }))
      .filter(ev => ev._delta <= window)
      .sort((a, b) => a._delta - b._delta)
      .slice(0, 5);
  }, [events, currentTs]);

  // Scrubber position as percent
  const scrubPct = hasPoints && tsEnd > tsStart
    ? ((currentTs - tsStart) / (tsEnd - tsStart)) * 100
    : 0;

  const totalRamMb = totalRamBytes ? totalRamBytes / 1024 / 1024 : 0;
  const maxRamMbData = chartData.length ? Math.max(...chartData.map(d => d.ramMb), 1) : 1;
  const ramDomainMax = Math.max(totalRamMb, maxRamMbData * 1.05);

  const job = data?.job;
  const durationMin = hasPoints ? ((tsEnd - tsStart) / 60000).toFixed(1) : '?';

  return (
    <div className="fixed inset-0 bg-gray-900 text-gray-300 z-40 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700 bg-gray-800">
        <div className="flex items-center gap-3 min-w-0">
          <Activity className="w-5 h-5 text-blue-400 shrink-0" />
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-white truncate">
              Replay · Job #{id}
              {job?.domain && <span className="text-gray-400 font-normal"> · {job.domain}</span>}
            </h2>
            <div className="text-[11px] text-gray-500 flex gap-3 flex-wrap">
              {job?.start_time && <span>Démarré {fmtDate(job.start_time)}</span>}
              {hasPoints && <span>Durée capturée: {durationMin} min</span>}
              {job?.crawl_mode === 'update' && <span className="text-purple-400">↻ update mode</span>}
              {job?.oom_restart_count > 0 && <span className="text-orange-400">{job.oom_restart_count} OOM</span>}
            </div>
          </div>
        </div>
        <button onClick={close} className="text-gray-400 hover:text-white p-1 rounded" title="Fermer (Esc)">
          <XCircle className="w-6 h-6" />
        </button>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-gray-700 bg-gray-800/60 flex-wrap">
        <button onClick={jumpStart} disabled={!hasPoints} className="p-1.5 rounded hover:bg-gray-700 disabled:opacity-40" title="Début">
          <SkipBack className="w-4 h-4" />
        </button>
        <button onClick={togglePlay} disabled={!hasPoints} className="p-1.5 rounded bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white" title={isPlaying ? 'Pause (espace)' : 'Lecture (espace)'}>
          {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
        </button>
        <button onClick={stepBack} disabled={!hasPoints} className="p-1.5 rounded hover:bg-gray-700 disabled:opacity-40" title="Précédent (←)">
          <SkipBack className="w-3 h-3" />
        </button>
        <button onClick={stepForward} disabled={!hasPoints} className="p-1.5 rounded hover:bg-gray-700 disabled:opacity-40" title="Suivant (→)">
          <SkipForward className="w-3 h-3" />
        </button>
        <button onClick={jumpEnd} disabled={!hasPoints} className="p-1.5 rounded hover:bg-gray-700 disabled:opacity-40" title="Fin">
          <SkipForward className="w-4 h-4" />
        </button>
        <div className="flex gap-1 ml-2 bg-gray-900 p-0.5 rounded">
          {SPEED_OPTIONS.map(s => (
            <button
              key={s}
              onClick={() => setSpeed(s)}
              className={`px-2 py-0.5 text-xs rounded transition-colors ${
                s === speed ? 'bg-blue-600 text-white' : 'text-gray-400 hover:bg-gray-800 hover:text-white'
              }`}
            >
              {s}×
            </button>
          ))}
        </div>
        <div className="flex-1 min-w-[200px] flex items-center gap-3">
          <input
            type="range"
            min={tsStart}
            max={tsEnd}
            value={currentTs || tsStart}
            onChange={onScrub}
            disabled={!hasPoints}
            className="flex-1 accent-blue-500"
          />
          <div className="text-xs font-mono text-white whitespace-nowrap">
            {fmtTime(currentTs || tsStart)}
            <span className="text-gray-500 ml-1">/ {fmtTime(tsEnd)}</span>
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 flex overflow-hidden">
        {/* Main chart + "at this moment" */}
        <div className="flex-1 flex flex-col p-4 gap-4 overflow-auto">
          {query.isLoading ? (
            <div className="flex items-center justify-center flex-1">
              <RefreshCw className="w-6 h-6 animate-spin text-gray-500" />
            </div>
          ) : !hasPoints ? (
            <div className="flex items-center justify-center flex-1 text-gray-500">
              <div className="text-center">
                <Cpu className="w-12 h-12 mx-auto mb-3 opacity-40" />
                <p>Aucune donnée de performance disponible pour ce job.</p>
                <p className="text-xs mt-2">Données collectées à partir du déploiement de la feature (rétention 7j).</p>
              </div>
            </div>
          ) : (
            <>
              <div className="bg-gray-800 rounded-lg p-3">
                <div className="text-xs text-gray-400 mb-2 flex items-center gap-2">
                  <Cpu className="w-3 h-3" /> CPU % et RAM dans le temps (ligne verticale = position du scrubber)
                </div>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData} margin={{ top: 5, right: 8, left: -10, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                      <XAxis dataKey="time" stroke="#6b7280" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                      <YAxis yAxisId="cpu" domain={[0, 100]} stroke="#06b6d4" tick={{ fontSize: 10 }} tickFormatter={v => `${v}%`} width={45} />
                      <YAxis yAxisId="ram" orientation="right" domain={[0, Math.ceil(ramDomainMax / 100) * 100]} stroke="#ec4899" tick={{ fontSize: 10 }} tickFormatter={v => `${v}M`} width={50} />
                      <Tooltip
                        contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 4, fontSize: 11 }}
                        formatter={(v, k) => k === 'cpu' ? [`${v.toFixed(1)}%`, 'CPU'] : [`${v.toFixed(0)} MB`, 'RAM']}
                      />
                      {/* Hot CPU zones (shaded background) */}
                      {hotZones.map((z, i) => (
                        <ReferenceArea
                          key={`hz-${i}`}
                          yAxisId="cpu"
                          x1={fmtTime(z.from)}
                          x2={fmtTime(z.to)}
                          fill="#ef4444"
                          fillOpacity={0.07}
                        />
                      ))}
                      {/* Scrubber position */}
                      <ReferenceLine
                        yAxisId="cpu"
                        x={fmtTime(currentTs)}
                        stroke="#fff"
                        strokeWidth={2}
                        strokeDasharray="3 3"
                      />
                      <Line yAxisId="cpu" type="monotone" dataKey="cpu"   name="CPU" stroke="#06b6d4" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                      <Line yAxisId="ram" type="monotone" dataKey="ramMb" name="RAM" stroke="#ec4899" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* At this moment */}
              {currentPoint && (
                <div className="bg-gray-800 rounded-lg p-4">
                  <div className="text-xs text-gray-400 mb-2">À {fmtDate(currentTs)}</div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div className="bg-gray-900 p-3 rounded">
                      <div className="text-[10px] text-gray-400">CPU</div>
                      <div className="text-2xl font-bold text-cyan-400">{((currentPoint.cpu || 0) * 100).toFixed(1)}%</div>
                      <div className="text-[10px] text-gray-500">Peak global: {((data?.summary?.peak_cpu || 0) * 100).toFixed(1)}%</div>
                    </div>
                    <div className="bg-gray-900 p-3 rounded">
                      <div className="text-[10px] text-gray-400">RAM</div>
                      <div className="text-2xl font-bold text-pink-400">{fmtBytes(currentPoint.ram)}</div>
                      <div className="text-[10px] text-gray-500">
                        {totalRamBytes ? `/ ${fmtBytes(totalRamBytes)} (${((currentPoint.ram / totalRamBytes) * 100).toFixed(0)}%)` : ''}
                      </div>
                    </div>
                    <div className="bg-gray-900 p-3 rounded">
                      <div className="text-[10px] text-gray-400">Replica</div>
                      <div className="text-sm font-mono text-white truncate">{(currentPoint.replicaId || '—').slice(0, 20)}</div>
                    </div>
                    <div className="bg-gray-900 p-3 rounded">
                      <div className="text-[10px] text-gray-400">Progression</div>
                      <div className="text-lg font-bold text-white">{scrubPct.toFixed(0)}%</div>
                      <div className="h-1 mt-1 bg-gray-700 rounded-full overflow-hidden">
                        <div className="h-full bg-blue-500" style={{ width: `${scrubPct}%` }} />
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Events sidebar */}
        <div className="w-80 border-l border-gray-700 bg-gray-800/40 overflow-y-auto">
          <div className="p-3 border-b border-gray-700">
            <div className="text-xs font-semibold text-gray-300">Événements ({events.length})</div>
            <div className="text-[10px] text-gray-500 mt-0.5">Mis en surbrillance près du scrubber</div>
          </div>
          {events.length === 0 ? (
            <div className="p-4 text-xs text-gray-500 text-center">Aucun événement notable.</div>
          ) : (
            <ul className="p-2 space-y-1.5">
              {events.map((ev, i) => {
                const s = EVENT_STYLES[ev.severity] || EVENT_STYLES.info;
                const SIcon = s.Icon;
                const isNear = nearbyEvents.some(n => n.ts === ev.ts && n.kind === ev.kind);
                return (
                  <li
                    key={`${ev.ts}-${ev.kind}-${i}`}
                    onClick={() => { setCurrentTs(ev.ts); indexRef.current = Math.max(0, points.findIndex(p => p.ts >= ev.ts)); setIsPlaying(false); }}
                    className={`cursor-pointer px-2.5 py-2 rounded border text-xs transition-all ${s.bg} ${s.border} ${s.text} ${isNear ? 'ring-2 ring-white/50 shadow-lg' : 'opacity-80 hover:opacity-100'}`}
                    title="Cliquer pour sauter ici"
                  >
                    <div className="flex items-center gap-2">
                      <SIcon className="w-3.5 h-3.5 shrink-0" />
                      <span className="font-mono text-[10px] text-gray-400">{fmtTime(ev.ts)}</span>
                      <span className="uppercase text-[9px] opacity-60 ml-auto">{ev.kind.replace(/_/g, ' ')}</span>
                    </div>
                    <div className="mt-1 leading-tight">{ev.label}</div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
};

export default ReplayPage;