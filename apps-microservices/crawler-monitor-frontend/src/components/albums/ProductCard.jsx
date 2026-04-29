import { lazy, memo, Suspense } from 'react';
import { MoreVertical, RefreshCw, Trash2 } from 'lucide-react';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu';
import { ProductImageStrip } from './ProductImageStrip';

// Lazy imports pour les variations stylisées : un utilisateur qui reste sur le
// mode legacy (`null` / valeur invalide) ne paie pas le JS des autres modes.
// Default export attendu dans chaque fichier pour que `lazy()` fonctionne.
const ProductImageStripDeck = lazy(() => import('./ProductImageStripDeck'));
const ProductImageStripCoverflow = lazy(() => import('./ProductImageStripCoverflow'));
const ProductImageStripReel = lazy(() => import('./ProductImageStripReel'));
const ProductImageStripDial = lazy(() => import('./ProductImageStripDial'));

const STATUS_VARIANTS = {
  synced:  'success',
  pending: 'outline',
  error:   'destructive',
};

/**
 * Carte produit (header + dropdown actions + strip d'images).
 *
 * La strip d'images est dispatchée selon `imageMode` :
 *   - `deck`      → ProductImageStripDeck      (pile rotative)
 *   - `coverflow` → ProductImageStripCoverflow (3D iTunes)
 *   - `reel`      → ProductImageStripReel      (filmstrip)
 *   - `dial`      → ProductImageStripDial      (carrousel projecteur)
 *   - autre/null  → ProductImageStrip          (legacy, bande horizontale)
 *
 * Mémoïsée : la liste virtualisée des produits ré-rend toutes les Row à chaque
 * scroll, donc on évite les re-renders inutiles avec `memo`. Les callbacks
 * (`onSelectImage`, `onRebuild`, `onDelete`) sont stables côté parent
 * (références créées dans `AlbumDetailPage`).
 */
function ProductCardImpl({ product, domain, onSelectImage, onRebuild, onDelete, imageMode }) {
  const variant = STATUS_VARIANTS[product.sync_status] || 'outline';

  const stripCommon = {
    domain,
    images: product.images,
    onSelectImage: (img) => onSelectImage(img, product),
  };
  let strip;
  switch (imageMode) {
    case 'deck':      strip = <ProductImageStripDeck {...stripCommon} />; break;
    case 'reel':      strip = <ProductImageStripReel {...stripCommon} />; break;
    case 'dial':      strip = <ProductImageStripDial {...stripCommon} />; break;
    case 'coverflow': strip = <ProductImageStripCoverflow {...stripCommon} />; break;
    default:          strip = <ProductImageStrip {...stripCommon} />;
  }

  const hasImages = product.images && product.images.length > 0;
  const isLegacy = !imageMode || (
    imageMode !== 'deck' && imageMode !== 'reel' &&
    imageMode !== 'dial' && imageMode !== 'coverflow'
  );

  return (
    <div className="space-y-2 rounded-md border border-border bg-card p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="font-mono text-xs text-muted-foreground">#{product.id_produit}</span>
          <span className="truncate font-medium">{product.nom}</span>
          <Badge variant={variant}>{product.sync_status}</Badge>
          {product.error_count > 0 && (
            <Badge variant="destructive">{product.error_count} err</Badge>
          )}
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              aria-label={`Actions produit ${product.nom || product.id_produit}`}
            >
              <MoreVertical className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => onRebuild(product)}>
              <RefreshCw className="mr-2 h-4 w-4" /> Rebuild (force redownload)
            </DropdownMenuItem>
            <DropdownMenuItem
              className="text-destructive focus:text-destructive"
              onClick={() => onDelete(product)}
            >
              <Trash2 className="mr-2 h-4 w-4" /> Supprimer le produit
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {!hasImages ? (
        <div className="text-xs italic text-muted-foreground">Aucune image</div>
      ) : isLegacy ? (
        // Mode legacy : pas de Suspense (composant chargé statiquement, pas de coût).
        strip
      ) : (
        <Suspense fallback={<div className="h-[200px] animate-pulse rounded bg-muted" />}>
          {strip}
        </Suspense>
      )}
    </div>
  );
}

export const ProductCard = memo(ProductCardImpl);
