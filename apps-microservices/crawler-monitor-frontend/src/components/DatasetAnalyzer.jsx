// src/components/DatasetAnalyzer.jsx
import { useCallback, useEffect, useState } from 'react';
import { Server, XCircle, RefreshCw } from 'lucide-react';
import { api } from '../lib/api';
import UrlListBrowser from './UrlListBrowser';
import DuplicatesTab from './DuplicatesTab';

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
 * Tab switch unmounts the previous tab (simple + predictable for v1).
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
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-800 rounded-lg shadow-xl w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden">
        <div className="flex justify-between items-center p-4 border-b border-gray-700">
          <h3 className="text-xl font-bold text-white flex items-center gap-2">
            <Server className="w-5 h-5 text-purple-400" /> Analyse Dataset
            {countsLoading && <RefreshCw className="w-4 h-4 animate-spin text-gray-400" />}
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-white" aria-label="Fermer">
            <XCircle className="w-6 h-6" />
          </button>
        </div>

        {/* Tabs */}
        <nav className="flex gap-1 px-4 pt-3 border-b border-gray-700 bg-gray-800" role="tablist">
          {TABS.map(t => {
            const isActive = activeTab === t.id;
            const countLabel =
              t.kind === 'urls' && counts ? ` (${formatInt(counts[t.id])})` : '';
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setActiveTab(t.id)}
                role="tab"
                aria-selected={isActive}
                className={
                  'px-4 py-2 text-sm rounded-t-md transition-colors ' +
                  (isActive
                    ? 'bg-gray-900 text-white border border-b-0 border-gray-700'
                    : 'text-gray-400 hover:text-white hover:bg-gray-700/50')
                }
              >
                {t.label}{countLabel}
              </button>
            );
          })}
        </nav>

        {countsError && (
          <div className="mx-4 mt-3 bg-red-900/20 border border-red-500/50 text-red-300 p-3 rounded text-sm flex items-center justify-between gap-3">
            <span>Impossible de charger les comptes. {countsError}</span>
            <button onClick={fetchCounts} className="underline text-red-200 hover:text-white text-xs">
              Réessayer
            </button>
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-6">
          {activeTab === 'duplicates'
            ? <DuplicatesTab jobId={jobId} token={token} />
            : <UrlListBrowser jobId={jobId} category={activeTab} token={token} />}
        </div>
      </div>
    </div>
  );
};

export default DatasetAnalyzer;
