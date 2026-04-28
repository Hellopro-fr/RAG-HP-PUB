import { useMemo, memo } from 'react';
import { ResponsiveContainer, LineChart, Line, YAxis, Tooltip } from 'recharts';
import { AlertTriangle } from 'lucide-react';
import { useCapacityHistoryQuery } from '../hooks/queries';
import { Card } from './ui/card';
import { cn } from '../lib/utils';
import { CoherencePastille } from '../coherence/components/CoherencePastille';

const SATURATION_THRESHOLD_MS = 5 * 60 * 1000; // 5 minutes

/**
 * Compute the duration (ms) of the latest continuous saturation episode
 * ending "at now". Returns 0 if not currently saturated or no points.
 */
function currentSaturationStreak(points) {
  if (!points || points.length === 0) return 0;
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
  const historyAvailable = !historyQuery.isError;

  const saturationMs = useMemo(() => currentSaturationStreak(history), [history]);
  const showSaturationBanner = saturationMs > SATURATION_THRESHOLD_MS;

  if (!capacity || !capacity.max_global_jobs || capacity.max_global_jobs <= 0) return null;

  const pct = (capacity.running_jobs / capacity.max_global_jobs) * 100;
  const fillClass = capacity.is_full
    ? 'bg-destructive'
    : pct > 80 ? 'bg-warning'
      : 'bg-success';
  // Recharts strokes need raw color values — read the CSS var via computed style.
  const lineColor = capacity.is_full ? 'hsl(var(--destructive))' : 'hsl(var(--success))';

  return (
    <div className="space-y-2">
      {showSaturationBanner && (
        <div className="flex items-center gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-1.5 text-xs text-warning">
          <AlertTriangle className="h-4 w-4" />
          <span>Capacité saturée depuis {Math.floor(saturationMs / 60000)} min</span>
        </div>
      )}
      <Card className="p-3">
        <div className="mb-2 flex items-center justify-between gap-4">
          <div className="flex flex-1 items-baseline gap-3">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Capacité globale
            </span>
            <span className={cn('flex items-center gap-1.5 font-mono text-sm font-bold', capacity.is_full ? 'text-destructive' : 'text-success')}>
              {capacity.running_jobs} / {capacity.max_global_jobs} slots
              <CoherencePastille ruleId="replicas_vs_max_slots" />
            </span>
          </div>
          {historyAvailable && history.length > 1 && (
            <div className="h-8 w-[150px] shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={history}>
                  <YAxis hide domain={[0, capacity.max_global_jobs]} />
                  <Tooltip
                    contentStyle={{
                      background: 'hsl(var(--popover))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: 4,
                      fontSize: 11,
                      color: 'hsl(var(--popover-foreground))',
                    }}
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
        <div className="h-2 overflow-hidden rounded-full bg-muted">
          <div
            className={cn('h-full rounded-full transition-all duration-500', fillClass)}
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
        </div>
      </Card>
    </div>
  );
};

export default memo(CapacityBar);
