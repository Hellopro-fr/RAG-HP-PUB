import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
  ReferenceLine, ReferenceArea,
} from 'recharts';
import {
  Play, Pause, SkipBack, SkipForward, RefreshCw,
  AlertTriangle, AlertCircle, Activity, Cpu,
} from 'lucide-react';
import { useJobReplayQuery } from '../hooks/queries';
import { Card } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { cn } from '../lib/utils';

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

function pointAt(points, ts) {
  if (!points || points.length === 0) return null;
  let lo = 0, hi = points.length - 1, best = 0;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (points[mid].ts <= ts) { best = mid; lo = mid + 1; }
    else { hi = mid - 1; }
  }
  return points[best];
}

const EVENT_STYLES = {
  info:     { surface: 'bg-info/10 border-info/30 text-info',               Icon: Activity },
  warn:     { surface: 'bg-warning/10 border-warning/30 text-warning',      Icon: AlertTriangle },
  critical: { surface: 'bg-destructive/10 border-destructive/30 text-destructive', Icon: AlertCircle },
};

const ReplayPage = ({ token }) => {
  const { id } = useParams();
  const navigate = useNavigate();
  const close = useCallback(() => navigate(`/jobs/${id}`), [navigate, id]);

  const query = useJobReplayQuery(token, id);
  const data = query.data;

  const points = data?.points || [];
  const hasPoints = points.length > 1;
  const events = data?.events || [];
  const hotZones = data?.hot_zones || [];
  const totalRamBytes = data?.summary?.total_ram || 0;

  const tsStart = hasPoints ? points[0].ts : 0;
  const tsEnd = hasPoints ? points[points.length - 1].ts : 0;

  const [currentTs, setCurrentTs] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState(2);
  const indexRef = useRef(0);

  useEffect(() => {
    if (hasPoints && currentTs === 0) {
      setCurrentTs(tsStart);
      indexRef.current = 0;
    }
  }, [hasPoints, tsStart, currentTs]);

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

  const onScrub = useCallback((e) => {
    const ts = parseInt(e.target.value, 10);
    if (!Number.isFinite(ts)) return;
    setCurrentTs(ts);
    let idx = 0;
    for (let i = 0; i < points.length; i++) {
      if (points[i].ts <= ts) idx = i;
      else break;
    }
    indexRef.current = idx;
  }, [points]);

  const togglePlay = useCallback(() => {
    if (!hasPoints) return;
    if (indexRef.current >= points.length - 1) {
      indexRef.current = 0;
      setCurrentTs(tsStart);
    }
    setIsPlaying(p => !p);
  }, [hasPoints, points, tsStart]);

  const stepBack = useCallback(() => {
    if (!hasPoints) return;
    setIsPlaying(false);
    indexRef.current = Math.max(0, indexRef.current - 1);
    setCurrentTs(points[indexRef.current].ts);
  }, [hasPoints, points]);

  const stepForward = useCallback(() => {
    if (!hasPoints) return;
    setIsPlaying(false);
    indexRef.current = Math.min(points.length - 1, indexRef.current + 1);
    setCurrentTs(points[indexRef.current].ts);
  }, [hasPoints, points]);

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
  }, [togglePlay, stepBack, stepForward, close]);

  const chartData = useMemo(() => {
    return points.map(p => ({
      ts: p.ts,
      time: fmtTime(p.ts),
      cpu: (p.cpu || 0) * 100,
      ramMb: (p.ram || 0) / 1024 / 1024,
    }));
  }, [points]);

  const currentPoint = useMemo(() => pointAt(points, currentTs), [points, currentTs]);

  const nearbyEvents = useMemo(() => {
    const window = 60_000;
    return events
      .map(ev => ({ ...ev, _delta: Math.abs(ev.ts - currentTs) }))
      .filter(ev => ev._delta <= window)
      .sort((a, b) => a._delta - b._delta)
      .slice(0, 5);
  }, [events, currentTs]);

  const scrubPct = hasPoints && tsEnd > tsStart
    ? ((currentTs - tsStart) / (tsEnd - tsStart)) * 100
    : 0;

  const totalRamMb = totalRamBytes ? totalRamBytes / 1024 / 1024 : 0;
  const maxRamMbData = chartData.length ? Math.max(...chartData.map(d => d.ramMb), 1) : 1;
  const ramDomainMax = Math.max(totalRamMb, maxRamMbData * 1.05);

  const job = data?.job;
  const durationMin = hasPoints ? ((tsEnd - tsStart) / 60000).toFixed(1) : '?';

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border bg-card px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <Activity className="h-5 w-5 shrink-0 text-primary" />
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-foreground">
              Replay · <span className="font-mono">#{id}</span>
              {job?.domain && <span className="font-normal text-muted-foreground"> · {job.domain}</span>}
            </h2>
            <div className="flex flex-wrap gap-3 text-[11px] text-muted-foreground">
              {job?.start_time && <span>Démarré {fmtDate(job.start_time)}</span>}
              {hasPoints && <span>Durée capturée: {durationMin} min</span>}
              {job?.crawl_mode === 'update' && <span className="text-primary">↻ update mode</span>}
              {job?.oom_restart_count > 0 && <span className="text-warning">{job.oom_restart_count} OOM</span>}
            </div>
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3 border-b border-border bg-muted/30 px-4 py-2">
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={jumpStart} disabled={!hasPoints} title="Début">
          <SkipBack className="h-4 w-4" />
        </Button>
        <Button size="icon" className="h-8 w-8" onClick={togglePlay} disabled={!hasPoints} title={isPlaying ? 'Pause (espace)' : 'Lecture (espace)'}>
          {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
        </Button>
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={stepBack} disabled={!hasPoints} title="Précédent (←)">
          <SkipBack className="h-3 w-3" />
        </Button>
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={stepForward} disabled={!hasPoints} title="Suivant (→)">
          <SkipForward className="h-3 w-3" />
        </Button>
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={jumpEnd} disabled={!hasPoints} title="Fin">
          <SkipForward className="h-4 w-4" />
        </Button>
        <div className="ml-2 flex gap-0.5 rounded-md border border-border bg-background p-0.5">
          {SPEED_OPTIONS.map(s => (
            <button
              key={s}
              onClick={() => setSpeed(s)}
              className={cn(
                'rounded px-2 py-0.5 text-xs transition-colors',
                s === speed
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-foreground'
              )}
            >
              {s}×
            </button>
          ))}
        </div>
        <div className="flex min-w-[200px] flex-1 items-center gap-3">
          <input
            type="range"
            min={tsStart}
            max={tsEnd}
            value={currentTs || tsStart}
            onChange={onScrub}
            disabled={!hasPoints}
            className="flex-1 accent-primary"
          />
          <div className="whitespace-nowrap font-mono text-xs text-foreground">
            {fmtTime(currentTs || tsStart)}
            <span className="ml-1 text-muted-foreground">/ {fmtTime(tsEnd)}</span>
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        <div className="flex flex-1 flex-col gap-4 overflow-auto p-4">
          {query.isLoading ? (
            <div className="flex flex-1 items-center justify-center">
              <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : !hasPoints ? (
            <div className="flex flex-1 items-center justify-center text-muted-foreground">
              <div className="text-center">
                <Cpu className="mx-auto mb-3 h-10 w-10 opacity-40" />
                <p className="text-sm">Aucune donnée de performance disponible pour ce job.</p>
                <p className="mt-2 text-xs">Données collectées à partir du déploiement de la feature (rétention 7j).</p>
              </div>
            </div>
          ) : (
            <>
              <Card className="p-3">
                <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
                  <Cpu className="h-3 w-3" /> CPU % et RAM dans le temps (ligne verticale = position du scrubber)
                </div>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData} margin={{ top: 5, right: 8, left: -10, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="time" stroke="hsl(var(--muted-foreground))" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                      <YAxis yAxisId="cpu" domain={[0, 100]} stroke="hsl(var(--info))" tick={{ fontSize: 10 }} tickFormatter={v => `${v}%`} width={45} />
                      <YAxis
                        yAxisId="ram"
                        orientation="right"
                        domain={[0, Math.ceil(ramDomainMax / 100) * 100]}
                        stroke="hsl(var(--primary))"
                        tick={{ fontSize: 10 }}
                        tickFormatter={v => `${v}M`}
                        width={50}
                      />
                      <Tooltip
                        contentStyle={{
                          background: 'hsl(var(--popover))',
                          border: '1px solid hsl(var(--border))',
                          borderRadius: 4,
                          fontSize: 11,
                          color: 'hsl(var(--popover-foreground))',
                        }}
                        formatter={(v, k) => k === 'cpu' ? [`${v.toFixed(1)}%`, 'CPU'] : [`${v.toFixed(0)} MB`, 'RAM']}
                      />
                      {hotZones.map((z, i) => (
                        <ReferenceArea
                          key={`hz-${i}`}
                          yAxisId="cpu"
                          x1={fmtTime(z.from)}
                          x2={fmtTime(z.to)}
                          fill="hsl(var(--destructive))"
                          fillOpacity={0.08}
                        />
                      ))}
                      <ReferenceLine
                        yAxisId="cpu"
                        x={fmtTime(currentTs)}
                        stroke="hsl(var(--foreground))"
                        strokeWidth={2}
                        strokeDasharray="3 3"
                      />
                      <Line yAxisId="cpu" type="monotone" dataKey="cpu"   name="CPU" stroke="hsl(var(--info))"    strokeWidth={1.5} dot={false} isAnimationActive={false} />
                      <Line yAxisId="ram" type="monotone" dataKey="ramMb" name="RAM" stroke="hsl(var(--primary))" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </Card>

              {currentPoint && (
                <Card className="p-4">
                  <div className="mb-2 text-xs text-muted-foreground">À {fmtDate(currentTs)}</div>
                  <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                    <MomentTile label="CPU" value={`${((currentPoint.cpu || 0) * 100).toFixed(1)}%`} valueClass="text-info"
                      sub={`Peak global: ${((data?.summary?.peak_cpu || 0) * 100).toFixed(1)}%`} />
                    <MomentTile label="RAM" value={fmtBytes(currentPoint.ram)} valueClass="text-primary"
                      sub={totalRamBytes ? `/ ${fmtBytes(totalRamBytes)} (${((currentPoint.ram / totalRamBytes) * 100).toFixed(0)}%)` : ''} />
                    <MomentTile label="Replica" value={(currentPoint.replicaId || '—').slice(0, 20)} valueClass="font-mono text-sm truncate" />
                    <div className="rounded-md border border-border bg-background p-3">
                      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Progression</div>
                      <div className="font-mono text-lg font-bold text-foreground">{scrubPct.toFixed(0)}%</div>
                      <div className="mt-1 h-1 overflow-hidden rounded-full bg-muted">
                        <div className="h-full bg-primary" style={{ width: `${scrubPct}%` }} />
                      </div>
                    </div>
                  </div>
                </Card>
              )}
            </>
          )}
        </div>

        {/* Events sidebar */}
        <div className="w-80 overflow-y-auto border-l border-border bg-muted/20">
          <div className="border-b border-border p-3">
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Événements ({events.length})
            </div>
            <div className="mt-0.5 text-[10px] text-muted-foreground/70">
              Mis en surbrillance près du scrubber
            </div>
          </div>
          {events.length === 0 ? (
            <div className="p-4 text-center text-xs text-muted-foreground">
              Aucun événement notable.
            </div>
          ) : (
            <ul className="space-y-1.5 p-2">
              {events.map((ev, i) => {
                const s = EVENT_STYLES[ev.severity] || EVENT_STYLES.info;
                const SIcon = s.Icon;
                const isNear = nearbyEvents.some(n => n.ts === ev.ts && n.kind === ev.kind);
                return (
                  <li
                    key={`${ev.ts}-${ev.kind}-${i}`}
                    onClick={() => { setCurrentTs(ev.ts); indexRef.current = Math.max(0, points.findIndex(p => p.ts >= ev.ts)); setIsPlaying(false); }}
                    className={cn(
                      'cursor-pointer rounded-md border px-2.5 py-2 text-xs transition-all',
                      s.surface,
                      isNear ? 'shadow-sm ring-2 ring-foreground/30' : 'opacity-80 hover:opacity-100'
                    )}
                    title="Cliquer pour sauter ici"
                  >
                    <div className="flex items-center gap-2">
                      <SIcon className="h-3.5 w-3.5 shrink-0" />
                      <span className="font-mono text-[10px] opacity-70">{fmtTime(ev.ts)}</span>
                      <span className="ml-auto text-[9px] uppercase opacity-60">{ev.kind.replace(/_/g, ' ')}</span>
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

const MomentTile = ({ label, value, valueClass = 'text-foreground', sub }) => (
  <div className="rounded-md border border-border bg-background p-3">
    <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
    <div className={cn('font-mono text-2xl font-bold', valueClass)}>{value}</div>
    {sub && <div className="text-[10px] text-muted-foreground">{sub}</div>}
  </div>
);

export default ReplayPage;
