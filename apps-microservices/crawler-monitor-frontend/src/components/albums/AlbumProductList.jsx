import { List } from 'react-window';
import { ProductCard } from './ProductCard';

// Hauteur fixe par carte selon le mode d'affichage des images :
//   - legacy (bande horizontale 56×56) : header (~32) + strip 56 + paddings = ~132
//   - fancy (deck/coverflow/reel/dial) : strip ~200-210 + chrome (header, controls,
//     captions) + paddings de la carte = ~280
const CARD_HEIGHT_LEGACY = 132;
const CARD_HEIGHT_FANCY  = 280;
const MAX_LIST_HEIGHT = 700;

const FANCY_MODES = new Set(['deck', 'coverflow', 'reel', 'dial']);

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
  imageMode,
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
        imageMode={imageMode}
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
 * `rowHeight` est calculé selon `imageMode` (132 legacy, 280 fancy). Quand le
 * user change de mode, react-window ré-rend toutes les rows avec la nouvelle
 * hauteur — pas besoin d'invalider le cache.
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
  imageMode,
}) {
  const rowCount = products.length + (hasMore ? 1 : 0);
  const rowHeight = FANCY_MODES.has(imageMode) ? CARD_HEIGHT_FANCY : CARD_HEIGHT_LEGACY;
  // Hauteur calculée pour ne pas réserver 700px quand il n'y a que 2 cartes.
  const listHeight = Math.min(MAX_LIST_HEIGHT, Math.max(rowHeight, rowCount * rowHeight));

  const handleRowsRendered = ({ visibleStopIndex }) => {
    if (hasMore && visibleStopIndex >= products.length - 1) {
      onLoadMore();
    }
  };

  return (
    <List
      rowComponent={ProductRow}
      rowCount={rowCount}
      rowHeight={rowHeight}
      rowProps={{ products, domain, onSelectImage, onRebuild, onDelete, hasMore, imageMode }}
      style={{ height: listHeight }}
      overscanCount={3}
      onRowsRendered={handleRowsRendered}
    />
  );
}
