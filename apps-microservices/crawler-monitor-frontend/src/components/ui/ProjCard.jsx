const TONE_STYLES = {
  accent: {
    border: 'border-accent/25',
    bg: 'bg-accent-soft',
    value: 'text-accent-ink',
    label: 'text-ink-2',
  },
  ok: {
    border: 'border-ok/25',
    bg: 'bg-ok-soft',
    value: 'text-ok',
    label: 'text-ink-2',
  },
  warn: {
    border: 'border-warn/25',
    bg: 'bg-warn-soft',
    value: 'text-warn',
    label: 'text-ink-2',
  },
};

export default function ProjCard({ label, value, sub, tone = 'accent' }) {
  const t = TONE_STYLES[tone] ?? TONE_STYLES.accent;
  return (
    <div className={`rounded-lg border ${t.border} ${t.bg} px-5 py-4`}>
      <div className={`text-[11px] font-semibold uppercase tracking-[0.06em] mb-2 ${t.label}`}>{label}</div>
      <div className={`text-[22px] font-semibold tracking-[-0.025em] tabular-nums font-display ${t.value}`}>
        {value ?? '—'}
      </div>
      {sub && <div className="mt-1 text-[11px] text-ink-3">{sub}</div>}
    </div>
  );
}
