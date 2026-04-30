import {
  CheckCircle, XCircle, Clock, AlertTriangle, RefreshCw, Archive, RotateCcw,
} from 'lucide-react';
import { cn } from '../lib/utils';

/**
 * JobCard — dense row in the jobs list.
 *
 * Status → variant mapping (not dynamic class names, so Tailwind purge keeps them).
 * An OOM-restart count overrides the left rail to warning regardless of status.
 */
const STATUS_MAP = {
  running:        { label: 'En cours',   icon: RefreshCw,     spin: true,  accent: 'info' },
  finished:       { label: 'Succès',     icon: CheckCircle,   accent: 'success' },
  failed:         { label: 'Échec',      icon: XCircle,       accent: 'destructive' },
  stopping:       { label: 'Arrêt…',     icon: AlertTriangle, accent: 'warning' },
  archived:       { label: 'Archivé',    icon: Archive,       accent: 'muted' },
  restarting_oom: { label: 'Restart OOM', icon: RotateCcw,    spin: true,  accent: 'warning' },
};

// Static class map — required so Tailwind keeps these classes in the bundle.
const ACCENT_CLASSES = {
  info:        { badge: 'bg-info/15 text-info',               rail: 'border-l-info' },
  success:     { badge: 'bg-ok-soft text-ok',         rail: 'border-l-success' },
  destructive: { badge: 'bg-err-soft text-err', rail: 'border-l-destructive' },
  warning:     { badge: 'bg-warn-soft text-warn',         rail: 'border-l-warning' },
  muted:       { badge: 'bg-bg-2 text-ink-3',     rail: 'border-l-ink-3/40' },
};

const JobCard = ({ job, onClick, isSelected }) => {
  const status = STATUS_MAP[(job.status || '').toLowerCase()] ?? {
    label: job.status || 'pending',
    icon: Clock,
    accent: 'muted',
  };
  const StatusIcon = status.icon;
  const accent = ACCENT_CLASSES[status.accent];

  const oomCount = job.oom_restart_count || 0;
  const railClass = isSelected
    ? 'border-l-primary'
    : oomCount > 0
      ? 'border-l-warning'
      : accent.rail;

  const hasMeta = job.crawl_mode === 'update' || oomCount > 0 || job.previous_crawl_id;

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick?.();
        }
      }}
      className={cn(
        'cursor-pointer rounded-md border border-hairline bg-surface p-3 text-ink-0 transition-colors border-l-4',
        'hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
        isSelected && 'bg-accent shadow-sm',
        railClass
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate font-mono text-sm font-semibold text-ink-0">
            #{job.id}
          </p>
          <p className="truncate text-xs text-ink-3">{job.domain}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <span className={cn('rounded px-1.5 py-0.5 text-[10px] font-medium', accent.badge)}>
            {status.label}
          </span>
          <StatusIcon
            className={cn(
              'h-4 w-4',
              status.accent === 'info' && 'text-info',
              status.accent === 'success' && 'text-ok',
              status.accent === 'destructive' && 'text-err',
              status.accent === 'warning' && 'text-warn',
              status.accent === 'muted' && 'text-ink-3',
              status.spin && 'animate-spin'
            )}
          />
        </div>
      </div>

      {hasMeta && (
        <div className="mt-1.5 flex flex-wrap items-center gap-1">
          {job.crawl_mode === 'update' && (
            <span
              className="rounded bg-accent/15 px-1.5 py-0.5 text-[10px] text-accent"
              title="Crawl incrémental (update)"
            >
              ↻ update
            </span>
          )}
          {oomCount > 0 && (
            <span
              className="rounded bg-warn-soft px-1.5 py-0.5 text-[10px] font-semibold text-warn"
              title={`${oomCount} redémarrage${oomCount > 1 ? 's' : ''} après OOM`}
            >
              {oomCount}× OOM
            </span>
          )}
          {job.previous_crawl_id && (
            <span
              className="text-[10px] text-ink-3"
              title={`Retry de ${job.previous_crawl_id}`}
            >
              ↩
            </span>
          )}
        </div>
      )}

      <p className="mt-2 font-mono text-[11px] text-ink-3">
        {new Date(job.start_time).toLocaleString('fr-FR')}
      </p>
    </div>
  );
};

export default JobCard;
