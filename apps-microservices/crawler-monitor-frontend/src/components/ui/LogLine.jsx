const LEVEL_COLORS = {
  debug: 'text-ink-2',
  info:  'text-info',
  warn:  'text-warn',
  err:   'text-err',
};

export default function LogLine({ t, lvl = 'info', msg, meta }) {
  const lvlColor = LEVEL_COLORS[lvl] ?? 'text-ink-2';
  const msgColor = lvl === 'err' ? 'text-err' : 'text-ink-1';

  return (
    <div className="grid grid-cols-[auto_auto_1fr_auto] gap-x-3 items-start py-1 px-3 text-[12px]">
      <span className="font-mono text-ink-3 whitespace-nowrap tabular-nums">{t}</span>
      <span className={`w-[34px] font-mono font-medium uppercase ${lvlColor}`}>
        {lvl}
      </span>
      <span className={msgColor}>{msg}</span>
      {meta != null && (
        <span className="font-mono text-ink-3 text-[11px] whitespace-nowrap overflow-hidden text-ellipsis max-w-[200px]">
          {typeof meta === 'object' ? JSON.stringify(meta) : meta}
        </span>
      )}
    </div>
  );
}
