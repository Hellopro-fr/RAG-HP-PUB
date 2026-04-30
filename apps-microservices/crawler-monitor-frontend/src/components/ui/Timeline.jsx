import { useIsMobile } from '../../hooks/useIsMobile';

const BAR_H = 40;

// data: [{ label: '00h', ok: number, run: number, fail: number }, ...]
export default function Timeline({ data = [] }) {
  const isMobile = useIsMobile();
  // Sur mobile, limiter aux 30 dernières barres pour éviter l'écrasement visuel.
  const displayData = isMobile ? data.slice(-30) : data;
  if (!displayData.length) return <div className="h-10 bg-bg-2 rounded animate-shimmer" />;
  const maxTotal = Math.max(...displayData.map(d => (d.ok || 0) + (d.run || 0) + (d.fail || 0)), 1);
  return (
    <div className="flex items-end gap-0.5 h-[48px]">
      {displayData.map((d, i) => {
        const total = (d.ok || 0) + (d.run || 0) + (d.fail || 0);
        if (!total) return <div key={i} className="flex-1 h-1 bg-hairline rounded-sm" />;
        const height = Math.round((total / maxTotal) * BAR_H);
        const okH   = Math.round((d.ok  / total) * height);
        const runH  = Math.round((d.run / total) * height);
        const failH = Math.max(0, height - okH - runH);
        return (
          <div key={i} className="flex-1 flex flex-col-reverse rounded-sm overflow-hidden" style={{ height }}>
            {d.fail > 0 && <div style={{ height: failH }} className="bg-err" />}
            {d.run  > 0 && <div style={{ height: runH  }} className="bg-warn" />}
            {d.ok   > 0 && <div style={{ height: okH   }} className="bg-ok" />}
          </div>
        );
      })}
    </div>
  );
}
