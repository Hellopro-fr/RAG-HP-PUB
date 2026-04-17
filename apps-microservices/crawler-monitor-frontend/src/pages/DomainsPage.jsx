import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Globe, RefreshCw, AlertCircle, Search,
} from 'lucide-react';
import { useDomainsQuery } from '../hooks/queries';
import { Card } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Button } from '../components/ui/button';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '../components/ui/table';
import {
  Tooltip, TooltipTrigger, TooltipContent,
} from '../components/ui/tooltip';
import { cn } from '../lib/utils';

const WINDOW_OPTIONS = ['24h', '7d', '30d'];

// Fix 3b : libellés explicites pour les entêtes cryptiques
const HEAD_TOOLTIPS = {
  oom:    'Out Of Memory — nombre de redémarrages suite à un dépassement mémoire',
  ok:     'Succès (jobs finished/archived)',
  ko:     'Échec (failed)',
  run:    'En cours (running/stopping/restarting_oom)',
  update: 'Pourcentage de jobs lancés en mode update (crawl incrémental)',
  succ:   'Taux de succès sur les jobs terminés (finished+archived) / (finished+archived+failed)',
};

// Wrapper pour des <TableHead> annotés d'un tooltip explicatif
const HeadWithTip = ({ tip, className, children }) => (
  <TableHead className={className}>
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="cursor-help border-b border-dotted border-muted-foreground/40">
          {children}
        </span>
      </TooltipTrigger>
      <TooltipContent>{tip}</TooltipContent>
    </Tooltip>
  </TableHead>
);

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
    if (rate == null) return 'text-muted-foreground';
    if (rate >= 0.9) return 'text-success';
    if (rate >= 0.7) return 'text-warning';
    return 'text-destructive';
  };

  // Fix 3a : handler unifié (click + clavier) pour l'a11y des lignes cliquables
  const goToDomain = useCallback((d) => {
    navigate(`/domains/${encodeURIComponent(d.domain)}`);
  }, [navigate]);

  const onRowKeyDown = useCallback((e, d) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      goToDomain(d);
    }
  }, [goToDomain]);

  return (
    <div className="p-4">
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border p-4">
          <h2 className="flex items-center gap-2 text-base font-semibold">
            <Globe className="h-4 w-4 text-primary" />
            Domains
            <span className="font-mono text-xs font-normal text-muted-foreground">
              ({filtered.length}{filtered.length !== all.length ? ` / ${all.length}` : ''})
            </span>
          </h2>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                type="text"
                placeholder="Filtrer…"
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="h-8 w-[200px] pl-8"
              />
            </div>
            <div className="flex gap-0.5 rounded-md border border-border bg-muted p-0.5">
              {WINDOW_OPTIONS.map(w => (
                <button
                  key={w}
                  onClick={() => setWindow(w)}
                  className={cn(
                    'rounded px-2 py-0.5 text-xs transition-colors',
                    w === window
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                  )}
                >
                  {w}
                </button>
              ))}
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => query.refetch()}
              disabled={query.isFetching}
              title="Rafraîchir"
            >
              <RefreshCw className={cn('h-4 w-4', query.isFetching && 'animate-spin')} />
            </Button>
          </div>
        </div>

        {query.isError && (
          <div className="flex items-center gap-2 border-b border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" /> {query.error?.message || 'Erreur de chargement'}
          </div>
        )}

        <div className="max-h-[75vh] overflow-auto">
          {query.isLoading && all.length === 0 ? (
            <div className="flex items-center justify-center py-16">
              <RefreshCw className="h-6 w-6 animate-spin text-primary" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="py-16 text-center text-muted-foreground">
              <Globe className="mx-auto mb-3 h-10 w-10 opacity-40" />
              <p className="text-sm">
                {search ? `Aucun domaine ne correspond à "${search}".` : 'Aucun domaine sur la période.'}
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Domain</TableHead>
                  <TableHead className="text-right">Jobs</TableHead>
                  <HeadWithTip tip={HEAD_TOOLTIPS.ok}     className="text-right">✓</HeadWithTip>
                  <HeadWithTip tip={HEAD_TOOLTIPS.ko}     className="text-right">✗</HeadWithTip>
                  <HeadWithTip tip={HEAD_TOOLTIPS.run}    className="text-right">▶</HeadWithTip>
                  <HeadWithTip tip={HEAD_TOOLTIPS.oom}    className="text-right">OOM</HeadWithTip>
                  <HeadWithTip tip={HEAD_TOOLTIPS.succ}   className="text-right">Success rate</HeadWithTip>
                  <HeadWithTip tip={HEAD_TOOLTIPS.update} className="text-right">Update %</HeadWithTip>
                  <TableHead>Last run</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map(d => (
                  <TableRow
                    key={d.domain}
                    onClick={() => goToDomain(d)}
                    onKeyDown={(e) => onRowKeyDown(e, d)}
                    role="button"
                    tabIndex={0}
                    className="cursor-pointer focus:outline-none focus-visible:bg-accent focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <TableCell className="font-mono text-foreground">{d.domain}</TableCell>
                    <TableCell className="text-right font-mono text-muted-foreground">{d.total_jobs}</TableCell>
                    <TableCell className="text-right font-mono text-success">{d.success || ''}</TableCell>
                    <TableCell className="text-right font-mono text-destructive">{d.failure || ''}</TableCell>
                    <TableCell className="text-right font-mono text-info">{d.running || ''}</TableCell>
                    <TableCell className="text-right font-mono text-warning">{d.oom_total || ''}</TableCell>
                    <TableCell className={cn('text-right font-mono font-semibold', successColor(d.success_rate))}>
                      {fmtPct(d.success_rate)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-primary">
                      {d.update_share > 0 ? `${(d.update_share * 100).toFixed(0)}%` : ''}
                    </TableCell>
                    <TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">
                      {fmtDate(d.last_run_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      </Card>
    </div>
  );
};

export default DomainsPage;
