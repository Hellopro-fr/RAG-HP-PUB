import { useState, useCallback } from 'react';
import { AlertCircle, ChevronLeft, Loader2 } from 'lucide-react';
import { Badge } from '../ui/badge';

// Mapping `image.status` → variant Badge. Cohérent avec ProductCard.jsx +
// ajout des statuts spécifiques aux images (downloading, orphan_manifest).
const STATUS_VARIANTS = {
  synced:           'success',
  pending:          'outline',
  error:            'destructive',
  downloading:      'outline',
  orphan_manifest:  'destructive',
  ok:               'success',
};

/**
 * Vignette unique d'image avec gestion des états (error, downloading) — interne
 * à la variation Deck. Pas de bouton autour ; la carte parente est cliquable.
 */
function DeckImage({ img, domain }) {
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
 * Mode Stack — pile rotative de cartes (cf. handoff §1 "Stack `deck`").
 *
 * La carte du dessus est cliquable (ouvre le drawer via `onSelectImage`) ;
 * double-click OU bouton "Suivante" → défausse + ré-empile en bas. Le bouton
 * "←" ramène la dernière carte au sommet sans animation (volontaire — perception
 * "couper le paquet").
 *
 * Les dots à droite permettent de sauter directement à un index : la pile est
 * tournée circulairement pour amener cette image au sommet.
 *
 * Props : `{ images, domain, onSelectImage }` (signature commune aux 4 modes).
 */
export default function ProductImageStripDeck({ images, domain, onSelectImage }) {
  // `order` = liste d'index (références dans `images`) dans l'ordre courant
  // de la pile (premier = top). On garde des index pour pouvoir réutiliser
  // `images[idx]` sans copier les objets.
  const [order, setOrder] = useState(images.map((_, i) => i));
  const [pulled, setPulled] = useState(null);

  const next = useCallback(() => {
    setPulled(order[0]);
    window.setTimeout(() => {
      setOrder((o) => [...o.slice(1), o[0]]);
      setPulled(null);
    }, 380);
  }, [order]);

  const prev = useCallback(() => {
    setOrder((o) => [o[o.length - 1], ...o.slice(0, -1)]);
  }, []);

  if (!images.length) return null;

  const topIdx = order[0];
  const topImg = images[topIdx];
  const topStatus = topImg?.status;
  const topVariant = STATUS_VARIANTS[topStatus] || 'outline';

  return (
    <div className="grid grid-cols-[1fr_auto] gap-4">
      <div className="relative h-[200px]">
        <div className="absolute inset-0">
          {order.map((imgIdx, stackPos) => {
            const img = images[imgIdx];
            const visible = stackPos < 5;
            const isPulled = pulled === imgIdx;
            const baseTilt = (stackPos === 0 ? -1.5 : (stackPos % 2 === 0 ? 1.5 : -2.5)) * (1 + stackPos * 0.4);
            const offsetX = stackPos * 8;
            const offsetY = stackPos * 6;
            const scale = 1 - stackPos * 0.04;
            const opacity = visible ? 1 - stackPos * 0.06 : 0;
            const z = 100 - stackPos;
            const transform = isPulled
              ? `translate(140%, -10%) rotate(18deg) scale(0.92)`
              : `translate(${offsetX}px, ${offsetY}px) rotate(${baseTilt}deg) scale(${scale})`;
            return (
              <div
                key={img.filename}
                className="absolute left-0 top-0 h-[200px] w-[300px] origin-bottom-left rounded-md border border-hairline shadow-[0_8px_24px_-6px_rgba(0,0,0,0.6)] overflow-hidden"
                style={{
                  zIndex: z,
                  opacity: isPulled ? 0 : opacity,
                  transform,
                  transition: 'transform 380ms cubic-bezier(0.5, 0, 0.2, 1), opacity 380ms ease',
                  pointerEvents: stackPos === 0 ? 'auto' : 'none',
                }}
              >
                <button
                  type="button"
                  className="block h-full w-full cursor-pointer text-left"
                  onClick={stackPos === 0 ? () => onSelectImage(img) : undefined}
                  onDoubleClick={stackPos === 0 ? next : undefined}
                  aria-label={`Voir ${img.filename}`}
                >
                  <DeckImage img={img} domain={domain} />
                </button>
                {stackPos === 0 && !isPulled && (
                  <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-between gap-2 rounded-b-md bg-gradient-to-t from-black/85 to-transparent px-2.5 py-1.5">
                    <div className="font-mono text-[10px] text-white/80 truncate">
                      {img.filename} · {String(order[0] + 1).padStart(2, '0')}/{images.length}
                    </div>
                    {topStatus && (
                      <Badge variant={topVariant} className="shrink-0">{topStatus}</Badge>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="flex w-[140px] flex-col justify-between">
        <div>
          <div className="mb-2 font-mono text-[10px] uppercase tracking-widest text-ink-3">Stack</div>
          <div className="font-mono text-2xl tabular-nums text-ink-0">
            {String(order[0] + 1).padStart(2, '0')}
            <span className="text-sm text-ink-3">/{images.length}</span>
          </div>
        </div>

        <div className="grid grid-cols-5 gap-1.5">
          {images.map((_, i) => (
            <button
              key={i}
              type="button"
              onClick={() => {
                const start = order.indexOf(i);
                if (start === 0) return;
                setOrder((o) => [...o.slice(start), ...o.slice(0, start)]);
              }}
              className="h-1.5 rounded-full"
              style={{ background: order[0] === i ? 'hsl(var(--primary))' : 'hsla(0,0%,100%,0.15)' }}
              aria-label={`Image ${i + 1}`}
            />
          ))}
        </div>

        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={prev}
            disabled={images.length <= 1}
            className="flex-1 rounded border border-hairline py-1.5 text-ink-3 hover:text-ink-0 disabled:opacity-50 disabled:cursor-not-allowed"
            aria-label="Image précédente"
          >
            <ChevronLeft className="mx-auto h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={next}
            disabled={images.length <= 1}
            className="flex-[2] rounded bg-accent py-1.5 text-xs font-medium text-accent-foreground hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Suivante →
          </button>
        </div>
      </div>
    </div>
  );
}
