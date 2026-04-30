import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Globe, HeartPulse, FileText } from 'lucide-react';
import { cn } from '../../lib/utils';

/**
 * BottomTabBar — barre de navigation fixe en bas, mobile uniquement (< 640px).
 *
 * 4 items : Vue d'ensemble / Audit / Domaines / Sante
 * Visible uniquement sous le breakpoint sm (classe sm:hidden).
 */

const TABS = [
  { to: '/',       label: 'Vue',      icon: LayoutDashboard },
  { to: '/audit',  label: 'Alertes',  icon: FileText },
  { to: '/domains',label: 'Domaines', icon: Globe },
  { to: '/health', label: 'Sante',    icon: HeartPulse },
];

export function BottomTabBar({ alertCount = 0 }) {
  return (
    <nav
      className="fixed bottom-0 left-0 right-0 h-14 z-40 sm:hidden bg-surface border-t border-hairline grid grid-cols-4"
      aria-label="Navigation mobile"
    >
      {TABS.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          className={({ isActive }) =>
            cn(
              'flex flex-col items-center justify-center gap-0.5 relative text-[10px] font-medium transition-colors',
              isActive ? 'text-accent' : 'text-ink-3 hover:text-ink-1'
            )
          }
        >
          <span className="relative">
            <Icon className="h-5 w-5" aria-hidden="true" />
            {label === 'Alertes' && alertCount > 0 && (
              <span className="absolute -top-1 -right-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-err text-[8px] font-bold text-white leading-none">
                {alertCount > 9 ? '9+' : alertCount}
              </span>
            )}
          </span>
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
