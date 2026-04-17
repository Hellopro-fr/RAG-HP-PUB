import { useCallback, useEffect, useState } from 'react';
import { Server, RefreshCw, AlertCircle, ArrowLeft } from 'lucide-react';
import { api } from '../lib/api';
import UrlListBrowser from './UrlListBrowser';
import DuplicatesTab from './DuplicatesTab';
import { Card } from './ui/card';
import { Tabs, TabsList, TabsTrigger, TabsContent } from './ui/tabs';
import { Button } from './ui/button';

const TABS = [
  { id: 'success',    label: 'Succès',   kind: 'urls' },
  { id: 'error',      label: 'Erreurs',  kind: 'urls' },
  { id: 'nfr',        label: 'Non-FR',   kind: 'urls' },
  { id: 'duplicates', label: 'Doublons', kind: 'duplicates' },
];

const formatInt = (n) => (n ?? 0).toLocaleString('fr-FR');

/**
 * Tabbed dataset page.
 *   - Succès / Erreurs / Non-FR → <UrlListBrowser category={...} />
 *   - Doublons                   → <DuplicatesTab />
 *
 * Counts are fetched on mount via /dataset/counts and displayed in tab labels.
 */
const DatasetAnalyzer = ({ jobId, onClose, token }) => {
  const [activeTab, setActiveTab] = useState('success');
  const [counts, setCounts] = useState(null);
  const [countsLoading, setCountsLoading] = useState(false);
  const [countsError, setCountsError] = useState(null);

  const fetchCounts = useCallback(async () => {
    setCountsLoading(true);
    setCountsError(null);
    try {
      const data = await api.get(`/jobs/${jobId}/dataset/counts`, token);
      setCounts(data);
    } catch (err) {
      setCountsError(err.message);
    } finally {
      setCountsLoading(false);
    }
  }, [jobId, token]);

  useEffect(() => { fetchCounts(); }, [fetchCounts]);

  return (
    <div className="p-4">
      <Card className="overflow-hidden">
        <div className="flex items-center justify-between border-b border-border p-4">
          <h3 className="flex items-center gap-2 text-base font-semibold">
            <Server className="h-4 w-4 text-primary" />
            Analyse Dataset
            <span className="font-mono text-xs font-normal text-muted-foreground">
              #{String(jobId).slice(0, 10)}
            </span>
            {countsLoading && <RefreshCw className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
          </h3>
          {onClose && (
            <Button variant="outline" size="sm" onClick={onClose}>
              <ArrowLeft className="h-4 w-4" />
              Retour au job
            </Button>
          )}
        </div>

        {countsError && (
          <div className="flex items-center justify-between gap-3 border-b border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-destructive">
            <span className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4" />
              Impossible de charger les comptes. {countsError}
            </span>
            <Button variant="ghost" size="sm" onClick={fetchCounts}>
              Réessayer
            </Button>
          </div>
        )}

        <Tabs value={activeTab} onValueChange={setActiveTab} className="p-4">
          <TabsList>
            {TABS.map(t => {
              const countLabel = t.kind === 'urls' && counts ? ` (${formatInt(counts[t.id])})` : '';
              return (
                <TabsTrigger key={t.id} value={t.id}>
                  {t.label}{countLabel}
                </TabsTrigger>
              );
            })}
          </TabsList>

          {TABS.map(t => (
            <TabsContent key={t.id} value={t.id} className="mt-4">
              {t.kind === 'duplicates'
                ? <DuplicatesTab jobId={jobId} token={token} />
                : <UrlListBrowser jobId={jobId} category={t.id} token={token} />}
            </TabsContent>
          ))}
        </Tabs>
      </Card>
    </div>
  );
};

export default DatasetAnalyzer;
