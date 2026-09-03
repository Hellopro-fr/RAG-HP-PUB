import { useState, useEffect, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft, RefreshCw, RotateCcw, Trash2, AlertCircle, CheckCircle, Mail,
} from 'lucide-react';
import { api } from '../lib/api';
import ConfirmDestructive from './ConfirmDestructive';
import { Card } from './ui/card';
import { Button } from './ui/button';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from './ui/table';
import { formatApiDate } from '../lib/dates';
import { queryKeys } from '../hooks/queries';
import { cn } from '../lib/utils';

const typeBadgeClass = (type) => {
  switch (type) {
    case 'success': return 'bg-ok-soft text-ok';
    case 'failure': return 'bg-err-soft text-err';
    case 'stop':    return 'bg-warn-soft text-warn';
    default:        return 'bg-bg-2 text-ink-3';
  }
};

const truncate = (s, n = 50) => {
  if (!s) return '';
  return s.length > n ? s.slice(0, n - 1) + '…' : s;
};

/* Clé React stable : l'index de liste change dès qu'une entrée est supprimée,
   ce qui réattribuait l'état de ligne (spinner « retry en cours ») au mauvais
   callback. url + timestamp identifie une entrée de façon stable. */
const entryKey = (entry, idx) =>
  entry?.url || entry?.timestamp
    ? `${entry.url ?? ''}|${entry.timestamp ?? ''}`
    : `idx-${idx}`;

