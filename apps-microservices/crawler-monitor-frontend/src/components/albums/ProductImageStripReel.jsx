import { useState, useEffect, useRef } from 'react';
import { AlertCircle, Loader2, Pause, Play, SkipBack, SkipForward } from 'lucide-react';

/**
 * Vue d'image pour la variation Reel (hero + filmstrip).
 */
function ReelImage({ img, domain }) {
  const isError = img.status === 'error' || img.status === 'orphan_manifest';
  const isDownloading = img.status === 'downloading';
  const src = `/cdn-images/${encodeURIComponent(domain)}/${img.thumb}`;
  if (isError) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-muted">
        <AlertCircle className="h-5 w-5 text-destructive" />
      </div>
    );
  }
  if (isDownloading) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-muted">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
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
 * Mode Reel — bobine cinéma : hero "now playing" à gauche + filmstrip défilable
 * à droite (cf. handoff §3 "Bobine `reel`").
 *
 * - Auto-advance toutes les 2200ms si `playing === true`.
 * - À chaque changement d'`active`, le frame correspondant est `scrollIntoView`
 *   en horizontal (smooth, center).
 * - Click frame → la sélectionne (sans ouvrir le drawer). Double-click frame
 *   ou click hero → ouvre le drawer.
 * - Crosshairs aux 4 coins du hero, dot rouge pulsant si playing, perforations
 *   sprocket en haut/bas du filmstrip.
 *
 * Note React 18 strict mode (Vite dev) : `setInterval` peut être démonté/remonté
 * 2x. Le cleanup dans `useEffect` clear l'interval donc pas de double-fire en
 * pratique (deuxième mount → nouveau timer, l'ancien est cleared).
 *
 * Props : `{ images, domain, onSelectImage }` (signature commune aux 4 modes).
 */
export default function ProductImageStripReel({ images, domain, onSelectImage }) {
  const [active, setActive] = useState(0);
  const [playing, setPlaying] = useState(false);
  const stripRef = useRef(null);
  const total = images.length;

  useEffect(() => {
    if (!playing || total <= 1) return undefined;
    const id = window.setInterval(() => setActive((a) => (a + 1) % total), 2200);
    return () => window.clearInterval(id);
  }, [playing, total]);

  useEffect(() => {
    const strip = stripRef.current;
    if (!strip) return;
    const frame = strip.querySelector(`[data-frame="${active}"]`);
    if (frame) frame.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
  }, [active]);

  if (!total) return null;
  const safeActive = Math.min(active, total - 1);
  const img = images[safeActive];

  return (
    <div className="grid grid-cols-[176px_1fr] gap-3">
      <div className="relative">
        <button
          type="button"
          onClick={() => onSelectImage(img)}
          className="relative block aspect-[4/3] w-full overflow-hidden rounded border border-border"
          aria-label={`Voir ${img.filename}`}
        >
          <ReelImage img={img} domain={domain} />
          <div
            className="pointer-events-none absolute inset-0"
            style={{ background: 'radial-gradient(ellipse at center, transparent 30%, hsla(0,0%,0%,0.55) 100%)' }}
          />
          {[
            'top-1 left-1 border-t border-l',
            'top-1 right-1 border-t border-r',
            'bottom-1 left-1 border-b border-l',
            'bottom-1 right-1 border-b border-r',
          ].map((cls) => (
            <div
              key={cls}
              className={`absolute h-2 w-2 ${cls}`}
              style={{ borderColor: 'hsla(0,0%,100%,0.45)' }}
              aria-hidden="true"
            />
          ))}
          <div className="absolute left-1.5 top-1.5 flex items-center gap-1.5 rounded bg-black/55 px-1.5 py-0.5 font-mono text-[10px] text-white/85 backdrop-blur">
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{
                background: playing ? 'hsl(0 84% 60%)' : 'hsla(0,0%,100%,0.4)',
                boxShadow: playing ? '0 0 6px hsl(0 84% 60%)' : 'none',
              }}
            />
            REC · {String(safeActive + 1).padStart(3, '0')}/{String(total).padStart(3, '0')}
          </div>
        </button>
        <div className="mt-1.5 flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setPlaying((p) => !p)}
            className="rounded border border-border bg-card p-1 text-muted-foreground hover:text-foreground"
            aria-label={playing ? 'Pause' : 'Play'}
          >
            {playing ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
          </button>
          <button
            type="button"
            onClick={() => setActive((a) => (a - 1 + total) % total)}
            className="rounded border border-border bg-card p-1 text-muted-foreground hover:text-foreground"
            aria-label="Image précédente"
          >
            <SkipBack className="h-3 w-3" />
          </button>
          <button
            type="button"
            onClick={() => setActive((a) => (a + 1) % total)}
            className="rounded border border-border bg-card p-1 text-muted-foreground hover:text-foreground"
            aria-label="Image suivante"
          >
            <SkipForward className="h-3 w-3" />
          </button>
          <div className="ml-1 truncate font-mono text-[10px] text-muted-foreground">
            {img.filename} · {img.status}
          </div>
        </div>
      </div>

      <div className="relative self-stretch">
        {/* Perforations sprocket */}
        <div
          className="absolute inset-x-0 top-0 h-2"
          style={{
            backgroundImage: 'radial-gradient(circle 4px at 14px 4px, hsla(0,0%,0%,0.85) 100%, transparent 100%)',
            backgroundSize: '28px 8px',
            backgroundRepeat: 'repeat-x',
          }}
          aria-hidden="true"
        />
        <div
          className="absolute inset-x-0 bottom-0 h-2"
          style={{
            backgroundImage: 'radial-gradient(circle 4px at 14px 4px, hsla(0,0%,0%,0.85) 100%, transparent 100%)',
            backgroundSize: '28px 8px',
            backgroundRepeat: 'repeat-x',
          }}
          aria-hidden="true"
        />

        <div
          ref={stripRef}
          className="absolute inset-x-0 top-2 bottom-2 flex items-stretch gap-1 overflow-x-auto rounded-[2px] px-1.5 py-1"
          style={{ scrollbarWidth: 'none', background: 'hsl(220, 15%, 4%)' }}
        >
          {images.map((im, i) => {
            const isActive = i === safeActive;
            return (
              <button
                key={im.filename}
                type="button"
                data-frame={i}
                onClick={() => setActive(i)}
                onDoubleClick={() => onSelectImage(im)}
                className="relative aspect-[4/3] h-full shrink-0 overflow-hidden rounded-[2px]"
                style={{
                  outline: isActive ? '2px solid hsl(var(--primary))' : '1px solid hsla(0,0%,100%,0.08)',
                  outlineOffset: isActive ? '-2px' : '-1px',
                  filter: isActive ? 'none' : 'brightness(0.65) saturate(0.7)',
                  transition: 'filter 200ms, outline-color 200ms',
                }}
                aria-label={`Frame ${i + 1}`}
              >
                <ReelImage img={im} domain={domain} />
                <div className="absolute left-0.5 top-0.5 rounded bg-black/60 px-1 font-mono text-[8px] text-white/80">
                  {String(i + 1).padStart(3, '0')}
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
