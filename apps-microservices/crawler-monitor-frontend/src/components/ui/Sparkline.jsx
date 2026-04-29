export default function Sparkline({ data = [], w = 64, h = 24, color = 'var(--accent)', fill = true }) {
  if (!data.length) {
    return (
      <svg width={w} height={h}>
        <line x1={0} y1={h / 2} x2={w} y2={h / 2} stroke="var(--hairline)" strokeWidth={1} />
      </svg>
    );
  }
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => {
    const x = data.length > 1 ? (i / (data.length - 1)) * w : w / 2;
    const y = h - ((v - min) / range) * (h - 4) - 2;
    return `${x},${y}`;
  });
  const polyline = pts.join(' ');
  const first = pts[0].split(',')[0];
  const last = pts[pts.length - 1].split(',')[0];
  const area = `${first},${h} ${polyline} ${last},${h}`;
  const gradId = `sg-${color.replace(/[^a-z0-9]/gi, '')}`;
  return (
    <svg width={w} height={h} className="overflow-visible">
      {fill && (
        <defs>
          <linearGradient id={gradId} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.15} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
      )}
      {fill && <polygon points={area} fill={`url(#${gradId})`} />}
      <polyline points={polyline} fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
