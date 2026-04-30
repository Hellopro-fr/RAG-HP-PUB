import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Images, RefreshCw } from 'lucide-react';
import {
  useAlbumsQuery,
  useDeleteAlbumMutation,
  useAlbumDeleteJobQuery,
} from '../hooks/queries';
import { AlbumsToolbar } from '../components/albums/AlbumsToolbar';
import { AlbumsTable } from '../components/albums/AlbumsTable';
import { Card } from '../components/ui/card';
import ConfirmDestructive from '../components/ConfirmDestructive';
import { useToast } from '../components/ToastProvider';

/**
 * Page index `/albums` — listing virtualisé des domaines avec albums photo.
 *
 * Comportement :
 *  - `useAlbumsQuery` charge la liste complète (pas de pagination côté serveur).
 *  - Filtrage côté client : recherche substring + filtre rapide (errors / unsynced).
 *  - Tri ASC/DESC togglable sur chaque colonne.
 *  - Click ligne → /albums/:domain ; Trash → ConfirmDestructive (type-to-confirm).
 *  - Confirm → DELETE renvoie {job_id} ; on poll le job via useAlbumDeleteJobQuery
 *    et on émet des toasts (info au lancement, success/error sur transition).
 */
export default function AlbumsPage({ token }) {
  const navigate = useNavigate();
  const toast = useToast();
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState('all');
  const [sort, setSort] = useState('domain');
  const [pendingDelete, setPendingDelete] = useState(null);
  const [activeJobId, setActiveJobId] = useState(null);

  const { data, isLoading, refetch, isRefetching } = useAlbumsQuery(token);
  const deleteMutation = useDeleteAlbumMutation(token);
  const jobQ = useAlbumDeleteJobQuery(token, activeJobId);

  // Réagit aux transitions du job DELETE en cours : completed → success toast,
  // failed → error toast. Dans les deux cas on libère activeJobId pour stopper
  // le polling. La query est déjà invalidée par la mutation, donc la ligne
  // disparaît d'elle-même quand le job aboutit.
  useEffect(() => {
    const status = jobQ.data?.status;
    if (status === 'completed') {
      const dom = jobQ.data?.domain ?? '';
      toast.success(`Album "${dom}" supprimé`);
      setActiveJobId(null);
    } else if (status === 'failed') {
      const dom = jobQ.data?.domain ?? '';
      const err = jobQ.data?.error || 'erreur inconnue';
      toast.error(`Échec suppression "${dom}" — ${err}`);
      setActiveJobId(null);
    }
  }, [jobQ.data, toast]);

  const rows = useMemo(() => {
    const all = data?.domains || [];
    const needle = q.trim().toLowerCase();
    let r = all.filter(a => !needle || a.domain.toLowerCase().includes(needle));
    if (filter === 'errors')   r = r.filter(a => (a.error_count ?? 0) > 0);
    if (filter === 'unsynced') r = r.filter(a => (a.unsynced_count ?? 0) > 0);

    const desc = sort.endsWith('_desc');
    const key = desc ? sort.slice(0, -5) : sort;
    const dir = desc ? -1 : 1;
    return [...r].sort((a, b) => {
      const va = a[key];
      const vb = b[key];
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (va < vb) return -dir;
      if (va > vb) return dir;
      return 0;
    });
  }, [data, q, filter, sort]);

  const handleSort = (k) => setSort(prev => (prev === k ? `${k}_desc` : k));

  const handleResetFilters = () => {
    setQ('');
    setFilter('all');
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <RefreshCw className="h-8 w-8 animate-spin text-ink-3" />
      </div>
    );
  }

  const total = data?.total ?? (data?.domains?.length ?? 0);

  return (
    <div className="space-y-3 p-4">
      <header className="flex items-center justify-between">
        <h1 className="flex items-center gap-2 text-[26px] font-semibold tracking-[-0.025em] font-display text-ink-0">
          <Images className="h-5 w-5 text-ink-2" /> Albums
        </h1>
        <button
          type="button"
          className="flex items-center gap-1 text-xs text-ink-3 hover:text-ink-0 disabled:opacity-50"
          onClick={() => refetch()}
          disabled={isRefetching}
        >
          <RefreshCw className={`h-3 w-3 ${isRefetching ? 'animate-spin' : ''}`} /> Rafraîchir
        </button>
      </header>

      <AlbumsToolbar q={q} onQ={setQ} filter={filter} onFilter={setFilter} total={total} />

      {total === 0 ? (
        <Card className="p-8 text-center text-ink-3">Aucun album</Card>
      ) : rows.length === 0 ? (
        <Card className="p-8 text-center text-ink-3">
          Aucun résultat pour ces filtres.
          <button
            type="button"
            className="ml-2 underline hover:text-ink-0"
            onClick={handleResetFilters}
          >
            Réinitialiser
          </button>
        </Card>
      ) : (
        <Card className="overflow-hidden p-0">
          <AlbumsTable
            rows={rows}
            onSelectDomain={(d) => navigate(`/albums/${encodeURIComponent(d)}`)}
            onRequestDelete={setPendingDelete}
            sort={sort}
            onSort={handleSort}
          />
        </Card>
      )}

      {pendingDelete && (
        <ConfirmDestructive
          open
          title={`Supprimer l'album ${pendingDelete.domain}`}
          shortId={pendingDelete.domain}
          confirmWord="SUPPRIMER"
          description={
            <div className="space-y-2">
              <p>
                Cette action supprime <strong>définitivement</strong> :
              </p>
              <ul className="list-disc pl-5 text-sm">
                <li>{pendingDelete.product_count ?? 0} produits</li>
                <li>{pendingDelete.image_count ?? 0} images</li>
                {(pendingDelete.total_size_bytes ?? 0) > 0 && (
                  <li>
                    {((pendingDelete.total_size_bytes ?? 0) / (1024 * 1024)).toFixed(1)} MB
                  </li>
                )}
              </ul>
              <p className="text-xs text-ink-3">
                Le job s&apos;exécute en arrière-plan ; tu peux fermer cette page.
              </p>
            </div>
          }
          busy={deleteMutation.isPending}
          onConfirm={async () => {
            const domain = pendingDelete.domain;
            const productCount = pendingDelete.product_count ?? 0;
            try {
              const resp = await deleteMutation.mutateAsync({ domain });
              const jobId = resp?.job_id;
              if (jobId) {
                setActiveJobId(jobId);
                toast.info(
                  `Suppression de "${domain}" lancée — ${productCount} produits`,
                );
              }
            } catch (err) {
              toast.error(
                `Lancement suppression "${domain}" échoué — ${err?.message || 'erreur inconnue'}`,
              );
            } finally {
              setPendingDelete(null);
            }
          }}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </div>
  );
}
