const SIZE = 160;
const STROKE = 10;
const R = (SIZE - STROKE) / 2;
const CIRC = 2 * Math.PI * R;

export default function CapacityRing({ used = 0, total = 1, label = 'Utilisé' }) {
  const pct = Math.min(1, used / total);
  const offset = CIRC * (1 - pct);
  const tone = pct > 0.9 ? 'var(--err)' : pct > 0.7 ? 'var(--warn)' : 'var(--ok)';
  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width={SIZE} height={SIZE} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={SIZE / 2} cy={SIZE / 2} r={R} fill="none" stroke="var(--hairline-strong)" strokeWidth={STROKE} />
        <circle
          cx={SIZE / 2} cy={SIZE / 2} r={R}
          fill="none" stroke={tone} strokeWidth={STROKE}
          strokeDasharray={CIRC} strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 0.6s ease' }}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="font-display text-[28px] font-semibold tabular-nums text-ink-0 leading-none">
          {Math.round(pct * 100)}%
        </span>
        <span className="text-[11px] text-ink-2 mt-1">{label}</span>
      </div>
    </div>
  );
}
