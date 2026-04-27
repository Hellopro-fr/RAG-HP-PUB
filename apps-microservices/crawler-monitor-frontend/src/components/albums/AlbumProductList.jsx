import { List } from 'react-window';
import { ProductCard } from './ProductCard';

// Hauteur fixe par carte. Header (~32) + strip 56 + paddings et marges = ~132.
// Si une carte a beaucoup d'images, le strip scroll horizontalement (overflow-x-auto)
// donc la hauteur reste constante.
const CARD_HEIGHT = 132;
const MAX_LIST_HEIGHT = 700;

/**
 * Row component for react-window v2 — reçoit `index`, `style`, et toutes les
 * props additionnelles via `rowProps` (mécanisme v2). On reste minimaliste :
 * la dernière "row" peut être un placeholder de chargement quand `hasMore`
 * est vrai et que l'infinite scroll est en cours.
 */
function ProductRow({ index, style, products, domain, onSelectImage, onRebuild, onDelete, hasMore }) {
  const p = products[index];
  if (!p) {
    // Slot de chargement (dernière row virtuelle quand hasMore = true).
    return (
      <div style={style} className="px-1 pb-2">
        {hasMore && (
          <div className="rounded-md border border-dashed border-border p-3 text-center text-xs text-muted-foreground">
            Chargement…
          </div>
        )}
      </div>
    );
  }
  return (
    <div style={style} className="px-1 pb-2">
      <ProductCard
        product={p}
        domain={domain}
        onSelectImage={onSelectImage}
        onRebuild={onRebuild}
        onDelete={onDelete}
      />
    </div>
  );
}

/**
 * Liste virtualisée (react-window v2 `List`) des produits d'un album.
 *
 * react-window v2 API (différente de v1) :
 *   - `rowComponent` (au lieu de children render-prop)
 *   - `rowCount`, `rowHeight`, `rowProps`
 *   - `style={{ height }}` (hauteur via prop CSS, pas via prop `height`)
 *   - `onRowsRendered({ visibleStopIndex })` pour déclencher l'infinite scroll
 *
 * Précédent posé en Task 11 (`AlbumsTable`) — on garde le même shape.
 */
export function AlbumProductList({
  products,
  domain,
  onSelectImage,
  onRebuild,
  onDelete,
  onLoadMore,
  hasMore,
}) {
  const rowCount = products.length + (hasMore ? 1 : 0);
  // Hauteur calculée pour ne pas réserver 700px quand il n'y a que 2 cartes.
  const listHeight = Math.min(MAX_LIST_HEIGHT, Math.max(CARD_HEIGHT, rowCount * CARD_HEIGHT));

  const handleRowsRendered = ({ visibleStopIndex }) => {
    if (hasMore && visibleStopIndex >= products.length - 1) {
      onLoadMore();
    }
  };

  return (
    <List
      rowComponent={ProductRow}
      rowCount={rowCount}
      rowHeight={CARD_HEIGHT}
      rowProps={{ products, domain, onSelectImage, onRebuild, onDelete, hasMore }}
      style={{ height: listHeight }}
      overscanCount={3}
      onRowsRendered={handleRowsRendered}
    />
  );
}
