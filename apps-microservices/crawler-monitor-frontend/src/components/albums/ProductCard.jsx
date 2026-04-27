import { memo } from 'react';
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

const STATUS_VARIANTS = {
  synced:  'success',
  pending: 'outline',
  error:   'destructive',
};

/**
 * Carte produit (header + dropdown actions + strip horizontale d'images).
 *
 * Mémoïsée : la liste virtualisée des produits ré-rend toutes les Row à chaque
 * scroll, donc on évite les re-renders inutiles avec `memo`. Les callbacks
 * (`onSelectImage`, `onRebuild`, `onDelete`) sont stables côté parent
 * (références créées dans `AlbumDetailPage`).
 */
function ProductCardImpl({ product, domain, onSelectImage, onRebuild, onDelete }) {
  const variant = STATUS_VARIANTS[product.sync_status] || 'outline';

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
      <ProductImageStrip
        domain={domain}
        images={product.images}
        onSelectImage={(img) => onSelectImage(img, product)}
      />
    </div>
  );
}

export const ProductCard = memo(ProductCardImpl);
