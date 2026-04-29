import Sparkline from './Sparkline';

export default function StatTile({ label, value, delta, deltaTone, spark, sub, accent }) {
  const isLoading = value == null;
  return (
    <div className="bg-surface rounded-lg p-5 shadow-sm border border-hairline flex flex-col gap-3 min-w-0">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-2">{label}</span>
        {spark && !isLoading && <Sparkline data={spark} />}
      </div>
      {isLoading ? (
        <div className="h-7 w-24 rounded animate-shimmer" />
      ) : (
        <span className="font-display text-[28px] font-semibold tabular-nums tracking-tight text-ink-0 leading-none">
          {value}
        </span>
      )}
      <div className="flex items-center gap-2 min-h-[16px]">
        {delta != null && !isLoading && (
          <span className={`text-[11px] font-medium tabular-nums ${
            deltaTone === 'ok' ? 'text-ok' : deltaTone === 'err' ? 'text-err' : 'text-ink-2'
          }`}>
            {delta}
          </span>
        )}
        {sub && !isLoading && <span className="text-[11px] text-ink-2">{sub}</span>}
      </div>
      {accent != null && (
        <div className="h-0.5 w-full bg-hairline rounded-full overflow-hidden">
          <div className="h-full bg-accent rounded-full" style={{ width: `${Math.min(100, accent)}%` }} />
        </div>
      )}
    </div>
  );
}
