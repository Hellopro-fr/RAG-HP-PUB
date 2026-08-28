import { List } from 'react-window';
import { ProductCard } from './ProductCard';

/*
 * Hauteur de ligne fixe imposée par react-window. Sous-estimée, la carte
 * déborde sur la suivante ; les 280 précédents étaient une estimation à vue.
 * Décomposition mesurée sur les classes réelles de ProductCard +
 * ProductImageStripCoverflow :
 *
 *   ProductCard    bordures 1px × 2 ..............................    2
 *                  p-3 (12px haut + 12px bas) ....................   24
 *                  header : Button h-7 = 28px .....................   28
 *                  space-y-2 entre header et strip ................    8
 *   Coverflow      scène h-[210px] ................................  210
 *                  mt-2 avant la légende ..........................    8
 *                  légende text-[11px] × line-height 1.5 ..........   17
 *                                                                   ----
 *                  carte ..........................................  297
 *   ProductRow     pb-2 (gouttière entre deux lignes) .............    8
 *                                                                   ----
 *                  total ..........................................  305
 *
 * Arrondi à 308 : ~3px de marge pour les arrondis de rendu (line-height
 * fractionnaire, zoom navigateur) sans creuser de blanc visible.
 */
const CARD_HEIGHT = 308;
const MAX_LIST_HEIGHT = 700;

/**
 * Row component for react-window v2 — reçoit `index`, `style`, et toutes les
 * props additionnelles via `rowProps` (mécanisme v2). On reste minimaliste :
 * la dernière "row" peut être un placeholder de chargement quand `hasMore`
 * est vrai et que l'infinite scroll est en cours.
 */
function ProductRow({
  index,
  style,
  products,
  domain,
  onSelectImage,
  onRebuild,
  onDelete,
  hasMore,
}) {
  const p = products[index];
  if (!p) {
    // Slot de chargement (dernière row virtuelle quand hasMore = true).
    return (
      <div style={style} className="px-1 pb-2">
        {hasMore && (
          <div className="rounded-md border border-dashed border-hairline p-3 text-center text-xs text-ink-3">
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
