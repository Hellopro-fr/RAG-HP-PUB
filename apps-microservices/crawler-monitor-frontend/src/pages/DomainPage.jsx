import { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  Globe, RefreshCw, AlertCircle, ChevronLeft, ChevronRight, Clock,
  CheckCircle, XCircle, RotateCcw, Archive, AlertTriangle,
} from 'lucide-react';
import { useDomainDetailQuery } from '../hooks/queries';

const WINDOW_OPTIONS = ['24h', '7d', '30d'];

const STATUS_META = {
  finished:  { color: 'green',  text: 'Succès',     Icon: CheckCircle },
  failed:    { color: 'red',    text: 'Échec',      Icon: XCircle },
  running:   { color: 'blue',   text: 'En cours',   Icon: RefreshCw },
  stopping:  { color: 'yellow', text: 'Arrêt',      Icon: AlertTriangle },
  archived:  { color: 'gray',   text: 'Archivé',    Icon: Archive },
  restarting_oom: { color: 'orange', text: 'OOM',  Icon: RotateCcw },
};

const fmtDate = (s) => s ? new Date(s).toLocaleString('fr-FR') : '—';

const ChainNode = ({ entry, isFirst }) => {
  const meta = STATUS_META[(entry.status || '').toLowerCase()] || { color: 'gray', text: entry.status, Icon: Clock };
  const Icon = meta.Icon;
  return (
    <Link
      to={`/jobs/${entry.id}`}
      className={`flex flex-col items-center gap-1 group min-w-[110px] ${isFirst ? '' : 'opacity-90'}`}
      title={`${meta.text} · ${fmtDate(entry.start_time)}`}
    >
      <div className={`w-12 h-12 flex items-center justify-center rounded-full bg-${meta.color}-500/20 border-2 border-${meta.color}-500/40 group-hover:border-${meta.color}-400 transition-colors`}>
        <Icon className={`w-5 h-5 text-${meta.color}-400`} />
      </div>
      <div className="text-xs text-gray-300 font-mono truncate max-w-[110px]">#{entry.id.slice(0, 10)}</div>
      <div className="text-[10px] text-gray-500">{fmtDate(entry.start_time).slice(0, 16)}</div>
      {entry.crawl_mode === 'update' && (
        <span className="text-[9px] px-1 py-0 rounded bg-purple-500/20 text-purple-400">↻ update</span>
      )}
      {entry.oom_restart_count > 0 && (
        <span className="text-[9px] px-1 py-0 rounded bg-orange-500/20 text-orange-400">{entry.oom_restart_count}× OOM</span>
      )}
    </Link>
  );
};

