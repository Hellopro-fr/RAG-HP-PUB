import { useMemo, memo } from 'react';
import { ResponsiveContainer, LineChart, Line, YAxis, Tooltip } from 'recharts';
import { AlertTriangle } from 'lucide-react';
import { useCapacityHistoryQuery } from '../hooks/queries';

const SATURATION_THRESHOLD_MS = 5 * 60 * 1000; // 5 minutes

/**
 * Compute the duration (ms) of the latest continuous saturation episode
 * ending "at now". Returns 0 if not currently saturated or no points.
 */
function currentSaturationStreak(points) {
  if (!points || points.length === 0) return 0;
  // points are ordered chronologically
  const last = points[points.length - 1];
  if (!last.full) return 0;
  let start = last.ts;
  for (let i = points.length - 2; i >= 0; i--) {
    if (points[i].full) start = points[i].ts;
    else break;
  }
  return last.ts - start;
}

const CapacityBar = ({ capacity, token }) => {
  const historyQuery = useCapacityHistoryQuery(token, '1h');
  const history = historyQuery.data?.points || [];
  // Hide sparkline silently if endpoint is unavailable (404 or other error)
  const historyAvailable = !historyQuery.isError;

  const saturationMs = useMemo(() => currentSaturationStreak(history), [history]);
  const showSaturationBanner = saturationMs > SATURATION_THRESHOLD_MS;

  if (!capacity || !capacity.max_global_jobs || capacity.max_global_jobs <= 0) return null;

  const pct = (capacity.running_jobs / capacity.max_global_jobs) * 100;
  const fillClass = capacity.is_full
    ? 'bg-red-500'
    : pct > 80 ? 'bg-yellow-500'
      : 'bg-green-500';
  const lineColor = capacity.is_full ? '#ef4444' : '#22c55e';

  return (
    <div className="space-y-2">
      {showSaturationBanner && (
        <div className="bg-orange-900/40 border border-orange-500/40 text-orange-300 text-xs px-3 py-1.5 rounded-lg flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" />
          Capacité saturée depuis {Math.floor(saturationMs / 60000)} min
        </div>
      )}
      <div className="bg-gray-800 rounded-lg p-4 shadow-lg">
        <div className="flex items-center justify-between mb-2 gap-4">
          <div className="flex items-baseline gap-3 flex-1">
            <span className="text-sm font-semibold text-gray-400">Capacité globale</span>
            <span className={`text-sm font-bold ${capacity.is_full ? 'text-red-400' : 'text-green-400'}`}>
              {capacity.running_jobs} / {capacity.max_global_jobs} slots
            </span>
          </div>
          {historyAvailable && history.length > 1 && (
            <div className="w-[150px] h-8 shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={history}>
                  <YAxis hide domain={[0, capacity.max_global_jobs]} />
                  <Tooltip
                    contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 4, fontSize: 11 }}
                    labelStyle={{ display: 'none' }}
                    formatter={(v) => [`${v} running`, '']}
                    separator=""
                  />
                  <Line
                    type="monotone"
                    dataKey="running"
                    stroke={lineColor}
                    strokeWidth={1.5}
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
        <div className="h-3 bg-gray-700 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${fillClass}`}
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
        </div>
      </div>
    </div>
  );
};

export default memo(CapacityBar);