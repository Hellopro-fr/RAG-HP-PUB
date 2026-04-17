import { useState, useMemo, memo } from 'react';
import { useTimelineQuery } from '../hooks/queries';
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Legend, CartesianGrid,
} from 'recharts';
import { Clock, RefreshCw, Calendar } from 'lucide-react';
import { Card } from './ui/card';
import { Input } from './ui/input';
import { cn } from '../lib/utils';

const WINDOW_OPTIONS = ['1h', '6h', '24h', '7d', 'custom'];

const formatBucketLabel = (ts, granMs) => {
  const d = new Date(ts);
  if (granMs >= 6 * 60 * 60 * 1000) {
    return `${d.getDate().toString().padStart(2, '0')}/${(d.getMonth()+1).toString().padStart(2, '0')}`;
  }
  if (granMs >= 60 * 60 * 1000) {
    return `${d.getDate().toString().padStart(2, '0')}/${(d.getMonth()+1).toString().padStart(2, '0')} ${d.getHours().toString().padStart(2, '0')}h`;
  }
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
};

const TooltipBox = ({ active, payload, label }) => {
  if (!active || !payload || payload.length === 0) return null;
  const data = payload[0]?.payload;
  if (!data) return null;
  const total = (data.success || 0) + (data.failure || 0) + (data.running || 0) + (data.other || 0);
  return (
    <div className="rounded border border-border bg-popover p-2 text-xs text-popover-foreground shadow-md">
      <div className="mb-1 font-semibold">{label}</div>
      <div className="text-muted-foreground">Total: {total}</div>
      {data.success > 0 && <div className="text-success">✓ Success: {data.success}</div>}
      {data.failure > 0 && <div className="text-destructive">✗ Failure: {data.failure}</div>}
      {data.running > 0 && <div className="text-info">▶ Running: {data.running}</div>}
      {data.other   > 0 && <div>· Autres: {data.other}</div>}
      {data.oom_events > 0 && <div className="text-warning">⚠ OOM events: {data.oom_events}</div>}
    </div>
  );
};

const todayStr = () => new Date().toISOString().slice(0, 10);
const weekAgoStr = () => new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);

const Timeline = ({ token, onBucketClick }) => {
  const [windowMode, setWindowMode] = useState('6h');
  const [customFrom, setCustomFrom] = useState(weekAgoStr);
  const [customTo, setCustomTo] = useState(todayStr);

  const isCustom = windowMode === 'custom';

  const fromIso = isCustom ? new Date(customFrom + 'T00:00:00').toISOString() : undefined;
  const toIso = isCustom ? new Date(customTo + 'T23:59:59').toISOString() : undefined;

  const query = useTimelineQuery(
    token,
    isCustom ? undefined : windowMode,
    isCustom ? { from: fromIso, to: toIso } : {}
  );
  const data = query.data;

  const chartData = useMemo(() => {
    if (!data?.buckets) return [];
    return data.buckets.map(b => ({
      ...b,
      label: formatBucketLabel(b.ts, data.granularity_ms),
    }));
  }, [data]);

  const handleBarClick = (payload) => {
    if (!payload || !data || !onBucketClick) return;
    const ts = payload.activePayload?.[0]?.payload?.ts;
    if (typeof ts !== 'number') return;
    onBucketClick({ from: ts, to: ts + data.granularity_ms });
  };

  const totalEvents = useMemo(() => {
    if (!chartData.length) return 0;
    return chartData.reduce((acc, b) => acc + (b.success || 0) + (b.failure || 0) + (b.running || 0) + (b.other || 0), 0);
  }, [chartData]);

  return (
    <Card className="p-3">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          <Clock className="h-4 w-4 text-primary" />
          Timeline jobs
          <span className="font-mono text-xs normal-case text-muted-foreground tracking-normal">
            ({totalEvents} démarrés)
          </span>
          {query.isFetching && <RefreshCw className="h-3 w-3 animate-spin text-muted-foreground" />}
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex gap-0.5 rounded-md border border-border bg-muted p-0.5">
            {WINDOW_OPTIONS.map(w => (
              <button
                key={w}
                onClick={() => setWindowMode(w)}
                className={cn(
                  'rounded px-2 py-0.5 text-xs transition-colors',
                  w === windowMode
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                )}
              >
                {w === 'custom' ? <Calendar className="inline h-3 w-3" /> : w}
              </button>
            ))}
          </div>
          {isCustom && (
            <div className="flex items-center gap-1.5">
              <Input
                type="date"
                value={customFrom}
                onChange={e => setCustomFrom(e.target.value)}
                className="h-7 w-[140px] text-xs"
              />
              <span className="text-muted-foreground">→</span>
              <Input
                type="date"
                value={customTo}
                onChange={e => setCustomTo(e.target.value)}
                className="h-7 w-[140px] text-xs"
              />
            </div>
          )}
        </div>
      </div>
      {query.isLoading && !data ? (
        <div className="flex h-32 items-center justify-center">
          <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : query.isError ? (
        <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
          Timeline indisponible
        </div>
      ) : (
        <div className="h-32">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} onClick={handleBarClick} margin={{ top: 5, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
              <XAxis
                dataKey="label"
                stroke="hsl(var(--muted-foreground))"
                tick={{ fontSize: 10 }}
                interval="preserveStartEnd"
              />
              <YAxis
                stroke="hsl(var(--muted-foreground))"
                tick={{ fontSize: 10 }}
                allowDecimals={false}
              />
              <Tooltip content={<TooltipBox />} cursor={{ fill: 'hsl(var(--primary) / 0.08)' }} />
              <Legend wrapperStyle={{ fontSize: 11, paddingTop: 4 }} iconSize={8} />
              <Bar dataKey="success" stackId="jobs" fill="hsl(var(--success))"     name="Succès"   cursor={onBucketClick ? 'pointer' : 'default'} />
              <Bar dataKey="failure" stackId="jobs" fill="hsl(var(--destructive))" name="Échec"    cursor={onBucketClick ? 'pointer' : 'default'} />
              <Bar dataKey="running" stackId="jobs" fill="hsl(var(--info))"        name="En cours" cursor={onBucketClick ? 'pointer' : 'default'} />
              <Bar dataKey="other"   stackId="jobs" fill="hsl(var(--muted-foreground))" name="Autres" cursor={onBucketClick ? 'pointer' : 'default'} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
};

export default memo(Timeline);
