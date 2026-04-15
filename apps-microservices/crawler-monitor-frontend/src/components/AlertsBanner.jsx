import { useState, useEffect, useRef } from 'react';
import { AlertTriangle, AlertCircle, ChevronDown, ChevronUp, X, Bell, BellOff } from 'lucide-react';
import { useAlertsQuery } from '../hooks/queries';
import { useBrowserNotifications } from '../hooks/useBrowserNotifications';

/**
 * AlertsBanner — top-of-Overview banner aggregating active alerts.
 *
 * Behavior:
 *  - Shows nothing when no alerts (no chrome at all)
 *  - When alerts exist: collapsed strip showing the top alert + "voir tous (N)"
 *  - Click expands to show the full list with severity chips
 *  - Severities: critical (red, immediate eye-catch), warn (orange)
 *  - 30s background refetch via useAlertsQuery
 */

const SEVERITY_STYLES = {
  critical: {
    bg:    'bg-red-900/40 border-red-500/50',
    text:  'text-red-200',
    chip:  'bg-red-500/30 text-red-200',
    Icon:  AlertCircle,
  },
  warn: {
    bg:    'bg-orange-900/40 border-orange-500/40',
    text:  'text-orange-200',
    chip:  'bg-orange-500/30 text-orange-200',
    Icon:  AlertTriangle,
  },
  info: {
    bg:    'bg-blue-900/40 border-blue-500/40',
    text:  'text-blue-200',
    chip:  'bg-blue-500/30 text-blue-200',
    Icon:  AlertCircle,
  },
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

  // Browser notifications: notify on NEW critical alerts that we haven't notified yet.
  useEffect(() => {
    const currentCriticalIds = new Set(allAlerts.filter(a => a.severity === 'critical').map(a => a.id));
    // Notify each newly-appeared critical alert
    for (const a of allAlerts) {
      if (a.severity !== 'critical') continue;
      if (notifiedIdsRef.current.has(a.id)) continue;
      notifiedIdsRef.current.add(a.id);
      notif.notify(`Crawler: ${a.kind}`, { body: a.message, tag: a.id });
    }
    // Garbage-collect IDs that are no longer active so they re-notify if they come back
    for (const id of notifiedIdsRef.current) {
      if (!currentCriticalIds.has(id)) notifiedIdsRef.current.delete(id);
    }
  }, [allAlerts, notif]);

  if (visible.length === 0) return null;

  // Worst severity across visible alerts drives the bar color
  const worstSeverity = visible.some(a => a.severity === 'critical') ? 'critical' : 'warn';
  const styles = SEVERITY_STYLES[worstSeverity];
  const TopIcon = styles.Icon;

  const dismissOne = (id) => {
    setDismissedIds(prev => {
      const next = new Set(prev);
      next.add(id);
      return next;
    });
  };

  return (
    <div className={`rounded-lg border ${styles.bg} ${styles.text}`}>
      <div className="w-full flex items-center gap-3 px-3 py-2">
        <button
          type="button"
          onClick={() => setExpanded(e => !e)}
          className="flex-1 min-w-0 flex items-center gap-3 text-left"
        >
          <TopIcon className="w-5 h-5 shrink-0" />
          <div className="flex-1 min-w-0">
            <span className="font-semibold">{visible.length} alerte{visible.length > 1 ? 's' : ''}</span>
            <span className="ml-2 text-sm opacity-80 truncate">— {visible[0].message}</span>
          </div>
          {expanded ? <ChevronUp className="w-4 h-4 shrink-0" /> : <ChevronDown className="w-4 h-4 shrink-0" />}
        </button>
        {notif.supported && (
          <button
            type="button"
            onClick={notif.toggle}
            className="opacity-70 hover:opacity-100 shrink-0"
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
              ? <Bell className="w-4 h-4" />
              : <BellOff className="w-4 h-4" />}
          </button>
        )}
      </div>
      {expanded && (
        <ul className="px-3 pb-3 space-y-2">
          {visible.map(a => {
            const s = SEVERITY_STYLES[a.severity] || SEVERITY_STYLES.info;
            const SIcon = s.Icon;
            const since = fmtSince(a.since);
            return (
              <li key={a.id} className={`flex items-start gap-3 px-2 py-1.5 rounded ${s.bg} ${s.text}`}>
                <SIcon className="w-4 h-4 shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm">{a.message}</div>
                  <div className="text-[11px] opacity-70 mt-0.5">
                    <span className={`px-1.5 py-0.5 rounded mr-2 ${s.chip}`}>{a.severity}</span>
                    <span className="font-mono">{a.kind}</span>
                    {since && <span className="ml-2">· {since}</span>}
                  </div>
                </div>
                <button
                  onClick={(ev) => { ev.stopPropagation(); dismissOne(a.id); }}
                  className="opacity-60 hover:opacity-100"
                  title="Masquer (réapparaîtra si l'alerte persiste)"
                >
                  <X className="w-4 h-4" />
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