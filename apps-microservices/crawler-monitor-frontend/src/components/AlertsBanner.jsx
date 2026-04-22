import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, AlertCircle, ChevronDown, ChevronUp, X, Bell, BellOff } from 'lucide-react';
import { useAlertsQuery } from '../hooks/queries';
import { useBrowserNotifications } from '../hooks/useBrowserNotifications';
import { cn } from '../lib/utils';

/**
 * AlertsBanner — top-of-Overview banner aggregating active alerts.
 *
 * Behavior:
 *  - Shows nothing when no alerts (no chrome at all)
 *  - When alerts exist: collapsed strip showing the top alert + "voir tous (N)"
 *  - Click expands to show the full list with severity chips
 *  - Severities: critical (destructive), warn (warning), info (info)
 *  - 30s background refetch via useAlertsQuery
 */

const SEVERITY_STYLES = {
  critical: {
    surface: 'border-destructive/40 bg-destructive/10 text-destructive',
    chip:    'bg-destructive/20 text-destructive',
    Icon:    AlertCircle,
  },
  warn: {
    surface: 'border-warning/40 bg-warning/10 text-warning',
    chip:    'bg-warning/20 text-warning',
    Icon:    AlertTriangle,
  },
  info: {
    surface: 'border-info/40 bg-info/10 text-info',
    chip:    'bg-info/20 text-info',
    Icon:    AlertCircle,
  },
};

// Surface dominante quand il y a au moins une alerte critique : fond plein
// destructive, lisible d'un coup d'œil en pleine nuit.
const CRITICAL_DOMINANT_SURFACE =
  'bg-destructive text-destructive-foreground border-destructive';

const SEVERITY_LABELS = {
  critical: 'Critique',
  warn:     'Avertissement',
  info:     'Info',
};

const fmtSince = (ts) => {
  if (!ts) return null;
  const ageMs = Date.now() - ts;
  const min = Math.floor(ageMs / 60000);
  if (min < 1) return 'à l\'instant';
  if (min < 60) return `depuis ${min} min`;
  const h = Math.floor(min / 60);
  return `depuis ${h}h${(min % 60).toString().padStart(2, '0')}`;
};

const AlertsBanner = ({ token }) => {
  const [expanded, setExpanded] = useState(false);
  const [dismissedIds, setDismissedIds] = useState(() => new Set());
  const notif = useBrowserNotifications();
  const notifiedIdsRef = useRef(new Set());

  const query = useAlertsQuery(token);
  const allAlerts = query.data?.alerts || [];
  const visible = allAlerts.filter(a => !dismissedIds.has(a.id));

  useEffect(() => {
    const currentCriticalIds = new Set(allAlerts.filter(a => a.severity === 'critical').map(a => a.id));
    for (const a of allAlerts) {
      if (a.severity !== 'critical') continue;
      if (notifiedIdsRef.current.has(a.id)) continue;
      notifiedIdsRef.current.add(a.id);
      notif.notify(`Crawler: ${a.kind}`, { body: a.message, tag: a.id });
    }
    for (const id of notifiedIdsRef.current) {
      if (!currentCriticalIds.has(id)) notifiedIdsRef.current.delete(id);
    }
  }, [allAlerts, notif]);

  if (visible.length === 0) return null;

  const worstSeverity = visible.some(a => a.severity === 'critical') ? 'critical' : 'warn';
  const styles = SEVERITY_STYLES[worstSeverity];
  const TopIcon = styles.Icon;
  const isCriticalDominant = worstSeverity === 'critical';
  const hasCallbackAlert = visible.some(a => (a.kind || '').includes('callback'));

  const dismissOne = (id) => {
    setDismissedIds(prev => {
      const next = new Set(prev);
      next.add(id);
      return next;
    });
  };

  return (
    <div className={cn('rounded-md border', isCriticalDominant ? CRITICAL_DOMINANT_SURFACE : styles.surface)}>
      <div className="flex w-full items-center gap-3 px-3 py-2">
        <button
          type="button"
          onClick={() => setExpanded(e => !e)}
          className="flex min-w-0 flex-1 items-center gap-3 text-left"
        >
          <TopIcon className="h-4 w-4 shrink-0" />
          <div className="flex min-w-0 flex-1 items-baseline gap-2">
            <span className="text-sm font-bold">{visible.length} alerte{visible.length > 1 ? 's' : ''}</span>
            <span className="truncate text-sm">— {visible[0].message}</span>
          </div>
          {expanded ? <ChevronUp className="h-4 w-4 shrink-0" /> : <ChevronDown className="h-4 w-4 shrink-0" />}
        </button>
        {hasCallbackAlert && (
          <Link
            to="/callbacks"
            onClick={(ev) => ev.stopPropagation()}
            className="shrink-0 text-xs underline underline-offset-2 hover:opacity-80"
          >
            Voir callbacks
          </Link>
        )}
        {notif.supported && (
          <button
            type="button"
            onClick={notif.toggle}
            className="shrink-0 opacity-70 hover:opacity-100"
            title={
              notif.enabled
                ? (notif.permission === 'granted'
                    ? 'Notifications navigateur activées (cliquer pour couper)'
                    : notif.permission === 'denied'
                      ? 'Notifications bloquées par le navigateur'
                      : 'Cliquer pour autoriser les notifications')
                : 'Notifications navigateur muettes (cliquer pour activer)'
            }
          >
            {notif.enabled && notif.permission === 'granted'
              ? <Bell className="h-4 w-4" />
              : <BellOff className="h-4 w-4" />}
          </button>
        )}
      </div>
      {expanded && (
        <ul className="space-y-1.5 px-3 pb-3">
          {visible.map(a => {
            const s = SEVERITY_STYLES[a.severity] || SEVERITY_STYLES.info;
            const SIcon = s.Icon;
            const since = fmtSince(a.since);
            return (
              <li key={a.id} className={cn('flex items-start gap-3 rounded border px-2 py-1.5', s.surface)}>
                <SIcon className="mt-0.5 h-4 w-4 shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="text-sm">{a.message}</div>
                  <div className="mt-0.5 text-[11px] opacity-80">
                    <span className={cn('mr-2 rounded px-1.5 py-0.5', s.chip)}>{SEVERITY_LABELS[a.severity] || a.severity}</span>
                    <span className="font-mono">{a.kind}</span>
                    {since && <span className="ml-2">· {since}</span>}
                  </div>
                </div>
                <button
                  onClick={(ev) => { ev.stopPropagation(); dismissOne(a.id); }}
                  className="opacity-60 hover:opacity-100"
                  title="Masquer (réapparaîtra si l'alerte persiste)"
                >
                  <X className="h-4 w-4" />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};

export default AlertsBanner;
