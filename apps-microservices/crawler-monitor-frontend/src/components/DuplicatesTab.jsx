import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, AlertTriangle, Trash2, CheckCircle, AlertCircle } from 'lucide-react';
import { api } from '../lib/api';
import ConfirmDestructive from './ConfirmDestructive';
import { Card } from './ui/card';
import { Button } from './ui/button';
import { cn } from '../lib/utils';

/**
 * Duplicates analysis tab inside the Dataset page.
 */
const DuplicatesTab = ({ jobId, token }) => {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [purging, setPurging] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [showPurgeConfirm, setShowPurgeConfirm] = useState(false);

  const analyze = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get(`/jobs/${jobId}/dataset/analyze`, token);
      setStats(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [jobId, token]);

  const performPurge = async () => {
    setPurging(true);
    setError(null);
    try {
      const data = await api.post(`/jobs/${jobId}/dataset/deduplicate`, token);
      setSuccess(`Opération réussie: ${data.removedCount} fichiers supprimés.`);
      analyze();
      setShowPurgeConfirm(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setPurging(false);
    }
  };

  useEffect(() => { analyze(); }, [analyze]);

  if (loading && !stats) {
    return (
      <div className="flex justify-center py-12">
        <RefreshCw className="h-6 w-6 animate-spin text-accent" />
      </div>
    );
  }
  if (!stats) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-err/40 bg-err-soft p-4 text-sm text-err">
        <AlertCircle className="h-4 w-4" />
        Erreur impossible de charger les stats. {error}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <ConfirmDestructive
        open={showPurgeConfirm}
        title="Purge duplicates"
        description={
          <>
            Va supprimer <strong>{stats.duplicateCount || 0}</strong> fichier{(stats.duplicateCount || 0) > 1 ? 's' : ''} doublon
            pour le job <code className="rounded bg-bg-2 px-1 py-0.5 text-warn">{jobId}</code>.
            <br /><br />
            Le dataset garde la copie la plus récente de chaque URL.
            Cette action est <strong>irréversible</strong>.
          </>
        }
        shortId={String(jobId).slice(0, 8)}
        onConfirm={performPurge}
        onCancel={() => setShowPurgeConfirm(false)}
        busy={purging}
      />

      <div className="grid grid-cols-3 gap-3">
        <StatTile label="Total Items" value={stats.totalItems} />
        <StatTile label="URLs Uniques" value={stats.uniqueUrls} valueClass="text-ok" />
        <StatTile
          label="Doublons"
          value={stats.duplicateCount}
          valueClass="text-err"
          cardClass="border-err/40"
        />
      </div>

      {stats.duplicateCount > 0 ? (
        <Card className="border-err/40 bg-err-soft p-4">
          <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold text-err">
            <AlertTriangle className="h-4 w-4" /> Doublons détectés
          </h4>
          <p className="mb-4 text-sm text-ink-0/80">
            Le dataset contient <strong>{stats.duplicateCount}</strong> entrées en double.
            Cela arrive souvent après une reprise de crawl (&quot;resume&quot;) suite à un arrêt d&apos;urgence.
          </p>
          <Button
            variant="destructive"
            onClick={() => setShowPurgeConfirm(true)}
            disabled={purging}
          >
            {purging ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
            Purger les doublons
          </Button>
        </Card>
      ) : (
        <div className="flex items-center gap-3 rounded-md border border-ok/40 bg-ok-soft p-4">
          <CheckCircle className="h-5 w-5 text-ok" />
          <span className="font-medium text-ok">Le dataset est propre. Aucun doublon détecté.</span>
        </div>
      )}

      {stats.duplicatesExample && stats.duplicatesExample.length > 0 && (
        <Card className="bg-bg-1 p-4">
          <p className="mb-2 text-[10px] uppercase tracking-wider text-ink-3">
            Exemples de doublons :
          </p>
          <ul className="list-disc space-y-1 pl-4 font-mono text-xs text-ink-3">
            {stats.duplicatesExample.map((url, i) => <li key={i}>{url}</li>)}
          </ul>
        </Card>
      )}

      {success && (
        <div className="flex items-center gap-2 rounded-md border border-ok/40 bg-ok-soft p-3 text-sm text-ok">
          <CheckCircle className="h-4 w-4" /> {success}
        </div>
      )}
    </div>
  );
};

const StatTile = ({ label, value, valueClass = 'text-ink-0', cardClass }) => (
  <Card className={cn('p-4 text-center', cardClass)}>
    <p className="text-xs uppercase tracking-wider text-ink-3">{label}</p>
    <p className={cn('font-mono text-2xl font-bold', valueClass)}>{value}</p>
  </Card>
);

export default DuplicatesTab;
