import { isValidElement } from 'react';
import Sparkline from './Sparkline';

export default function StatTile({ label, value, delta, deltaTone, spark, sub, accent }) {
  const isLoading = value == null;

  // spark: JSX element (spec) or array (legacy fallback)
  let sparkNode = null;
  if (spark != null) {
    if (isValidElement(spark)) {
      sparkNode = spark;
    } else if (Array.isArray(spark) && spark.length > 0) {
      // legacy callers — wrap in Sparkline internally
      sparkNode = <Sparkline data={spark} />;
    }
  }

  return (
    <div className="bg-surface rounded-lg p-5 shadow-sm border border-hairline flex flex-col gap-3 min-w-0 relative overflow-hidden">
      {/* accent — full-width 2px top stripe (CSS color string) */}
      {accent && (
        <div
          className="absolute top-0 left-0 right-0 h-[2px]"
          style={{ background: accent }}
        />
      )}

      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-2">{label}</span>
        {delta != null && !isLoading && (
          <span className={`text-[11px] font-medium tabular-nums font-mono ${
            deltaTone === 'ok' ? 'text-ok' : deltaTone === 'warn' ? 'text-warn' : deltaTone === 'err' ? 'text-err' : 'text-ink-2'
          }`}>
            {delta}
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="h-7 w-24 rounded animate-shimmer" />
      ) : (
        <div className="flex items-baseline gap-2">
          <span className="font-display text-[28px] font-semibold tabular-nums tracking-tight text-ink-0 leading-none">
            {value}
          </span>
          {sub && <span className="text-[11px] text-ink-2 font-mono">{sub}</span>}
        </div>
      )}

      {sparkNode && !isLoading && (
        <div className="mt-auto">{sparkNode}</div>
      )}
    </div>
  );
}
