import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Globe, RefreshCw, AlertCircle, Search,
} from 'lucide-react';
import { useDomainsQuery } from '../hooks/queries';

const WINDOW_OPTIONS = ['24h', '7d', '30d'];

const DomainsPage = ({ token }) => {
  const navigate = useNavigate();
  const [window, setWindow] = useState('7d');
  const [search, setSearch] = useState('');
  const query = useDomainsQuery(token, window);

  const all = query.data?.domains || [];
  const filtered = search
    ? all.filter(d => d.domain.toLowerCase().includes(search.toLowerCase()))
    : all;

  const fmtPct = (v) => v == null ? '—' : `${(v * 100).toFixed(1)}%`;
  const fmtDate = (s) => s ? new Date(s).toLocaleString('fr-FR') : '—';

  const successColor = (rate) => {
    if (rate == null) return 'text-gray-500';
    if (rate >= 0.9) return 'text-green-400';
    if (rate >= 0.7) return 'text-yellow-400';
    return 'text-red-400';
  };

  return (
    <main className="container mx-auto p-4 space-y-4">
      <div className="bg-gray-800 rounded-lg shadow-xl">
        <div className="flex justify-between items-center p-4 border-b border-gray-700 flex-wrap gap-2">
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <Globe className="w-5 h-5 text-blue-400" /> Domains
            <span className="text-sm font-normal text-gray-400">
              ({filtered.length}{filtered.length !== all.length ? ` / ${all.length}` : ''})
            </span>
          </h2>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
              <input
                type="text"
                placeholder="Filtrer..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="bg-gray-900 border border-gray-700 rounded pl-8 pr-3 py-1 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
            </div>
            <div className="flex gap-1 bg-gray-900 p-1 rounded">
              {WINDOW_OPTIONS.map(w => (
                <button
                  key={w}
                  onClick={() => setWindow(w)}
                  className={`px-2 py-0.5 text-xs rounded transition-colors ${
                    w === window ? 'bg-blue-600 text-white' : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                  }`}
                >
                  {w}
                </button>
              ))}
            </div>
            <button
              onClick={() => query.refetch()}
              disabled={query.isFetching}
              className="p-2 rounded hover:bg-gray-700 disabled:opacity-50"
              title="Rafraîchir"
            >
              <RefreshCw className={`w-4 h-4 ${query.isFetching ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {query.isError && (
          <div className="px-4 py-2 bg-red-900/40 border-b border-red-700/50 text-red-300 text-sm flex items-center gap-2">
            <AlertCircle className="w-4 h-4" /> {query.error?.message || 'Erreur de chargement'}
          </div>
        )}

        <div className="overflow-auto max-h-[75vh]">
          {query.isLoading && all.length === 0 ? (
            <div className="flex items-center justify-center py-16">
              <RefreshCw className="w-8 h-8 animate-spin text-blue-400" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-16 text-gray-400">
              <Globe className="w-12 h-12 mx-auto mb-3 opacity-40" />
              <p>{search ? `Aucun domaine ne correspond à "${search}".` : 'Aucun domaine sur la période.'}</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-900 sticky top-0">
                <tr className="text-left text-gray-400 text-xs uppercase">
                  <th className="px-3 py-2">Domain</th>
                  <th className="px-3 py-2 text-right">Jobs</th>
                  <th className="px-3 py-2 text-right">✓</th>
                  <th className="px-3 py-2 text-right">✗</th>
                  <th className="px-3 py-2 text-right">▶</th>
                  <th className="px-3 py-2 text-right">OOM</th>
                  <th className="px-3 py-2 text-right">Success rate</th>
                  <th className="px-3 py-2 text-right">Update %</th>
                  <th className="px-3 py-2">Last run</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(d => (
                  <tr
                    key={d.domain}
                    onClick={() => navigate(`/domains/${encodeURIComponent(d.domain)}`)}
                    className="border-t border-gray-700 hover:bg-gray-700/30 cursor-pointer"
                  >
                    <td className="px-3 py-2 text-white font-mono">{d.domain}</td>
                    <td className="px-3 py-2 text-right text-gray-300">{d.total_jobs}</td>
                    <td className="px-3 py-2 text-right text-green-400">{d.success || ''}</td>
                    <td className="px-3 py-2 text-right text-red-400">{d.failure || ''}</td>
                    <td className="px-3 py-2 text-right text-blue-400">{d.running || ''}</td>
                    <td className="px-3 py-2 text-right text-orange-400">{d.oom_total || ''}</td>
                    <td className={`px-3 py-2 text-right font-semibold ${successColor(d.success_rate)}`}>
                      {fmtPct(d.success_rate)}
                    </td>
                    <td className="px-3 py-2 text-right text-purple-400">
                      {d.update_share > 0 ? `${(d.update_share * 100).toFixed(0)}%` : ''}
                    </td>
                    <td className="px-3 py-2 text-gray-400 text-xs whitespace-nowrap">{fmtDate(d.last_run_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </main>
  );
};

export default DomainsPage;
