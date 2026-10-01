import { useId } from 'react';

const PAD = { top: 12, right: 12, bottom: 28, left: 36 };

function getValues(data, valueKey) {
  if (!data || !data.length) return [];
  return data.map(item =>
    typeof item === 'number' ? item : (item[valueKey] ?? 0)
  );
}

export default function AreaChart({
  data = [],
  w = 400,
  h = 120,
  color = 'var(--accent)',
  valueKey = 'value',
  refLine,
}) {
  const chartW = w - PAD.left - PAD.right;
  const chartH = h - PAD.top - PAD.bottom;

  const values = getValues(data, valueKey);
  const hasData = values.length > 0;

  const min = hasData ? Math.min(...values) : 0;
  const max = hasData ? Math.max(...values) : 1;
  const range = max - min || 1;

  const toX = i => PAD.left + (values.length > 1 ? (i / (values.length - 1)) * chartW : chartW / 2);
  const toY = v => PAD.top + chartH - ((v - min) / range) * chartH;

  const pts = values.map((v, i) => `${toX(i)},${toY(v)}`);
  const polyline = pts.join(' ');

  // Area path: start from first point, go through all, down to bottom-right, bottom-left, close
  const areaPath = hasData
    ? `M ${pts[0]} ${pts.slice(1).map(p => `L ${p}`).join(' ')} L ${toX(values.length - 1)},${PAD.top + chartH} L ${toX(0)},${PAD.top + chartH} Z`
    : '';

  // Y-axis ticks (4 ticks)
  const tickCount = 4;
  const divisor = tickCount > 1 ? tickCount - 1 : 1;
  const yTicks = Array.from({ length: tickCount }, (_, i) => {
    const val = min + (range / divisor) * i;
    const y = toY(val);
    return { val, y };
  });

  const uid = useId().replace(/:/g, '');
  const gradId = `ac-grad-${uid}`;

  // refLine Y position
  const refY = refLine != null ? toY(refLine) : null;

  return (
    <svg width={w} height={h} className="overflow-visible">
      <defs>
        <linearGradient id={gradId} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.15} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>

      {/* Y axis */}
      <line
        x1={PAD.left} y1={PAD.top}
        x2={PAD.left} y2={PAD.top + chartH}
        stroke="var(--hairline-strong)" strokeWidth={1}
      />
      {/* X axis */}
      <line
        x1={PAD.left} y1={PAD.top + chartH}
        x2={PAD.left + chartW} y2={PAD.top + chartH}
        stroke="var(--hairline-strong)" strokeWidth={1}
      />

      {/* Y axis ticks */}
      {yTicks.map(({ val, y }, i) => (
        <text
          key={i}
          x={PAD.left - 4}
          y={y + 3}
          textAnchor="end"
          className="font-mono text-[10px] fill-current text-ink-3"
        >
          {Number.isInteger(val) ? val : val.toFixed(1)}
        </text>
      ))}

      {/* Area fill */}
      {hasData && (
        <path d={areaPath} fill={`url(#${gradId})`} />
      )}

      {/* Polyline */}
      {hasData && (
        <polyline
          points={polyline}
          fill="none"
          stroke={color}
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      )}

      {/* Reference line */}
      {refY != null && (
        <line
          x1={PAD.left}
          y1={refY}
          x2={PAD.left + chartW}
          y2={refY}
          stroke="var(--err)"
          strokeDasharray="4 3"
          strokeWidth={1}
        />
      )}
    </svg>
  );
}
