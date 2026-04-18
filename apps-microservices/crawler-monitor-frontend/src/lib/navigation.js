import {
  LayoutDashboard, Globe, Mail, SlidersHorizontal, FileText,
} from 'lucide-react';

/**
 * Sidebar navigation tree.
 * Each entry has: to, label, icon, optional `section` (group heading),
 * optional `badgeKey` (to surface a count/indicator on the item).
 *
 * Labels are in French to match the operator-facing app language.
 */
export const NAV_ITEMS = [
  {
    section: 'Supervision',
    items: [
      { to: '/',                  label: 'Vue d\'ensemble',  icon: LayoutDashboard, description: 'KPI, timeline, replicas, liste des jobs' },
      { to: '/domains',           label: 'Domaines',         icon: Globe,            description: 'Activité agrégée par domaine crawlé' },
      { to: '/callbacks',         label: 'Callbacks',        icon: Mail,             description: 'Webhooks en échec à rejouer', badgeKey: 'failedCallbacks' },
    ],
  },
  {
    section: 'Opérations',
    items: [
      { to: '/capacity-planning', label: 'Capacity planning', icon: SlidersHorizontal, description: 'RAM allouée vs utilisée · dimensionnement' },
      { to: '/audit',             label: 'Journal d\'audit',  icon: FileText,          description: 'Historique des actions sensibles' },
    ],
  },
];

/**
 * Resolve a pathname to a human breadcrumb trail.
 * Handles param segments like /jobs/:id/queue → Job #c8f2 / Queue.
 */
const ROUTE_LABELS = {
  '/':                 'Vue d\'ensemble',
  '/domains':          'Domaines',
  '/callbacks':        'Callbacks',
  '/audit':            'Journal d\'audit',
  '/capacity-planning':'Capacity planning',
};

/**
 * Given a pathname, return an array of { label, to } breadcrumbs.
 * The last item has no `to` (current location).
 */
export function resolveBreadcrumbs(pathname) {
  if (!pathname || pathname === '/') {
    return [{ label: 'Vue d\'ensemble' }];
  }
  const parts = pathname.split('/').filter(Boolean);
  const crumbs = [{ label: 'Vue d\'ensemble', to: '/' }];

  // Match well-known prefixes first
  if (ROUTE_LABELS[pathname]) {
    crumbs.push({ label: ROUTE_LABELS[pathname] });
    return crumbs;
  }

  // /jobs/:id [queue|dataset|replay]
  if (parts[0] === 'jobs' && parts[1]) {
    crumbs.push({ label: `Job ${parts[1].slice(0, 8)}`, to: `/jobs/${parts[1]}` });
    if (parts[2] === 'queue')   crumbs.push({ label: 'Queue' });
    if (parts[2] === 'dataset') crumbs.push({ label: 'Dataset' });
    if (parts[2] === 'replay')  crumbs.push({ label: 'Replay' });
    return crumbs;
  }

  // /domains/:domain
  if (parts[0] === 'domains' && parts[1]) {
    crumbs.push({ label: 'Domaines', to: '/domains' });
    crumbs.push({ label: decodeURIComponent(parts[1]) });
    return crumbs;
  }

  // Fallback: show raw segments
  let acc = '';
  for (const p of parts) {
    acc += '/' + p;
    crumbs.push({ label: p, to: acc });
  }
  // Mark last as current (no `to`)
  if (crumbs.length > 1) delete crumbs[crumbs.length - 1].to;
  return crumbs;
}

/**
 * Flat list of nav items (sections flattened) — used by the command palette.
 */
export const FLAT_NAV = NAV_ITEMS.flatMap(s => s.items);
