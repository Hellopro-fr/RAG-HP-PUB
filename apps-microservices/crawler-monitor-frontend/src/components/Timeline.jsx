import { useState, useMemo } from 'react';
import { useTimelineQuery } from '../hooks/queries';
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Legend, CartesianGrid,
} from 'recharts';
import { Clock, RefreshCw } from 'lucide-react';

/**
 * Stacked timeline of jobs by start_time bucket — Overview header strip.
 *
 * Reads from /api/timeline?window=1h|6h|24h|7d (default 6h).
 * Stacks: success (green), failure (red), running (blue).
 * OOM events shown as a small red dot/marker at the top of the bar
 * (separate metric, not stacked since it's a count, not a job count).
 *
 * Click on a bar -> calls onBucketClick({from, to}) so the parent can filter
 * the jobs list. Hover -> tooltip with full breakdown.
 */
const WINDOW_OPTIONS = ['1h', '6h', '24h', '7d'];

const formatBucketLabel = (ts, granMs) => {
  const d = new Date(ts);
  if (granMs >= 60 * 60 * 1000) {
    // hour-bucket: show day/hour
    return `${d.getDate().toString().padStart(2, '0')}/${(d.getMonth()+1).toString().padStart(2, '0')} ${d.getHours().toString().padStart(2, '0')}h`;
  }
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
};

const TooltipBox = ({ active, payload, label }) => {
  if (!active || !payload || payload.length === 0) return null;
  const data = payload[0].payload;
  const total = (data.success || 0) + (data.failure || 0) + (data.running || 0) + (data.other || 0);
  return (
    <div className="bg-gray-900 border border-gray-700 rounded p-2 text-xs">
      <div className="font-semibold text-white mb-1">{label}</div>
      <div className="text-gray-400">Total: {total}</div>
      {data.success > 0 && <div className="text-green-400">✓ Success: {data.success}</div>}
      {data.failure > 0 && <div className="text-red-400">✗ Failure: {data.failure}</div>}
      {data.running > 0 && <div className="text-blue-400">▶ Running: {data.running}</div>}
      {data.other   > 0 && <div className="text-gray-300">· Autres: {data.other}</div>}
      {data.oom_events > 0 && <div className="text-orange-400">⚠ OOM events: {data.oom_events}</div>}
    </div>
  );
};

const Timeline = ({ token, onBucketClick }) => {
  const [window, setWindow] = useState('6h');
  const query = useTimelineQuery(token, window);
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
    return chartData.reduce((acc, b) => acc + b.success + b.failure + b.running + b.other, 0);
  }, [chartData]);

  return (
    <div className="bg-gray-800 rounded-lg p-4 shadow-lg">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
          <Clock className="w-4 h-4 text-blue-400" />
          Timeline jobs <span className="text-gray-500 font-normal">({totalEvents} démarrés)</span>
          {query.isFetching && <RefreshCw className="w-3 h-3 animate-spin text-gray-500" />}
        </h2>
        <div className="flex gap-1 bg-gray-900 p-1 rounded">
          {WINDOW_OPTIONS.map(w => (
            <button
              key={w}
              onClick={() => setWindow(w)}
              className={`px-2 py-0.5 text-xs rounded transition-colors ${
                w === window
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-400 hover:bg-gray-800 hover:text-white'
              }`}
            >
              {w}
            </button>
          ))}
        </div>
      </div>
      {query.isLoading && !data ? (
        <div className="h-32 flex items-center justify-center">
          <RefreshCw className="w-6 h-6 animate-spin text-gray-500" />
        </div>
      ) : query.isError ? (
        <div className="h-32 flex items-center justify-center text-sm text-gray-500">
          Timeline indisponible
        </div>
      ) : (
        <div className="h-32">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} onClick={handleBarClick} margin={{ top: 5, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
              <XAxis
                dataKey="label"
                stroke="#6b7280"
                tick={{ fontSize: 10 }}
                interval="preserveStartEnd"
              />
              <YAxis stroke="#6b7280" tick={{ fontSize: 10 }} allowDecimals={false} />
              <Tooltip content={<TooltipBox />} cursor={{ fill: 'rgba(59, 130, 246, 0.08)' }} />
              <Legend wrapperStyle={{ fontSize: 11, paddingTop: 4 }} iconSize={8} />
              <Bar dataKey="success" stackId="jobs" fill="#22c55e" name="Succès" cursor={onBucketClick ? 'pointer' : 'default'} />
              <Bar dataKey="failure" stackId="jobs" fill="#ef4444" name="Échec"  cursor={onBucketClick ? 'pointer' : 'default'} />
              <Bar dataKey="running" stackId="jobs" fill="#3b82f6" name="En cours" cursor={onBucketClick ? 'pointer' : 'default'} />
              <Bar dataKey="other"   stackId="jobs" fill="#6b7280" name="Autres" cursor={onBucketClick ? 'pointer' : 'default'} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
};

export default Timeline;
