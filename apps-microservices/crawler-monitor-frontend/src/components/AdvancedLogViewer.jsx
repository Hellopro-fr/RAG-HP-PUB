import { useState, useMemo, useCallback } from 'react';
import { List } from 'react-window';
import {
  XCircle, AlertTriangle, Info, Search, Download, ExternalLink,
} from 'lucide-react';

/**
 * Advanced log viewer.
 *
 * Virtualised with react-window v2 so it stays smooth on 100k+ lines.
 * Pagination has been removed in favor of a fixed-height scrolling list.
 */
const ROW_HEIGHT = 24;
const LIST_HEIGHT_PX = 480;

const highlightLogClass = (level) => {
  switch (level) {
    case 'error': return 'text-red-400 bg-red-900/20';
    case 'warn':  return 'text-yellow-400 bg-yellow-900/20';
    default:      return 'text-gray-300';
  }
};

// Row component used by react-window. Receives: { index, style, lines, searchTerm }
const LogRow = ({ index, style, lines, searchTerm }) => {
  const item = lines[index];
  if (!item) return null;
  const { line, level, url } = item;

  // Inline search highlighter (memoization per row would cost more than help)
  let content;
  if (!searchTerm) {
    content = line;
  } else {
    const parts = line.split(new RegExp(`(${searchTerm})`, 'gi'));
    content = parts.map((part, i) =>
      part.toLowerCase() === searchTerm.toLowerCase()
        ? <span key={i} className="bg-yellow-500 text-black font-bold">{part}</span>
        : part
    );
  }

  return (
    <div
      style={style}
      className={`flex gap-4 items-start py-0.5 hover:bg-gray-800/50 ${highlightLogClass(level)} px-2 rounded font-mono text-xs`}
    >
      <span className="text-gray-600 select-none w-12 text-right shrink-0">{index + 1}</span>
      <span className="flex-1 whitespace-pre truncate">{content}</span>
      {url && (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0 text-blue-400 hover:text-blue-300"
          title={url}
        >
          <ExternalLink className="w-3.5 h-3.5" />
        </a>
      )}
    </div>
  );
};

const AdvancedLogViewer = ({ content, jobId }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [levelFilter, setLevelFilter] = useState('all');

  const parsedLines = useMemo(() => {
    return content.split('\n').map((line, index) => {
      const lowerLine = line.toLowerCase();
      let level = 'info';
      if (lowerLine.includes('error')) level = 'error';
      else if (lowerLine.includes('warn')) level = 'warn';

      const urlMatch = line.match(/(https?:\/\/[^\s]+)/);
      const url = urlMatch ? urlMatch[1] : null;

      const timestampMatch = line.match(/(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2})/);
      const timestamp = timestampMatch ? timestampMatch[1] : null;

      return { line, level, url, timestamp, index };
    });
  }, [content]);

  const filteredLines = useMemo(() => {
    return parsedLines.filter(({ line, level }) => {
      const matchesSearch = !searchTerm || line.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesLevel = levelFilter === 'all' || level === levelFilter;
      return matchesSearch && matchesLevel;
    });
  }, [parsedLines, searchTerm, levelFilter]);

  const levelStats = useMemo(() => {
    const stats = { error: 0, warn: 0, info: 0 };
    parsedLines.forEach(({ level }) => stats[level]++);
    return stats;
  }, [parsedLines]);

  const downloadLogs = useCallback((format) => {
    let data, filename, type;
    if (format === 'txt') {
      data = filteredLines.map(l => l.line).join('\n');
      filename = `job-${jobId}-logs.txt`;
      type = 'text/plain';
    } else if (format === 'json') {
      data = JSON.stringify(filteredLines, null, 2);
      filename = `job-${jobId}-logs.json`;
      type = 'application/json';
    } else if (format === 'csv') {
      data = 'Index,Level,Line,URL,Timestamp\n' +
        filteredLines.map(l =>
          `${l.index},"${l.level}","${l.line.replace(/"/g, '""')}","${l.url || ''}","${l.timestamp || ''}"`
        ).join('\n');
      filename = `job-${jobId}-logs.csv`;
      type = 'text/csv';
    }
    const blob = new Blob([data], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }, [filteredLines, jobId]);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-3 flex items-center gap-3">
          <XCircle className="w-8 h-8 text-red-400" />
          <div>
            <p className="text-2xl font-bold text-red-400">{levelStats.error}</p>
            <p className="text-sm text-gray-400">Erreurs</p>
          </div>
        </div>
        <div className="bg-yellow-900/20 border border-yellow-500/30 rounded-lg p-3 flex items-center gap-3">
          <AlertTriangle className="w-8 h-8 text-yellow-400" />
          <div>
            <p className="text-2xl font-bold text-yellow-400">{levelStats.warn}</p>
            <p className="text-sm text-gray-400">Avertissements</p>
          </div>
        </div>
        <div className="bg-blue-900/20 border border-blue-500/30 rounded-lg p-3 flex items-center gap-3">
          <Info className="w-8 h-8 text-blue-400" />
          <div>
            <p className="text-2xl font-bold text-blue-400">{levelStats.info}</p>
            <p className="text-sm text-gray-400">Info</p>
          </div>
        </div>
      </div>

      <div className="bg-gray-800 p-4 rounded-lg space-y-3">
        <div className="flex gap-3 flex-wrap">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              type="text"
              placeholder="Rechercher dans les logs..."
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded-md pl-10 pr-4 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
          </div>

          <select
            value={levelFilter}
            onChange={e => setLevelFilter(e.target.value)}
            className="bg-gray-900 border border-gray-700 rounded-md px-4 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
          >
            <option value="all">Tous les niveaux</option>
            <option value="error">Erreurs</option>
            <option value="warn">Avertissements</option>
            <option value="info">Info</option>
          </select>

          <div className="flex gap-2">
            <button onClick={() => downloadLogs('txt')}  className="flex items-center gap-2 px-3 py-2 bg-blue-600 hover:bg-blue-700 rounded-md text-sm transition-colors">
              <Download className="w-4 h-4" /> TXT
            </button>
            <button onClick={() => downloadLogs('json')} className="flex items-center gap-2 px-3 py-2 bg-green-600 hover:bg-green-700 rounded-md text-sm transition-colors">
              <Download className="w-4 h-4" /> JSON
            </button>
            <button onClick={() => downloadLogs('csv')}  className="flex items-center gap-2 px-3 py-2 bg-purple-600 hover:bg-purple-700 rounded-md text-sm transition-colors">
              <Download className="w-4 h-4" /> CSV
            </button>
          </div>
        </div>

        <div className="text-sm text-gray-400">
          {filteredLines.length} lignes
          {filteredLines.length !== parsedLines.length && ` (sur ${parsedLines.length} au total)`}
        </div>
      </div>

      <div className="bg-gray-900 rounded-lg overflow-hidden">
        {filteredLines.length === 0 ? (
          <div className="text-center py-12 text-gray-500 text-sm">Aucune ligne ne correspond.</div>
        ) : (
          <List
            rowComponent={LogRow}
            rowCount={filteredLines.length}
            rowHeight={ROW_HEIGHT}
            rowProps={{ lines: filteredLines, searchTerm }}
            style={{ height: LIST_HEIGHT_PX }}
            overscanCount={10}
          />
        )}
      </div>
    </div>
  );
};

export default AdvancedLogViewer;
