const TONE_COLORS = {
  ok:      'text-ok',
  warn:    'text-warn',
  err:     'text-err',
  info:    'text-info',
  neutral: 'text-ink-0',
};

export default function KV({ k, v, mono = false, tone = 'neutral' }) {
  const toneClass = TONE_COLORS[tone] ?? TONE_COLORS.neutral;
  const isNullish = v == null;

  return (
    <div className="flex items-baseline justify-between gap-4 py-2 border-b border-hairline last:border-b-0">
      <span className="text-[12px] text-ink-2 font-medium flex-shrink-0">{k}</span>
      {isNullish ? (
        <span className="text-[12px] font-medium tabular-nums text-right text-ink-3">—</span>
      ) : (
        <span className={`text-[12px] font-medium tabular-nums text-right ${toneClass}${mono ? ' font-mono' : ''}`}>
          {String(v)}
        </span>
      )}
    </div>
  );
}
