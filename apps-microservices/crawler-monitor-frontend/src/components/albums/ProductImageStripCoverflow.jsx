import { useState } from 'react';
import { AlertCircle, ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';

/**
 * Vue d'image utilisée à la fois pour la carte et son reflet — interne à la
 * variation Coverflow.
 */
function CoverflowImage({ img, domain }) {
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
 * Mode Coverflow — image centrale 1:1 + cartes latérales tournées en perspective
 * (cf. handoff §2 "Coverflow `coverflow`").
 *
 * - Calcul `wrap` = chemin le plus court (gauche/droite équidistants) pour le
 *   wrap-around des slides.
 * - Reflet sous chaque carte : la même image dupliquée, scaleY(-1) + masque
 *   dégradé (opacité 0.5 max).
 * - Click carte non-centrée → la centre ; click carte centrée → ouvre le drawer.
 *
 * Note Tailwind : les classes `perspective-1000`, `preserve-3d` et
 * `backface-hidden` ne sont pas définies par défaut dans le repo — on utilise
 * directement `style={{ perspective, transformStyle, backfaceVisibility }}`.
 *
 * Props : `{ images, domain, onSelectImage }` (signature commune aux 4 modes).
 */
export default function ProductImageStripCoverflow({ images, domain, onSelectImage }) {
  const [center, setCenter] = useState(0);
  const total = images.length;
  if (!total) return null;
  const goTo = (i) => setCenter(((i % total) + total) % total);
  const safeCenter = Math.min(center, total - 1);
  const focused = images[safeCenter];

  return (
    <div className="relative">
      <div
        className="relative h-[210px] overflow-hidden rounded"
        style={{
          background: 'radial-gradient(ellipse at center, hsla(217, 33%, 22%, 0.5) 0%, transparent 65%)',
          perspective: '1000px',
        }}
      >
        <div className="absolute inset-0">
          {images.map((img, i) => {
            const offset = i - safeCenter;
            const wrap = ((offset + total / 2) % total + total) % total - total / 2;
            const abs = Math.abs(wrap);
            const isCenter = abs < 0.5;
            const sign = wrap < 0 ? -1 : 1;
            const x = wrap * 78;
            const z = -abs * 90;
            const rotY = -sign * Math.min(abs, 4) * 38;
            const scale = isCenter ? 1.0 : 0.78;
            const visible = abs <= 4;

            return (
              <div
                key={img.filename}
                className="absolute left-1/2 top-1/2"
                style={{
                  width: 130,
                  height: 130,
                  marginLeft: -65,
                  marginTop: -75,
                  zIndex: 100 - Math.round(abs * 10),
                  transform: `translate3d(${x}px, 0, ${z}px) rotateY(${rotY}deg) scale(${scale})`,
                  transition: 'transform 480ms cubic-bezier(0.4, 0, 0.2, 1), opacity 320ms',
                  opacity: visible ? (isCenter ? 1 : 0.85 - abs * 0.12) : 0,
                  pointerEvents: visible ? 'auto' : 'none',
                  transformStyle: 'preserve-3d',
                }}
                onClick={() => isCenter ? onSelectImage(img) : goTo(i)}
              >
                <div
                  className="relative h-full w-full cursor-pointer overflow-hidden rounded border border-hairline shadow-[0_12px_32px_-10px_rgba(0,0,0,0.85)]"
                  style={{ backfaceVisibility: 'hidden' }}
                >
                  <CoverflowImage img={img} domain={domain} />
                  {isCenter && (
                    <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 to-transparent px-2 py-1.5">
                      <div className="font-mono text-[10px] text-white/90 truncate">{img.filename}</div>
                    </div>
                  )}
                </div>
                <div
                  className="absolute left-0 top-full h-full w-full overflow-hidden rounded"
                  style={{
                    transform: 'scaleY(-1)',
                    maskImage: 'linear-gradient(to bottom, hsla(0,0%,0%,0.45), transparent 60%)',
                    WebkitMaskImage: 'linear-gradient(to bottom, hsla(0,0%,0%,0.45), transparent 60%)',
                    opacity: 0.5,
                    pointerEvents: 'none',
                    backfaceVisibility: 'hidden',
                  }}
                  aria-hidden="true"
                >
                  <CoverflowImage img={img} domain={domain} />
                </div>
              </div>
            );
          })}
        </div>

        <button
          type="button"
          onClick={() => goTo(safeCenter - 1)}
          className="absolute left-2 top-1/2 z-50 -translate-y-1/2 rounded-full border border-hairline bg-surface/80 p-1.5 text-ink-3 backdrop-blur hover:text-ink-0"
          aria-label="Image précédente"
          disabled={total <= 1}
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={() => goTo(safeCenter + 1)}
          className="absolute right-2 top-1/2 z-50 -translate-y-1/2 rounded-full border border-hairline bg-surface/80 p-1.5 text-ink-3 backdrop-blur hover:text-ink-0"
          aria-label="Image suivante"
          disabled={total <= 1}
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>

      <div className="mt-2 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 font-mono text-[11px] text-ink-3 min-w-0">
          <span className="tabular-nums text-ink-0">
            {String(safeCenter + 1).padStart(2, '0')}
            <span className="text-ink-3">/{total}</span>
          </span>
          <span className="text-border">·</span>
          <span className="truncate">{focused.filename} · {focused.status}</span>
        </div>
        <div className="flex h-1 flex-1 max-w-[200px] overflow-hidden rounded bg-secondary">
          <div
            className="h-full bg-accent transition-[width] duration-500"
            style={{ width: `${((safeCenter + 1) / total) * 100}%` }}
          />
        </div>
      </div>
    </div>
  );
}
