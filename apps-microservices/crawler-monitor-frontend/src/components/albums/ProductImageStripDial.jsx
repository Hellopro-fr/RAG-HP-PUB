import { useState, useRef, useEffect } from 'react';
import { AlertCircle, Loader2, RotateCcw, RotateCw } from 'lucide-react';
import { Badge } from '../ui/badge';

const STATUS_VARIANTS = {
  synced:           'success',
  pending:          'outline',
  error:            'destructive',
  downloading:      'outline',
  orphan_manifest:  'destructive',
  ok:               'success',
};

/**
 * Vue d'image utilisée à la fois pour le hero et les vignettes circulaires.
 */
function DialImage({ img, domain }) {
  const isError = img.status === 'error' || img.status === 'orphan_manifest';
  const isDownloading = img.status === 'downloading';
  const src = `/cdn-images/${encodeURIComponent(domain)}/${img.thumb}`;
  if (isError) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-bg-2">
        <AlertCircle className="h-5 w-5 text-err" />
      </div>
    );
  }
  if (isDownloading) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-bg-2">
        <Loader2 className="h-5 w-5 animate-spin text-ink-3" />
      </div>
    );
  }
  return (
    <img
      src={src}
      alt=""
      loading="lazy"
      decoding="async"
      className="h-full w-full object-cover"
    />
  );
}

/**
 * Mode Dial — carrousel projecteur Kodak : roue rotative draggable + image
 * featured à gauche (cf. handoff §4 "Dial `dial`").
 *
 * - Drag (mouse + touch) : `mousedown`/`touchstart` calcule l'angle pointeur
 *   vs centre, suit le mouvement, snap à `Math.round(-a/stepDeg)` au relâcher.
 * - Click vignette non-active → snap à cet index. Click vignette active →
 *   ouvre le drawer.
 * - Vignettes positionnées par `rotate(a) translate(0,-radius) rotate(-a-angle)`
 *   — le second rotate neutralise pour que la vignette reste droite.
 *
 * Cleanup important : tous les listeners attachés à `window` doivent être
 * retirés au démontage pour éviter les fuites.
 *
 * Props : `{ images, domain, onSelectImage }` (signature commune aux 4 modes).
 */
