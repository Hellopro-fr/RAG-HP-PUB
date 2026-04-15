import { useState, useEffect } from 'react';
import {
  Server, XCircle, RefreshCw, AlertTriangle, Trash2, CheckCircle
} from 'lucide-react';
import { API_URL } from '../lib/constants';
import ConfirmDestructive from './ConfirmDestructive';

const DatasetAnalyzer = ({ jobId, onClose, token }) => {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [purging, setPurging] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const authFetch = async (url, options = {}) => {
    const headers = { ...options.headers, 'Authorization': `Bearer ${token}` };
    const res = await fetch(url, { ...options, headers });
    if (!res.ok) throw new Error('Request failed');
    return res;
  };

  const analyzeDataset = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch(`${API_URL}/jobs/${jobId}/dataset/analyze`);
      const data = await res.json();
      setStats(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const [showPurgeConfirm, setShowPurgeConfirm] = useState(false);

  const performPurge = async () => {
    setPurging(true);
    setError(null);
    try {
      const res = await authFetch(`${API_URL}/jobs/${jobId}/dataset/deduplicate`, { method: 'POST' });
      const data = await res.json();
      setSuccess(`Opération réussie: ${data.removedCount} fichiers supprimés.`);
      analyzeDataset(); // Refresh stats
      setShowPurgeConfirm(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setPurging(false);
    }
  };

  const purgeDuplicates = () => setShowPurgeConfirm(true);

  useEffect(() => {
    analyzeDataset();
  }, [jobId]);

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
      <ConfirmDestructive
        open={showPurgeConfirm}
        title="Purge duplicates"
        description={
          <>
            Va supprimer <strong>{stats?.duplicateCount || 0}</strong> fichier{(stats?.duplicateCount || 0) > 1 ? 's' : ''} doublon
            pour le job <code className="text-orange-300">{jobId}</code>.
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
      <div className="bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl overflow-hidden">
        <div className="flex justify-between items-center p-4 border-b border-gray-700 bg-gray-750">
          <h3 className="text-xl font-bold text-white flex items-center gap-2">
            <Server className="w-5 h-5 text-purple-400" /> Analyse Dataset
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-white">
            <XCircle className="w-6 h-6" />
          </button>
        </div>

        <div className="p-6">
          {loading && !stats ? (
            <div className="flex justify-center py-12">
              <RefreshCw className="w-8 h-8 animate-spin text-blue-500" />
            </div>
          ) : stats ? (
            <div className="space-y-6">
              <div className="grid grid-cols-3 gap-4">
                <div className="bg-gray-700 p-4 rounded-lg text-center">
                  <p className="text-gray-400 text-sm">Total Items</p>
                  <p className="text-2xl font-bold text-white">{stats.totalItems}</p>
                </div>
                <div className="bg-gray-700 p-4 rounded-lg text-center">
                  <p className="text-gray-400 text-sm">URLs Uniques</p>
                  <p className="text-2xl font-bold text-green-400">{stats.uniqueUrls}</p>
                </div>
                <div className="bg-gray-700 p-4 rounded-lg text-center border border-red-500/30">
                  <p className="text-gray-400 text-sm">Doublons</p>
                  <p className="text-2xl font-bold text-red-400">{stats.duplicateCount}</p>
                </div>
              </div>

              {stats.duplicateCount > 0 ? (
                <div className="bg-red-900/20 border border-red-500/50 p-4 rounded-lg">
                  <h4 className="font-bold text-red-400 mb-2 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4" /> Doublons détectés
                  </h4>
                  <p className="text-sm text-gray-300 mb-4">
                    Le dataset contient <strong>{stats.duplicateCount}</strong> entrées en double.
                    Cela arrive souvent après une reprise de crawl ("resume") suite à un arrêt d'urgence.
                  </p>
                  <div className="flex gap-3">
                    <button
                      onClick={purgeDuplicates}
                      disabled={purging}
                      className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded font-medium flex items-center gap-2 transition-colors disabled:opacity-50"
                    >
                      {purging ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                      Purger les doublons
                    </button>
                  </div>
                </div>
              ) : (
                <div className="bg-green-900/20 border border-green-500/30 p-4 rounded-lg flex items-center gap-3">
                  <CheckCircle className="w-6 h-6 text-green-400" />
                  <span className="text-green-300 font-medium">Le dataset est propre. Aucun doublon détecté.</span>
                </div>
              )}

              {stats.duplicatesExample && stats.duplicatesExample.length > 0 && (
                <div className="bg-gray-900 p-4 rounded-lg font-mono text-xs text-gray-400">
                  <p className="mb-2 uppercase text-gray-500">Exemples de doublons :</p>
                  <ul className="list-disc pl-4 space-y-1">
                    {stats.duplicatesExample.map((url, i) => (
                      <li key={i}>{url}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <div className="bg-red-900/20 p-4 text-red-400 rounded">
              Erreur impossible de charger les stats. {error}
            </div>
          )}

          {success && (
            <div className="mt-4 bg-green-900/30 text-green-400 p-3 rounded flex items-center gap-2">
              <CheckCircle className="w-4 h-4" /> {success}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default DatasetAnalyzer;