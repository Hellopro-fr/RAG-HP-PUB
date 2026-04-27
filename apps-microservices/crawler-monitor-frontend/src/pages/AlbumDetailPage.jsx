import { useMemo, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import {
  useAlbumProductsQuery,
  useProductRedownloadMutation,
  useDeleteProductMutation,
} from '../hooks/queries';
import { AlbumHeader } from '../components/albums/AlbumHeader';
import { AlbumToolbar } from '../components/albums/AlbumToolbar';
import { AlbumProductList } from '../components/albums/AlbumProductList';
import { DeleteImageOrProductDialog } from '../components/albums/DeleteImageOrProductDialog';
import { Card } from '../components/ui/card';

/**
 * Page détail `/albums/:domain` — Mix 1 (stacked products).
 *
 * Affiche la liste virtualisée des produits du domaine, chacun avec son
 * header (id, nom, sync_status, error_count, dropdown actions) et sa strip
 * horizontale d'images. Click sur une image → `onSelectImage(img, product)`
 * (le drawer arrive en Task 13 ; pour l'instant, on log + state local).
 *
 * Polling adaptatif : `refetchInterval = 10s` activé si ≥1 image visible
 * a status `downloading`, sinon `false` (pas de polling). React Query v5
 * appelle la fonction avec l'objet query — on accède à `query.state.data.pages`.
 */
export default function AlbumDetailPage({ token }) {
  const { domain: rawDomain } = useParams();
  const domain = decodeURIComponent(rawDomain);

  const [q, setQ] = useState('');
  const [filter, setFilter] = useState('all');
  const [sort, setSort] = useState('updated');
  const [pendingProductDelete, setPendingProductDelete] = useState(null);
  const [, setSelected] = useState(null);

  const params = useMemo(() => ({ q, filter, sort }), [q, filter, sort]);

  const productsQ = useAlbumProductsQuery(token, domain, params, {
    refetchInterval: (query) => {
      const allPages = query.state.data?.pages || [];
      const anyDownloading = allPages.some((pg) =>
        (pg.products || []).some((p) =>
          (p.images || []).some((img) => img.status === 'downloading'),
        ),
      );
      return anyDownloading ? 10_000 : false;
    },
  });

  const products = useMemo(
    () => (productsQ.data?.pages || []).flatMap((pg) => pg.products || []),
    [productsQ.data],
  );
  const total = productsQ.data?.pages?.[0]?.total ?? 0;
  const totalImages = useMemo(
    () => products.reduce((s, p) => s + (p.image_count || 0), 0),
    [products],
  );
  const errorCount = useMemo(
    () => products.reduce((s, p) => s + (p.error_count || 0), 0),
    [products],
  );

  const rebuildMutation = useProductRedownloadMutation(token);
  const deleteProductMutation = useDeleteProductMutation(token);

  // Placeholder — Task 13 branche ici l'ouverture du drawer.
  const handleSelectImage = useCallback((img, product) => {
    setSelected({ image: img, product });
    console.log('[albums] selected image', product.id_produit, img.filename);
  }, []);

  const handleRebuild = useCallback(
    (p) => {
      rebuildMutation.mutate({ domain, productId: p.id_produit });
    },
    [domain, rebuildMutation],
  );

  const handleDelete = useCallback((p) => {
    setPendingProductDelete(p);
  }, []);

  if (productsQ.isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <RefreshCw className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-3 p-4">
      <AlbumHeader
        domain={domain}
        totalProducts={total}
        totalImages={totalImages}
        errorCount={errorCount}
        onRefresh={() => productsQ.refetch()}
        isRefetching={productsQ.isRefetching}
      />

      <AlbumToolbar
        q={q}
        onQ={setQ}
        filter={filter}
        onFilter={setFilter}
        sort={sort}
        onSort={setSort}
      />

      {products.length === 0 ? (
        <Card className="p-8 text-center text-muted-foreground">
          Pas encore de produits téléchargés pour ce domaine.
        </Card>
      ) : (
        <Card className="p-2">
          <AlbumProductList
            products={products}
            domain={domain}
            onSelectImage={handleSelectImage}
            onRebuild={handleRebuild}
            onDelete={handleDelete}
            onLoadMore={() => productsQ.fetchNextPage()}
            hasMore={!!productsQ.hasNextPage}
          />
        </Card>
      )}

      <DeleteImageOrProductDialog
        open={!!pendingProductDelete}
        kind="product"
        label={pendingProductDelete?.nom || pendingProductDelete?.id_produit || ''}
        busy={deleteProductMutation.isPending}
        onConfirm={async () => {
          try {
            await deleteProductMutation.mutateAsync({
              domain,
              productId: pendingProductDelete.id_produit,
            });
          } finally {
            setPendingProductDelete(null);
          }
        }}
        onCancel={() => setPendingProductDelete(null)}
      />
    </div>
  );
}
