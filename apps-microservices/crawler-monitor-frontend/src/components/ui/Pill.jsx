const TONES = {
  ok:      'bg-ok-soft text-ok border-ok/20',
  warn:    'bg-warn-soft text-warn border-warn/20',
  err:     'bg-err-soft text-err border-err/20',
  accent:  'bg-accent-soft text-accent-ink border-accent/20',
  info:    'bg-info-soft text-info border-info/20',
  neutral: 'bg-bg-2 text-ink-1 border-hairline',
};
const DOT_TONES = {
  ok: 'bg-ok', warn: 'bg-warn', err: 'bg-err',
  accent: 'bg-accent', info: 'bg-info', neutral: 'bg-ink-2',
};

export default function Pill({ tone = 'neutral', dot = false, pulse = false, children, className = '' }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-sm border text-[11px] font-medium ${TONES[tone] ?? TONES.neutral} ${className}`}>
      {dot && (
        <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${DOT_TONES[tone] ?? DOT_TONES.neutral} ${pulse ? 'animate-pulse-dot' : ''}`} />
      )}
      {children}
    </span>
  );
}
