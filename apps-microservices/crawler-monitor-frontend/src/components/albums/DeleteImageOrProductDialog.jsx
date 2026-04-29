import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import { Button } from '../ui/button';

/**
 * Dialog simple (Radix Dialog) pour confirmer la suppression d'une image ou
 * d'un produit (champ `kind` = 'image' | 'product'). Utilisé par
 * `AlbumDetailPage` (suppression produit, Task 12) et plus tard par
 * `ImageDetailSheet` (suppression image, Task 13).
 *
 * Pas de type-to-confirm ici (différent de `ConfirmDestructive` côté
 * suppression d'album entier) : suppression individuelle = friction modérée.
 */
export function DeleteImageOrProductDialog({ open, kind, label, busy, onConfirm, onCancel }) {
  const title = kind === 'image' ? "Supprimer l'image" : 'Supprimer le produit';

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v && !busy) onCancel(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {kind === 'image' ? (
              <>
                Cette action supprime <code className="rounded bg-muted px-1 py-0.5">{label}</code> du
                disque. Action irréversible.
              </>
            ) : (
              <>
                Cette action supprime le produit{' '}
                <code className="rounded bg-muted px-1 py-0.5">{label}</code> et toutes ses images.
                Action irréversible.
              </>
            )}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel} disabled={busy}>
            Annuler
          </Button>
          <Button variant="destructive" onClick={onConfirm} disabled={busy}>
            {busy ? 'En cours…' : 'Supprimer'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
