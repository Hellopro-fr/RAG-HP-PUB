import { useMemo } from 'react';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip,
  CartesianGrid, ReferenceDot, Legend,
} from 'recharts';
import { Cpu, RefreshCw } from 'lucide-react';
import { useJobPerformanceQuery } from '../hooks/queries';
import { Card } from './ui/card';

const fmtTime = (ts) => {
  if (!ts) return '';
  const d = new Date(ts);
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`;
};

const fmtBytes = (b) => {
  if (!b) return '0 MB';
  return `${(b / 1024 / 1024).toFixed(0)} MB`;
};

const PerfTooltip = ({ active, payload }) => {
  if (!active || !payload || payload.length === 0) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  return (
    <div className="rounded border border-border bg-popover p-2 text-xs text-popover-foreground shadow-md">
      <div className="mb-1 font-semibold">{fmtTime(d.ts)}</div>
      <div className="text-info">CPU: {((d.cpu || 0) * 100).toFixed(1)}%</div>
      <div className="text-primary">RAM: {fmtBytes(d.ram)}</div>
    </div>
  );
};

const JobPerformance = ({ token, jobId, isRunning = true }) => {
  const query = useJobPerformanceQuery(token, jobId, {
    refetchInterval: isRunning ? 15 * 1000 : false,
  });
  const data = query.data;

  const chartData = useMemo(() => {
    if (!data?.points || data.points.length === 0) return [];
    return data.points.map(p => ({
      ts: p.ts,
      time: fmtTime(p.ts),
      cpu: (p.cpu || 0) * 100,
      ram: p.ram || 0,
      ramMb: (p.ram || 0) / 1024 / 1024,
    }));
  }, [data]);

  const summary = data?.summary;
  const hasData = chartData.length > 1;

  if (query.isLoading && !data) {
    return (
      <Card className="p-4">
        <div className="flex items-center justify-center py-8">
          <RefreshCw className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      </Card>
    );
  }

  if (!hasData) {
    return (
      <Card className="p-4">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Cpu className="h-4 w-4" />
          Pas encore de données de performance (disponible pendant le crawl).
          {query.isFetching && <RefreshCw className="h-3 w-3 animate-spin" />}
        </div>
      </Card>
    );
  }

  const maxRamMb = Math.max(...chartData.map(d => d.ramMb), 1);
  const totalRamMb = summary?.total_ram ? summary.total_ram / 1024 / 1024 : maxRamMb;
  const durationMin = summary?.duration_ms ? (summary.duration_ms / 60000).toFixed(1) : '?';

  return (
    <Card className="p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          <Cpu className="h-4 w-4 text-info" />
          Performance
          {query.isFetching && <RefreshCw className="h-3 w-3 animate-spin text-muted-foreground" />}
        </h3>
        {summary && (
          <div className="flex flex-wrap gap-4 font-mono text-[11px] text-muted-foreground">
            <span>Durée: {durationMin} min</span>
            <span>
              Peak CPU:{' '}
              <span className="font-semibold text-info">{(summary.peak_cpu * 100).toFixed(1)}%</span>
              {' '}à {fmtTime(summary.peak_cpu_at)}
            </span>
            <span>
              Peak RAM:{' '}
              <span className="font-semibold text-primary">{fmtBytes(summary.peak_ram)}</span>
              {' '}à {fmtTime(summary.peak_ram_at)}
            </span>
            <span>Avg CPU: {(summary.avg_cpu * 100).toFixed(1)}%</span>
          </div>
        )}
      </div>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 5, right: 8, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
            <XAxis
              dataKey="time"
              stroke="hsl(var(--muted-foreground))"
              tick={{ fontSize: 10 }}
              interval="preserveStartEnd"
            />
            <YAxis
              yAxisId="cpu"
              domain={[0, 100]}
              stroke="hsl(var(--info))"
              tick={{ fontSize: 10 }}
              tickFormatter={v => `${v}%`}
              width={45}
            />
            <YAxis
              yAxisId="ram"
              orientation="right"
              domain={[0, Math.ceil(totalRamMb / 100) * 100]}
              stroke="hsl(var(--primary))"
              tick={{ fontSize: 10 }}
              tickFormatter={v => `${v}M`}
              width={50}
            />
            <Tooltip content={<PerfTooltip />} />
            <Legend wrapperStyle={{ fontSize: 11, paddingTop: 4 }} iconSize={8} />
            <Line yAxisId="cpu" type="monotone" dataKey="cpu"   name="CPU %"    stroke="hsl(var(--info))"    strokeWidth={1.5} dot={false} isAnimationActive={false} />
            <Line yAxisId="ram" type="monotone" dataKey="ramMb" name="RAM (MB)" stroke="hsl(var(--primary))" strokeWidth={1.5} dot={false} isAnimationActive={false} />
            {summary?.peak_cpu_at && (() => {
              const idx = chartData.findIndex(d => d.ts === summary.peak_cpu_at);
              if (idx < 0) return null;
              return (
                <ReferenceDot
                  yAxisId="cpu"
                  x={chartData[idx].time}
                  y={chartData[idx].cpu}
                  r={4}
                  fill="hsl(var(--info))"
                  stroke="hsl(var(--background))"
                  strokeWidth={1}
                />
              );
            })()}
            {summary?.peak_ram_at && (() => {
              const idx = chartData.findIndex(d => d.ts === summary.peak_ram_at);
              if (idx < 0) return null;
              return (
                <ReferenceDot
                  yAxisId="ram"
                  x={chartData[idx].time}
                  y={chartData[idx].ramMb}
                  r={4}
                  fill="hsl(var(--primary))"
                  stroke="hsl(var(--background))"
                  strokeWidth={1}
                />
              );
            })()}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
};

export default JobPerformance;
