import { NavLink } from 'react-router-dom';
import { Activity, LogOut, Search } from 'lucide-react';
import { NAV_ITEMS } from '../../lib/navigation';
import { cn } from '../../lib/utils';
// sync with SIDEBAR_WIDTH in src/lib/layout.js
// Les classes Tailwind w-[232px] sont conservées statiquement pour le JIT.

/**
 * Sidebar — navigation verticale.
 *
 * Modes :
 *   - desktop : largeur fixe 232px, pas de mode collapsible
 *   - mobile  : rendu par AppShell dans un <Sheet>, prop `mobile` = true
 *
 * Props :
 *   - mobile       : boolean — mode mobile (toujours étendu)
 *   - onItemSelect : callback à appeler lors du clic sur un item (ferme le drawer mobile)
 *   - onLogout     : callback déconnexion
 *   - onSearch     : callback — ouvre la command palette (déclenché par le bouton search)
 *   - badges       : { [badgeKey]: number } — badges numériques sur les items
 */
export function Sidebar({
  onItemSelect,
  onLogout,
  onSearch,
  badges = {},
  mobile = false,
  // Intentionally unused — placeholders for Task 12 (mobile responsive)
  collapsed = false,
  onToggleCollapsed,
}) {
  return (
    <div
      className={cn(
        'flex h-full flex-col bg-surface border-r border-hairline',
        mobile ? 'w-full' : 'w-[232px] flex-shrink-0'
      )}
    >
      {/* Brand — hauteur 52px alignée sur la Topbar */}
      <div className="flex items-center gap-2.5 h-[52px] px-4 border-b border-hairline flex-shrink-0">
        <Activity className="h-4 w-4 text-accent shrink-0" />
        <span className="font-display font-semibold text-[15px] text-ink-0 tracking-tight truncate">
          Crawlee <span className="text-ink-2">Monitor</span>
        </span>
      </div>

      {/* Bouton recherche rapide */}
      <div className="px-3 mt-3 flex-shrink-0">
        <button
          type="button"
          onClick={onSearch}
          className="w-full flex items-center gap-2 px-3 h-8 rounded-md border border-hairline text-[12px] text-ink-3 hover:bg-bg-2 transition-colors"
          aria-label="Rechercher"
        >
          <Search className="h-3.5 w-3.5 shrink-0" />
          <span>Rechercher…</span>
        </button>
      </div>

      {/* Sections de navigation */}
      <nav className="flex-1 overflow-y-auto px-2 py-3">
        {NAV_ITEMS.map((section) => (
          <div key={section.section} className="mb-4 last:mb-0">
            {/* Label de section */}
            <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-ink-2 mb-1 px-2">
              {section.section}
            </div>
            <ul className="space-y-0.5">
              {section.items.map((item) => (
                <SidebarItem
                  key={item.to}
                  to={item.to}
                  label={item.label}
                  icon={item.icon}
                  badge={item.badgeKey ? badges[item.badgeKey] : null}
                  onSelect={onItemSelect}
                />
              ))}
            </ul>
          </div>
        ))}
      </nav>

      {/* Pied de sidebar — déconnexion */}
      <div className="border-t border-hairline p-2 flex-shrink-0">
        <button
          type="button"
          onClick={onLogout}
          className="flex w-full items-center gap-2.5 px-3 py-2 rounded-md text-[13px] text-ink-2 hover:bg-bg-2 hover:text-err transition-colors"
        >
          <LogOut className="h-4 w-4 shrink-0" />
          <span className="truncate">Déconnexion</span>
        </button>
      </div>
    </div>
  );
}

/**
 * SidebarItem — un lien de navigation dans la sidebar.
 *
 * Actif : bg-bg-2 + barre gauche 2px accent + texte ink-0 bold
 * Hover  : bg-bg-2 + texte ink-0
 * Badge  : pastille rouge (bg-err) top-right
 */
function SidebarItem({ to, label, icon: Icon, badge, onSelect }) {
  return (
    <li>
      <NavLink
        to={to}
        end={to === '/'}
        onClick={onSelect}
        className={({ isActive }) =>
          cn(
            'relative flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] transition-colors',
            isActive
              ? 'bg-bg-2 text-ink-0 font-medium before:absolute before:left-0 before:top-1/2 before:-translate-y-1/2 before:h-5 before:w-0.5 before:rounded-full before:bg-accent'
              : 'text-ink-1 hover:bg-bg-2 hover:text-ink-0'
          )
        }
      >
        <Icon className="h-4 w-4 shrink-0" />
        <span className="truncate flex-1">{label}</span>
        {badge != null && badge > 0 && (
          <span className="ml-auto inline-flex items-center justify-center text-[10px] font-semibold tabular-nums bg-err text-white px-1.5 py-0.5 rounded-full leading-none">
            {badge > 99 ? '99+' : badge}
          </span>
        )}
      </NavLink>
    </li>
  );
}
