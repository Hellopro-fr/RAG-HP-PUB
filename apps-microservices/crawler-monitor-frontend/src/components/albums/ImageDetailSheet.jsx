import { useState } from 'react';
import { RefreshCw, Trash2, AlertCircle, ExternalLink } from 'lucide-react';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '../ui/sheet';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import {
  useImageRedownloadMutation,
  useDeleteImageMutation,
} from '../../hooks/queries';
import { DeleteImageOrProductDialog } from './DeleteImageOrProductDialog';

/**
 * Drawer latéral droit (shadcn `Sheet`) qui s'ouvre quand l'utilisateur clique
 * sur une vignette image dans `AlbumDetailPage`. Affiche :
 *  - preview moyenne (`/cdn-images/{domain}/{image.main}` — version `produit-2/...`)
 *  - métadonnées (`url_source`, `filename`, `status` badge)
 *  - actions C/D : Re-télécharger / Supprimer (avec dialog de confirmation)
 *
 * Les hooks de mutation (Task 10) attendent `{ domain, productId, imageId }` —
 * on passe donc `imageId: image.filename` (l'API utilise le filename comme id
 * dans le path `/products/{productId}/images/{imageId}`).
 *
 * Ferme via Esc, clic sur le backdrop, ou la croix (gérés nativement par Radix
 * Dialog/Sheet via `onOpenChange`). Après une suppression réussie, le drawer
 * se ferme automatiquement.
 */
const STATUS_LABEL = {
  ok:              { label: 'OK',                variant: 'secondary' },
  error:           { label: 'Erreur',            variant: 'destructive' },
  downloading:     { label: 'En cours…',         variant: 'outline' },
  orphan_manifest: { label: 'Fichier manquant',  variant: 'destructive' },
  orphan_file:     { label: 'Manifest manquant', variant: 'destructive' },
};

export function ImageDetailSheet({ open, image, product, domain, onClose, token }) {
  const [pendingDelete, setPendingDelete] = useState(false);
  const redownload = useImageRedownloadMutation(token);
  const deleteImage = useDeleteImageMutation(token);

  // Cas où le drawer est en transition vers `closed` mais que `selected` est
  // déjà null côté parent — on rend une coquille vide pour que Radix anime
  // proprement la fermeture.
  if (!image || !product) {
    return (
      <Sheet open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
        <SheetContent side="right" className="w-[480px]" />
      </Sheet>
    );
  }

  const statusInfo = STATUS_LABEL[image.status] || { label: image.status, variant: 'outline' };
  const isMissing = image.status === 'orphan_manifest' || image.status === 'error';
  const previewSrc = `/cdn-images/${encodeURIComponent(domain)}/${image.main}`;

  return (
    <>
      <Sheet open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
        <SheetContent side="right" className="flex w-[480px] flex-col">
          <SheetHeader>
            <SheetTitle className="font-mono text-base">{image.filename}</SheetTitle>
            <SheetDescription>
              Produit <code>#{product.id_produit}</code> · {product.nom}
            </SheetDescription>
          </SheetHeader>

          <div className="mt-4 flex-1 space-y-4 overflow-y-auto">
            <div className="flex aspect-square items-center justify-center overflow-hidden rounded border bg-bg-2">
              {isMissing ? (
                <AlertCircle className="h-10 w-10 text-err" />
              ) : (
                <img src={previewSrc} alt="" className="h-full w-full object-contain" />
              )}
            </div>

            <dl className="space-y-2 text-sm">
              <div>
                <dt className="text-xs text-ink-3">Statut</dt>
                <dd>
                  <Badge variant={statusInfo.variant}>{statusInfo.label}</Badge>
                </dd>
              </div>
              <div>
                <dt className="text-xs text-ink-3">URL source</dt>
                <dd className="break-all font-mono text-xs">
                  {image.url_source ? (
                    <a
                      href={image.url_source}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 hover:underline"
                    >
                      {image.url_source}
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  ) : (
                    <span className="text-ink-3">—</span>
                  )}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-ink-3">Chemin (main)</dt>
                <dd className="break-all font-mono text-xs">{image.main}</dd>
              </div>
            </dl>
          </div>

          <div className="flex gap-2 border-t pt-3">
            <Button
              variant="outline"
              className="flex-1"
              disabled={redownload.isPending}
              onClick={() =>
                redownload.mutate({
                  domain,
                  productId: product.id_produit,
                  imageId: image.filename,
                })
              }
            >
              <RefreshCw
                className={`mr-2 h-4 w-4 ${redownload.isPending ? 'animate-spin' : ''}`}
              />
              Re-télécharger
            </Button>
            <Button
              variant="destructive"
              className="flex-1"
              onClick={() => setPendingDelete(true)}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Supprimer
            </Button>
          </div>
        </SheetContent>
      </Sheet>

      <DeleteImageOrProductDialog
        open={pendingDelete}
        kind="image"
        label={image.filename}
        busy={deleteImage.isPending}
        onConfirm={async () => {
          try {
            await deleteImage.mutateAsync({
              domain,
              productId: product.id_produit,
              imageId: image.filename,
            });
            // Fermer le dialog confirm d'abord, puis le drawer (lecture
            // visuelle plus propre : confirm disparaît, puis sheet glisse).
            setPendingDelete(false);
            onClose();
          } catch {
            // Erreur affichée côté API client / toast global ; on garde le
            // dialog ouvert pour permettre un retry manuel.
            setPendingDelete(false);
          }
        }}
        onCancel={() => setPendingDelete(false)}
      />
    </>
  );
}
