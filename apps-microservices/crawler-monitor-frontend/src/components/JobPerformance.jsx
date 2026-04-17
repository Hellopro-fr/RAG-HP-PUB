import { useMemo } from 'react';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip,
  CartesianGrid, ReferenceDot, Legend,
} from 'recharts';
import { Cpu, RefreshCw } from 'lucide-react';
import { useJobPerformanceQuery } from '../hooks/queries';

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
    <div className="bg-gray-900 border border-gray-700 rounded p-2 text-xs">
      <div className="text-white font-semibold mb-1">{fmtTime(d.ts)}</div>
      <div className="text-cyan-400">CPU: {((d.cpu || 0) * 100).toFixed(1)}%</div>
      <div className="text-pink-400">RAM: {fmtBytes(d.ram)}</div>
    </div>
  );
};

/**
 * Per-job CPU/RAM performance chart.
 * Placed inside JobDetails, below the stat cards.
 * Shows CPU% (left Y axis) and RAM (right Y axis) over time,
 * with markers on peaks.
 */
const JobPerformance = ({ token, jobId, isRunning = true }) => {
  // Stop polling once the job is terminal — perf data won't change anymore.
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
      ramMb: (p.ram || 0) / 1024 / 1024,
    }));
  }, [data]);

  const summary = data?.summary;
  const hasData = chartData.length > 1;

  if (query.isLoading && !data) {
    return (
      <div className="bg-gray-800 rounded-lg p-4">
        <div className="flex items-center justify-center py-8">
          <RefreshCw className="w-5 h-5 animate-spin text-gray-500" />
        </div>
      </div>
    );
  }

  if (!hasData) {
    return (
      <div className="bg-gray-800 rounded-lg p-4">
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <Cpu className="w-4 h-4" />
          Pas encore de données de performance (disponible pendant le crawl).
          {query.isFetching && <RefreshCw className="w-3 h-3 animate-spin" />}
        </div>
      </div>
    );
  }

  const maxRamMb = Math.max(...chartData.map(d => d.ramMb), 1);
  const totalRamMb = summary?.total_ram ? summary.total_ram / 1024 / 1024 : maxRamMb;
  const durationMin = summary?.duration_ms ? (summary.duration_ms / 60000).toFixed(1) : '?';

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
          <Cpu className="w-4 h-4 text-cyan-400" />
          Performance
          {query.isFetching && <RefreshCw className="w-3 h-3 animate-spin text-gray-500" />}
        </h3>
        {summary && (
          <div className="flex gap-4 text-[11px] text-gray-400">
            <span>Durée: {durationMin} min</span>
            <span>Peak CPU: <span className="text-cyan-400 font-semibold">{(summary.peak_cpu * 100).toFixed(1)}%</span> à {fmtTime(summary.peak_cpu_at)}</span>
            <span>Peak RAM: <span className="text-pink-400 font-semibold">{fmtBytes(summary.peak_ram)}</span> à {fmtTime(summary.peak_ram_at)}</span>
            <span>Avg CPU: {(summary.avg_cpu * 100).toFixed(1)}%</span>
          </div>
        )}
      </div>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 5, right: 8, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis
              dataKey="time"
              stroke="#6b7280"
              tick={{ fontSize: 10 }}
              interval="preserveStartEnd"
            />
            <YAxis
              yAxisId="cpu"
              domain={[0, 100]}
              stroke="#06b6d4"
              tick={{ fontSize: 10 }}
              tickFormatter={v => `${v}%`}
              width={45}
            />
            <YAxis
              yAxisId="ram"
              orientation="right"
              domain={[0, Math.ceil(totalRamMb / 100) * 100]}
              stroke="#ec4899"
              tick={{ fontSize: 10 }}
              tickFormatter={v => `${v}M`}
              width={50}
            />
            <Tooltip content={<PerfTooltip />} />
            <Legend wrapperStyle={{ fontSize: 11, paddingTop: 4 }} iconSize={8} />
            <Line
              yAxisId="cpu"
              type="monotone"
              dataKey="cpu"
              name="CPU %"
              stroke="#06b6d4"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              yAxisId="ram"
              type="monotone"
              dataKey="ramMb"
              name="RAM (MB)"
              stroke="#ec4899"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
            {/* Peak CPU marker */}
            {summary?.peak_cpu_at && (() => {
              const idx = chartData.findIndex(d => d.ts === summary.peak_cpu_at);
              if (idx < 0) return null;
              return (
                <ReferenceDot
                  yAxisId="cpu"
                  x={chartData[idx].time}
                  y={chartData[idx].cpu}
                  r={4}
                  fill="#06b6d4"
                  stroke="#fff"
                  strokeWidth={1}
                />
              );
            })()}
            {/* Peak RAM marker */}
            {summary?.peak_ram_at && (() => {
              const idx = chartData.findIndex(d => d.ts === summary.peak_ram_at);
              if (idx < 0) return null;
              return (
                <ReferenceDot
                  yAxisId="ram"
                  x={chartData[idx].time}
                  y={chartData[idx].ramMb}
                  r={4}
                  fill="#ec4899"
                  stroke="#fff"
                  strokeWidth={1}
                />
              );
            })()}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default JobPerformance;