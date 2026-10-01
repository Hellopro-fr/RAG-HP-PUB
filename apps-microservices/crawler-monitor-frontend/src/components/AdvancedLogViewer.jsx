import { useState, useMemo, useCallback } from 'react';
import { List } from 'react-window';
import {
  XCircle, AlertTriangle, Info, Search, Download, ExternalLink,
} from 'lucide-react';
import { Card } from './ui/card';
import { Input } from './ui/input';
import { Button } from './ui/button';
import { cn } from '../lib/utils';

/**
 * Advanced log viewer.
 *
 * Virtualised with react-window v2 so it stays smooth on 100k+ lines.
 * Pagination has been removed in favor of a fixed-height scrolling list.
 */
const ROW_HEIGHT = 24;
const LIST_HEIGHT_PX = 480;

const levelRowClass = (level) => {
  switch (level) {
    case 'error': return 'text-err bg-err-soft';
    case 'warn':  return 'text-warn bg-warn-soft';
    default:      return 'text-ink-0/80';
  }
};

const SELECT_CLS =
  'h-9 appearance-none rounded-md border border-hairline bg-bg-1 px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent';

const LogRow = ({ index, style, lines, searchTerm }) => {
  const item = lines[index];
  if (!item) return null;
  const { line, level, url } = item;

  let content;
  if (!searchTerm) {
    content = line;
  } else {
    // Échappe les métacaractères regex pour éviter un crash sur `(`, `*`, `[`, `\`, etc.
    const escaped = searchTerm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const parts = line.split(new RegExp(`(${escaped})`, 'gi'));
    content = parts.map((part, i) =>
      part.toLowerCase() === searchTerm.toLowerCase()
        ? <span key={i} className="bg-warn font-bold text-warn-foreground">{part}</span>
        : part
    );
  }

  return (
    <div
      style={style}
      className={cn(
        'flex items-start gap-4 rounded px-2 py-0.5 font-mono text-xs hover:bg-accent/50',
        levelRowClass(level)
      )}
    >
      <span className="w-12 shrink-0 select-none text-right text-ink-3">{index + 1}</span>
      <span className="flex-1 truncate whitespace-pre">{content}</span>
      {url && (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0 text-accent hover:text-accent/80"
          title={url}
        >
          <ExternalLink className="h-3.5 w-3.5" />
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
      // Trim la ponctuation finale parfois capturée avec l'URL.
      const url = urlMatch ? urlMatch[1].replace(/[.,;)\]"'>]+$/, '') : null;

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
      <div className="grid grid-cols-3 gap-3">
        <Card className="flex items-center gap-3 border-err/30 bg-err-soft p-3">
          <XCircle className="h-7 w-7 text-err" />
          <div>
            <p className="font-mono text-2xl font-bold text-err">{levelStats.error}</p>
            <p className="text-xs text-ink-3">Erreurs</p>
          </div>
        </Card>
        <Card className="flex items-center gap-3 border-warn/30 bg-warn-soft p-3">
          <AlertTriangle className="h-7 w-7 text-warn" />
          <div>
            <p className="font-mono text-2xl font-bold text-warn">{levelStats.warn}</p>
            <p className="text-xs text-ink-3">Avertissements</p>
          </div>
        </Card>
        <Card className="flex items-center gap-3 border-info/30 bg-info-soft p-3">
          <Info className="h-7 w-7 text-info" />
          <div>
            <p className="font-mono text-2xl font-bold text-info">{levelStats.info}</p>
            <p className="text-xs text-ink-3">Info</p>
          </div>
        </Card>
      </div>

      <Card className="space-y-3 p-3">
        <div className="flex flex-wrap gap-3">
          <div className="relative min-w-[200px] flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" />
            <Input
              type="text"
              placeholder="Rechercher dans les logs…"
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              className="pl-10"
            />
          </div>

          <select
            value={levelFilter}
            onChange={e => setLevelFilter(e.target.value)}
            className={SELECT_CLS}
          >
            <option value="all">Tous les niveaux</option>
            <option value="error">Erreurs</option>
            <option value="warn">Avertissements</option>
            <option value="info">Info</option>
          </select>

          <div className="flex gap-2">
            <Button size="sm" onClick={() => downloadLogs('txt')}>
              <Download className="h-4 w-4" /> TXT
            </Button>
            <Button size="sm" variant="outline" onClick={() => downloadLogs('json')}>
              <Download className="h-4 w-4" /> JSON
            </Button>
            <Button size="sm" variant="outline" onClick={() => downloadLogs('csv')}>
              <Download className="h-4 w-4" /> CSV
            </Button>
          </div>
        </div>

        <div className="text-xs text-ink-3">
          <span className="font-mono">{filteredLines.length}</span> lignes
          {filteredLines.length !== parsedLines.length && (
            <> (sur <span className="font-mono">{parsedLines.length}</span> au total)</>
          )}
        </div>
      </Card>

      <Card className="overflow-hidden bg-bg-1 p-0">
        {filteredLines.length === 0 ? (
          <div className="py-12 text-center text-sm text-ink-3">
            Aucune ligne ne correspond.
          </div>
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
      </Card>
    </div>
  );
};

export default AdvancedLogViewer;
