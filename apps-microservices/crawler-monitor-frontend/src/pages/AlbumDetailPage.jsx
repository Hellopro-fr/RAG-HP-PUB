import { useMemo, useState, useCallback, useEffect } from 'react';
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
import { ImageDetailSheet } from '../components/albums/ImageDetailSheet';
import { Card } from '../components/ui/card';
import { useToast } from '../components/ToastProvider';

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
  const toast = useToast();

  const [q, setQ] = useState('');
  const [filter, setFilter] = useState('all');
  const [sort, setSort] = useState('updated');
  const [pendingProductDelete, setPendingProductDelete] = useState(null);
  const [selected, setSelected] = useState(null);

  // Mode d'affichage des images (stack/coverflow/reel/dial). Persisté en
  // localStorage pour que l'utilisateur retrouve son mode préféré au refresh.
  // Default = `coverflow` (cf. handoff design — README §"Default mode").
  const [imageMode, setImageMode] = useState(() => {
    try {
      return localStorage.getItem('albumImageMode') || 'coverflow';
    } catch {
      return 'coverflow';
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem('albumImageMode', imageMode);
    } catch {
      /* ignore quota errors */
    }
  }, [imageMode]);

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

  // Click sur une vignette → ouvre le drawer (Task 13). On stocke à la fois
  // l'image et son produit parent pour les afficher dans le `ImageDetailSheet`.
  const handleSelectImage = useCallback((img, product) => {
    setSelected({ image: img, product });
  }, []);

  const handleRebuild = useCallback(
    async (p) => {
      const label = p.nom || `#${p.id_produit}`;
      try {
        const res = await rebuildMutation.mutateAsync({
          domain, productId: p.id_produit,
        });
        const dl = res?.downloaded ?? 0;
        const fl = res?.failed ?? 0;
        const sk = res?.skipped ?? 0;
        const total = dl + fl + sk;
        if (fl === 0 && sk === 0) {
          toast.success(`${label} : ${dl}/${total} images re-téléchargées`);
        } else if (dl > 0) {
          toast.warn(`${label} : ${dl} ok · ${fl} échec · ${sk} skip`);
        } else {
          toast.error(`${label} : aucun re-téléchargement (${fl} échec · ${sk} skip)`);
        }
      } catch (err) {
        // Distinction utile : 422 manifest legacy v1 vs autres erreurs
        const status = err?.status;
        const body = err?.body;
        const detail = (typeof body === 'object' && body?.detail) || err?.message || 'erreur inconnue';
        if (status === 422 && /legacy v1/i.test(String(detail))) {
          toast.error(
            `${label} : manifest v1 — re-ingérer côté BO pour migrer en v2`,
            { durationMs: 8000 },
          );
        } else {
          toast.error(`Rebuild ${label} échoué — ${detail}`);
        }
      }
    },
    [domain, rebuildMutation, toast],
  );

  const handleDelete = useCallback((p) => {
    setPendingProductDelete(p);
  }, []);

  if (productsQ.isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <RefreshCw className="h-8 w-8 animate-spin text-ink-3" />
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
        imageMode={imageMode}
        onImageMode={setImageMode}
      />

      {products.length === 0 ? (
        <Card className="p-8 text-center text-ink-3">
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
            imageMode={imageMode}
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

      <ImageDetailSheet
        open={!!selected}
        image={selected?.image}
        product={selected?.product}
        domain={domain}
        onClose={() => setSelected(null)}
        token={token}
      />
    </div>
  );
}