const DomainPage = ({ token }) => {
  const { domain } = useParams();
  const navigate = useNavigate();
  const [window, setWindow] = useState('7d');
  const query = useDomainDetailQuery(token, domain, window);
  const data = query.data;

  const chain = data?.chain || [];
  const jobs = data?.jobs || [];

  // Aggregated stats from the jobs in the window
  const success = jobs.filter(j => ['finished', 'archived'].includes((j.status || '').toLowerCase())).length;
  const failure = jobs.filter(j => (j.status || '').toLowerCase() === 'failed').length;
  const running = jobs.filter(j => ['running', 'stopping', 'restarting_oom'].includes((j.status || '').toLowerCase())).length;
  const oomTotal = jobs.reduce((acc, j) => acc + (j.oom_restart_count || 0), 0);
  const completed = success + failure;
  const successRate = completed > 0 ? success / completed : null;
  const updateCount = jobs.filter(j => j.crawl_mode === 'update').length;

  return (
    <main className="container mx-auto p-4 space-y-4">
      <div className="flex items-center gap-2 text-sm text-gray-400">
        <Link to="/domains" className="hover:text-white">Domains</Link>
        <ChevronRight className="w-4 h-4" />
        <span className="text-white">{domain}</span>
      </div>

      <div className="bg-gray-800 rounded-lg shadow-xl">
        <div className="flex justify-between items-center p-4 border-b border-gray-700 flex-wrap gap-2">
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <Globe className="w-5 h-5 text-blue-400" /> {domain}
          </h2>
          <div className="flex items-center gap-2">
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

        {/* KPI row */}
        <div className="p-4 grid grid-cols-2 md:grid-cols-5 gap-3 border-b border-gray-700">
          <div className="bg-gray-900 p-3 rounded">
            <div className="text-xs text-gray-400">Total jobs</div>
            <div className="text-2xl font-bold text-white">{jobs.length}</div>
          </div>
          <div className="bg-gray-900 p-3 rounded">
            <div className="text-xs text-gray-400">Success rate</div>
            <div className={`text-2xl font-bold ${successRate == null ? 'text-gray-500' : successRate >= 0.9 ? 'text-green-400' : successRate >= 0.7 ? 'text-yellow-400' : 'text-red-400'}`}>
              {successRate == null ? '—' : `${(successRate * 100).toFixed(1)}%`}
            </div>
          </div>
          <div className="bg-gray-900 p-3 rounded">
            <div className="text-xs text-gray-400">En cours</div>
            <div className="text-2xl font-bold text-blue-400">{running}</div>
          </div>
          <div className="bg-gray-900 p-3 rounded">
            <div className="text-xs text-gray-400">OOM restarts</div>
            <div className="text-2xl font-bold text-orange-400">{oomTotal}</div>
          </div>
          <div className="bg-gray-900 p-3 rounded">
            <div className="text-xs text-gray-400">Update mode</div>
            <div className="text-2xl font-bold text-purple-400">{updateCount}/{jobs.length || 0}</div>
          </div>
        </div>

        {/* Run chain */}
        <div className="p-4 border-b border-gray-700">
          <div className="text-sm font-semibold text-gray-300 mb-3">Run chain (via previous_crawl_id)</div>
          {chain.length === 0 ? (
            <div className="text-gray-500 text-sm italic">Pas de chaîne — aucune relation previous_crawl_id détectée.</div>
          ) : (
            <div className="overflow-x-auto">
              <div className="flex items-start gap-2 min-w-min">
                {chain.map((entry, idx) => (
                  <div key={entry.id} className="flex items-center gap-2">
                    <ChainNode entry={entry} isFirst={idx === 0} />
                    {idx < chain.length - 1 && (
                      <ChevronLeft className="w-4 h-4 text-gray-600 mt-6" />
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Jobs list */}
        <div className="overflow-auto max-h-[50vh]">
          {query.isLoading && jobs.length === 0 ? (
            <div className="flex items-center justify-center py-16">
              <RefreshCw className="w-8 h-8 animate-spin text-blue-400" />
            </div>
          ) : jobs.length === 0 ? (
            <div className="text-center py-16 text-gray-400">
              <p>Aucun job dans la fenêtre.</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-900 sticky top-0">
                <tr className="text-left text-gray-400 text-xs uppercase">
                  <th className="px-3 py-2">When</th>
                  <th className="px-3 py-2">Job</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Mode</th>
                  <th className="px-3 py-2 text-right">OOM</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map(j => {
                  const meta = STATUS_META[(j.status || '').toLowerCase()] || { color: 'gray', text: j.status };
                  return (
                    <tr
                      key={j.id}
                      onClick={() => navigate(`/jobs/${j.id}`)}
                      className="border-t border-gray-700 hover:bg-gray-700/30 cursor-pointer"
                    >
                      <td className="px-3 py-2 text-gray-300 whitespace-nowrap">{fmtDate(j.start_time)}</td>
                      <td className="px-3 py-2 text-white font-mono text-xs">{j.id.slice(0, 12)}</td>
                      <td className="px-3 py-2">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded bg-${meta.color}-500/20 text-${meta.color}-400`}>
                          {meta.text}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        {j.crawl_mode === 'update' && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-400">↻ update</span>
                        )}
                        {j.crawl_mode === 'standard' && (
                          <span className="text-[10px] text-gray-500">standard</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right text-orange-400">
                        {j.oom_restart_count || ''}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </main>
  );
};

export default DomainPage;
