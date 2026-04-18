import { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw, RotateCcw, Trash2, AlertCircle, CheckCircle, Mail,
} from 'lucide-react';
import { api } from '../lib/api';
import ConfirmDestructive from './ConfirmDestructive';
import { Card } from './ui/card';
import { Button } from './ui/button';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from './ui/table';
import { cn } from '../lib/utils';

const typeBadgeClass = (type) => {
  switch (type) {
    case 'success': return 'bg-success/15 text-success';
    case 'failure': return 'bg-destructive/15 text-destructive';
    case 'stop':    return 'bg-warning/15 text-warning';
    default:        return 'bg-muted text-muted-foreground';
  }
};

const truncate = (s, n = 50) => {
  if (!s) return '';
  return s.length > n ? s.slice(0, n - 1) + '…' : s;
};

const CallbacksPanel = ({ token, onClose }) => {
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

  const retryItem = async (index) => {
    setBusyIndex(`retry-${index}`);
    setError(null);
    setSuccess(null);
    try {
      const data = await api.post(`/callbacks/${index}/retry`, token);
      if (data && data.success) {
        setSuccess(`Callback #${index} relancé avec succès (${data.status}).`);
      } else {
        setError(`Échec retry #${index} : ${(data && data.error) || 'inconnu'}`);
      }
      await fetchItems();
    } catch (err) {
      const msg = err.body && err.body.error ? err.body.error : err.message;
      setError(`Échec retry #${index} : ${msg}`);
      await fetchItems();
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
      await api.delete(`/callbacks/${index}`, token);
      setSuccess(`Callback #${index} supprimé.`);
      await fetchItems();
    } catch (err) {
      setError(`Erreur suppression : ${err.message}`);
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
      setSuccess(`Liste vidée (${(data && data.cleared) || 0} entrées).`);
      setShowClearConfirm(false);
      await fetchItems();
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
        <div className="flex items-center justify-between border-b border-border p-4">
          <h3 className="flex items-center gap-2 text-base font-semibold">
            <Mail className="h-4 w-4 text-destructive" />
            Callbacks en échec
            <span className="font-mono text-xs font-normal text-muted-foreground">
              ({items.length})
            </span>
          </h3>
          <div className="flex items-center gap-2">
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
          <div className="flex items-center gap-2 border-b border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" /> {error}
          </div>
        )}
        {success && (
          <div className="flex items-center gap-2 border-b border-success/40 bg-success/10 px-4 py-2 text-sm text-success">
            <CheckCircle className="h-4 w-4" /> {success}
          </div>
        )}

        <div className="max-h-[75vh] overflow-auto">
          {loading && items.length === 0 ? (
            <div className="flex items-center justify-center py-20">
              <RefreshCw className="h-6 w-6 animate-spin text-primary" />
            </div>
          ) : items.length === 0 ? (
            <div className="py-20 text-center text-muted-foreground">
              <CheckCircle className="mx-auto mb-3 h-12 w-12 text-success/60" />
              <p className="text-base">Aucun callback en échec — tout est OK ✓</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Crawl</TableHead>
                  <TableHead>URL</TableHead>
                  <TableHead>Error</TableHead>
                  <TableHead className="text-right">Retries</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((entry, idx) => {
                  const isRetrying = busyIndex === `retry-${idx}`;
                  const isDeleting = busyIndex === `delete-${idx}`;
                  const ts = entry.timestamp ? new Date(entry.timestamp).toLocaleString('fr-FR') : '—';
                  return (
                    <TableRow key={idx}>
                      <TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">{ts}</TableCell>
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
                        className="text-xs text-destructive/90"
                        title={entry.error || entry.last_manual_retry_error || ''}
                      >
                        {truncate(entry.last_manual_retry_error || entry.error, 40)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-muted-foreground">
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
                          className="h-7 w-7 hover:bg-destructive hover:text-destructive-foreground"
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

        <div className="border-t border-border p-3 text-[11px] text-muted-foreground">
          Les actions Retry / Delete / Clear sont tracées dans l&apos;audit log.
        </div>
      </Card>
    </div>
  );
};

export default CallbacksPanel;