const CallbacksPanel = ({ token, onClose }) => {
  const queryClient = useQueryClient();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [busyIndex, setBusyIndex] = useState(null);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [clearing, setClearing] = useState(false);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get('/callbacks', token);
      setItems(data.items || []);
    } catch (err) {
      setError(`Erreur de chargement : ${err.message}`);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { fetchItems(); }, [fetchItems]);

  /* Le badge « callbacks en échec » de la sidebar est alimenté par la query
     ['callbacks'] : sans invalidation, il reste figé sur l'ancien compte après
     un retry / delete / clear. */
  const invalidateCallbacks = useCallback(() => {
    // queryKeys.callbacks() plutôt qu'un littéral : la clé n'a qu'une seule
    // définition (hooks/queries), sans quoi un renommage laisserait ce badge
    // silencieusement figé.
    queryClient.invalidateQueries({ queryKey: queryKeys.callbacks() });
  }, [queryClient]);

  const retryItem = async (index) => {
    setBusyIndex(`retry-${index}`);
    setError(null);
    setSuccess(null);
    try {
      // Le backend répond 200 avec { success: false } quand la relance échoue
      // côté destinataire : ce n'est pas une exception, il faut le lire.
      const data = await api.post(`/callbacks/${index}/retry`, token);
      if (data && data.success) {
        setSuccess(`Callback #${index} relancé avec succès (${data.status}).`);
      } else {
        setError(`Échec retry #${index} : ${(data && data.error) || 'inconnu'}`);
      }
      await fetchItems();
      invalidateCallbacks();
    } catch (err) {
      const msg = err.body && err.body.error ? err.body.error : err.message;
      setError(`Échec retry #${index} : ${msg}`);
      await fetchItems();
      invalidateCallbacks();
    } finally {
      setBusyIndex(null);
    }
  };

  const deleteItem = async (index) => {
    if (!window.confirm(`Supprimer le callback #${index} de la liste ?`)) return;
    setBusyIndex(`delete-${index}`);
    setError(null);
    setSuccess(null);
    try {
      const data = await api.delete(`/callbacks/${index}`, token);
      if (data && data.success === false) {
        setError(`Erreur suppression : ${data.error || 'inconnu'}`);
      } else {
        setSuccess(`Callback #${index} supprimé.`);
      }
      await fetchItems();
      invalidateCallbacks();
    } catch (err) {
      setError(`Erreur suppression : ${err.message}`);
      // La suppression a pu aboutir côté serveur avant l'erreur (timeout de
      // lecture) : on resynchronise la liste ET le badge, comme dans retryItem.
      await fetchItems();
      invalidateCallbacks();
    } finally {
      setBusyIndex(null);
    }
  };

  const performClearAll = async () => {
    setClearing(true);
    setError(null);
    setSuccess(null);
    try {
      const data = await api.post('/callbacks/clear', token);
      if (data && data.success === false) {
        setError(`Erreur clear : ${data.error || 'inconnu'}`);
      } else {
        setSuccess(`Liste vidée (${(data && data.cleared) || 0} entrées).`);
      }
      setShowClearConfirm(false);
      await fetchItems();
      invalidateCallbacks();
    } catch (err) {
      setError(`Erreur clear : ${err.message}`);
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="p-4">
      <ConfirmDestructive
        open={showClearConfirm}
        title="Clear all callbacks"
        description={
          <>
            Va supprimer <strong>{items.length}</strong> callback{items.length > 1 ? 's' : ''} en échec
            de la liste Redis. Aucune relance ne sera tentée — utilise <em>Retry all</em> avant si tu veux ré-essayer.
            <br /><br />
            Cette action est <strong>irréversible</strong>.
          </>
        }
        shortId="callbacks"
        onConfirm={performClearAll}
        onCancel={() => setShowClearConfirm(false)}
        busy={clearing}
      />

      <Card className="overflow-hidden">
        <div className="flex items-center justify-between border-b border-hairline p-4">
          <h3 className="flex items-center gap-2 text-base font-semibold">
            <Mail className="h-4 w-4 text-err" />
            Callbacks en échec
            <span className="font-mono text-xs font-normal text-ink-3">
              ({items.length})
            </span>
          </h3>
          <div className="flex items-center gap-2">
            {onClose && (
              <Button variant="outline" size="sm" onClick={onClose}>
                <ArrowLeft className="h-4 w-4" />
                Retour
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon"
              onClick={fetchItems}
              disabled={loading}
              title="Rafraîchir"
            >
              <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
            </Button>
            {items.length > 0 && (
              <Button
                variant="destructive"
                size="sm"
                onClick={() => setShowClearConfirm(true)}
              >
                <Trash2 className="h-4 w-4" />
                Tout supprimer ({items.length})
              </Button>
            )}
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 border-b border-err/40 bg-err-soft px-4 py-2 text-sm text-err">
            <AlertCircle className="h-4 w-4" /> {error}
          </div>
        )}
        {success && (
          <div className="flex items-center gap-2 border-b border-ok/40 bg-ok-soft px-4 py-2 text-sm text-ok">
            <CheckCircle className="h-4 w-4" /> {success}
          </div>
        )}

        <div className="max-h-[75vh] overflow-auto">
          {loading && items.length === 0 ? (
            <div className="flex items-center justify-center py-20">
              <RefreshCw className="h-6 w-6 animate-spin text-accent" />
            </div>
          ) : items.length === 0 ? (
            <div className="py-20 text-center text-ink-3">
              <CheckCircle className="mx-auto mb-3 h-12 w-12 text-ok/60" />
              <p className="text-base">Aucun callback en échec — tout est OK ✓</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Quand</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Crawl</TableHead>
                  <TableHead>URL</TableHead>
                  <TableHead>Erreur</TableHead>
                  <TableHead className="text-right">Relances</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((entry, idx) => {
                  const isRetrying = busyIndex === `retry-${idx}`;
                  const isDeleting = busyIndex === `delete-${idx}`;
                  const ts = formatApiDate(entry.timestamp, { dateStyle: 'short', timeStyle: 'medium' });
                  return (
                    <TableRow key={entryKey(entry, idx)}>
                      <TableCell className="whitespace-nowrap font-mono text-xs text-ink-3">{ts}</TableCell>
                      <TableCell>
                        <span className={cn('rounded px-1.5 py-0.5 text-[10px]', typeBadgeClass(entry.webhook_type))}>
                          {entry.webhook_type || 'unknown'}
                        </span>
                      </TableCell>
                      <TableCell className="font-mono text-xs">{truncate(entry.crawl_id, 16)}</TableCell>
                      <TableCell title={entry.url} className="font-mono text-xs">
                        {truncate(entry.url, 50)}
                      </TableCell>
                      <TableCell
                        className="text-xs text-err/90"
                        title={entry.error || entry.last_manual_retry_error || ''}
                      >
                        {truncate(entry.last_manual_retry_error || entry.error, 40)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-ink-3">
                        {entry.manual_retry_attempts || 0}
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-right">
                        <Button
                          size="sm"
                          className="mr-1 h-7 px-2"
                          onClick={() => retryItem(idx)}
                          disabled={busyIndex !== null}
                          title="Rejouer le webhook"
                        >
                          {isRetrying
                            ? <RefreshCw className="h-3 w-3 animate-spin" />
                            : <RotateCcw className="h-3 w-3" />}
                          Retry
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 hover:bg-err hover:text-err-foreground"
                          onClick={() => deleteItem(idx)}
                          disabled={busyIndex !== null}
                          title="Supprimer cette entrée"
                        >
                          {isDeleting
                            ? <RefreshCw className="h-3 w-3 animate-spin" />
                            : <Trash2 className="h-3 w-3" />}
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </div>

        <div className="border-t border-hairline p-3 text-[11px] text-ink-3">
          Les actions Retry / Delete / Clear sont tracées dans l&apos;audit log.
        </div>
      </Card>
    </div>
  );
};

export default CallbacksPanel;
