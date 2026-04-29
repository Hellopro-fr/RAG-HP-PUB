import { AlertCircle, Loader2 } from 'lucide-react';

/**
 * Vignette d'image (carrée 56×56). Cliquable, sert de trigger pour le drawer
 * (Task 13). En cas de status erreur (`error` / `orphan_manifest`), affiche
 * une icône au lieu de l'image. Le `<img>` charge la version `thumb` via
 * `/cdn-images/{domain}/{thumb}` — `thumb` inclut déjà le préfixe `produit-3/...`
 * (cf. spec section 5.2 schéma manifeste).
 */
export function ImageThumb({ image, domain, onClick }) {
  const isError = image.status === 'error' || image.status === 'orphan_manifest';
  const isDownloading = image.status === 'downloading';
  const src = `/cdn-images/${encodeURIComponent(domain)}/${image.thumb}`;

  return (
    <button
      type="button"
      onClick={onClick}
      className={`relative h-14 w-14 shrink-0 overflow-hidden rounded border bg-muted hover:ring-2 hover:ring-primary ${
        isError ? 'border-dashed border-destructive' : 'border-border'
      }`}
      title={image.url_source || image.filename}
      aria-label={`Image ${image.filename}${isError ? ' (en erreur)' : ''}`}
    >
      {isError ? (
        <AlertCircle className="absolute inset-0 m-auto h-5 w-5 text-destructive" />
      ) : isDownloading ? (
        <Loader2 className="absolute inset-0 m-auto h-5 w-5 animate-spin text-muted-foreground" />
      ) : (
        <img
          src={src}
          alt=""
          loading="lazy"
          decoding="async"
          className="h-full w-full object-cover"
        />
      )}
    </button>
  );
}