export default function ProductImageStripDial({ images, domain, onSelectImage }) {
  const total = images.length;
  const stepDeg = total > 0 ? 360 / total : 0;
  const [angle, setAngle] = useState(0);
  const dragRef = useRef({ active: false });
  const wrapRef = useRef(null);

  const norm = total > 0 ? ((-angle / stepDeg) % total + total) % total : 0;
  const active = total > 0 ? Math.round(norm) % total : 0;
  const safeActive = Math.min(active, Math.max(total - 1, 0));
  const focused = images[safeActive];

  const snap = (i) => setAngle(-i * stepDeg);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el || total === 0) return undefined;

    const center = () => {
      const r = el.getBoundingClientRect();
      return { cx: r.left + r.width / 2, cy: r.top + r.height / 2 };
    };
    const angleAt = (x, y, c) => Math.atan2(y - c.cy, x - c.cx) * 180 / Math.PI;

    const onDown = (e) => {
      const point = e.touches?.[0] || e;
      const c = center();
      dragRef.current = {
        active: true,
        c,
        startPointer: angleAt(point.clientX, point.clientY, c),
        startAngle: angle,
      };
      el.style.cursor = 'grabbing';
    };
    const onMove = (e) => {
      if (!dragRef.current.active) return;
      const point = e.touches?.[0] || e;
      const cur = angleAt(point.clientX, point.clientY, dragRef.current.c);
      setAngle(dragRef.current.startAngle + (cur - dragRef.current.startPointer));
    };
    const onUp = () => {
      if (!dragRef.current.active) return;
      dragRef.current.active = false;
      el.style.cursor = 'grab';
      // Snap à l'index entier le plus proche.
      setAngle((a) => {
        const n = Math.round(-a / stepDeg);
        return -n * stepDeg;
      });
    };

    el.addEventListener('mousedown', onDown);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    el.addEventListener('touchstart', onDown, { passive: true });
    window.addEventListener('touchmove', onMove, { passive: true });
    window.addEventListener('touchend', onUp);
    return () => {
      el.removeEventListener('mousedown', onDown);
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      el.removeEventListener('touchstart', onDown);
      window.removeEventListener('touchmove', onMove);
      window.removeEventListener('touchend', onUp);
    };
  }, [angle, stepDeg, total]);

  if (!total) return null;
  const focusedVariant = STATUS_VARIANTS[focused.status] || 'outline';
  const radius = 92;

  return (
    <div className="grid grid-cols-[1fr_240px] items-center gap-4">
      <button
        type="button"
        onClick={() => onSelectImage(focused)}
        className="relative h-[200px] w-full overflow-hidden rounded border border-hairline text-left"
        aria-label={`Voir ${focused.filename}`}
      >
        <DialImage img={focused} domain={domain} />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-between gap-2 bg-gradient-to-t from-black/85 to-transparent px-3 py-2">
          <div className="min-w-0">
            <div className="font-mono text-[10px] uppercase tracking-widest text-white/55">
              Slot {String(safeActive + 1).padStart(2, '0')} · loaded
            </div>
            <div className="font-mono text-xs text-white/95 truncate">{focused.filename}</div>
          </div>
          {focused.status && (
            <Badge variant={focusedVariant} className="shrink-0">{focused.status}</Badge>
          )}
        </div>
        <div className="pointer-events-none absolute left-1/2 top-0 -translate-x-1/2">
          <div className="h-2 w-8 rounded-b bg-accent" />
        </div>
      </button>

      <div className="relative h-[210px]">
        <div
          ref={wrapRef}
          className="absolute left-1/2 top-1/2 h-[200px] w-[200px] -translate-x-1/2 -translate-y-1/2 select-none rounded-full border border-hairline"
          style={{
            background: 'radial-gradient(circle at center, hsla(217,33%,17%,0.6) 0%, hsla(222,47%,8%,0.9) 80%)',
            cursor: 'grab',
          }}
        >
          {/* Triangle "12h" indicator */}
          <div
            className="absolute left-1/2 top-0 -translate-x-1/2 -translate-y-1/2"
            style={{
              width: 0,
              height: 0,
              borderLeft: '7px solid transparent',
              borderRight: '7px solid transparent',
              borderTop: '10px solid hsl(var(--primary))',
              filter: 'drop-shadow(0 0 6px hsl(var(--primary)))',
            }}
          />
          <div
            className="absolute inset-0"
            style={{
              transform: `rotate(${angle}deg)`,
              transition: dragRef.current.active ? 'none' : 'transform 320ms cubic-bezier(0.4, 0, 0.2, 1)',
            }}
          >
            {images.map((im, i) => {
              const a = i * stepDeg;
              const isActive = i === safeActive;
              return (
                <button
                  key={im.filename}
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (isActive) onSelectImage(im); else snap(i);
                  }}
                  className="absolute left-1/2 top-1/2 h-9 w-9 overflow-hidden rounded border"
                  style={{
                    transform: `translate(-50%, -50%) rotate(${a}deg) translate(0, -${radius}px) rotate(${-a - angle}deg)`,
                    borderColor: isActive ? 'hsl(var(--primary))' : 'hsla(0,0%,100%,0.15)',
                    boxShadow: isActive
                      ? '0 0 0 2px hsl(var(--primary)), 0 6px 14px hsla(0,0%,0%,0.5)'
                      : 'none',
                    transition: 'border-color 200ms, box-shadow 200ms',
                  }}
                  aria-label={`Image ${i + 1}`}
                >
                  <DialImage img={im} domain={domain} />
                </button>
              );
            })}
          </div>
          {/* Hub central */}
          <div className="absolute left-1/2 top-1/2 grid h-12 w-12 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border border-hairline bg-surface text-center">
            <div className="font-mono text-[10px] leading-tight">
              <div className="text-ink-0 tabular-nums">
                {String(safeActive + 1).padStart(2, '0')}
              </div>
              <div className="text-ink-3 text-[8px]">/ {String(total).padStart(2, '0')}</div>
            </div>
          </div>
        </div>

        <div className="absolute bottom-0 left-1/2 flex -translate-x-1/2 items-center gap-1">
          <button
            type="button"
            onClick={() => snap((safeActive - 1 + total) % total)}
            className="rounded border border-hairline bg-surface p-1 text-ink-3 hover:text-ink-0"
            aria-label="Image précédente"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
          <div className="rounded border border-hairline bg-surface px-2 py-0.5 font-mono text-[10px] uppercase text-ink-3">
            drag · spin
          </div>
          <button
            type="button"
            onClick={() => snap((safeActive + 1) % total)}
            className="rounded border border-hairline bg-surface p-1 text-ink-3 hover:text-ink-0"
            aria-label="Image suivante"
          >
            <RotateCw className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
