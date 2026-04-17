import { NavLink } from 'react-router-dom';
import { Activity, ChevronsLeft, ChevronsRight, LogOut } from 'lucide-react';
import { NAV_ITEMS } from '../../lib/navigation';
import { cn } from '../../lib/utils';
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip';

/**
 * Sidebar — vertical navigation.
 *
 * Two display modes:
 *   - desktop collapsible: fixed column that shrinks to icons-only
 *   - mobile drawer (passed via `mobile` prop): always expanded, rendered by
 *     AppShell inside a <Sheet> so it slides in from the left
 *
 * The `badges` prop lets the parent inject numeric cues onto items
 * (e.g. { failedCallbacks: 3 } → red dot on the Callbacks row).
 */
export function Sidebar({
  collapsed = false,
  onToggleCollapsed,
  onItemSelect,
  onLogout,
  badges = {},
  mobile = false,
}) {
  const showLabels = mobile || !collapsed;

  return (
    <div
      className={cn(
        'flex h-full flex-col border-r border-border bg-card text-card-foreground',
        mobile ? 'w-full' : (collapsed ? 'w-14' : 'w-60'),
        'transition-[width] duration-150'
      )}
    >
      {/* Brand */}
      <div
        className={cn(
          'flex items-center gap-2 border-b border-border px-3',
          mobile ? 'h-14' : 'h-14',
          showLabels ? 'justify-start' : 'justify-center'
        )}
      >
        <Activity className="h-5 w-5 text-primary shrink-0" />
        {showLabels && (
          <span className="truncate text-sm font-semibold tracking-tight">
            Crawlee Monitor
          </span>
        )}
      </div>

      {/* Nav sections */}
      <nav className="flex-1 overflow-y-auto px-2 py-3">
        {NAV_ITEMS.map((section) => (
          <div key={section.section} className="mb-4 last:mb-0">
            {showLabels && (
              <div className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                {section.section}
              </div>
            )}
            <ul className="space-y-0.5">
              {section.items.map((item) => (
                <SidebarItem
                  key={item.to}
                  to={item.to}
                  label={item.label}
                  icon={item.icon}
                  badge={item.badgeKey ? badges[item.badgeKey] : null}
                  description={item.description}
                  collapsed={!showLabels}
                  onSelect={onItemSelect}
                />
              ))}
            </ul>
          </div>
        ))}
      </nav>

      {/* Footer: logout + collapse toggle */}
      <div className="border-t border-border p-2 space-y-1">
        <SidebarButton
          icon={LogOut}
          label="Déconnexion"
          onClick={onLogout}
          collapsed={!showLabels}
          danger
        />
        {!mobile && onToggleCollapsed && (
          <SidebarButton
            icon={collapsed ? ChevronsRight : ChevronsLeft}
            label={collapsed ? 'Déplier' : 'Replier'}
            onClick={onToggleCollapsed}
            collapsed={collapsed}
          />
        )}
      </div>
    </div>
  );
}

function SidebarItem({ to, label, icon: Icon, badge, description, collapsed, onSelect }) {
  const content = (
    <NavLink
      to={to}
      end={to === '/'}
      onClick={onSelect}
      className={({ isActive }) =>
        cn(
          'group relative flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors',
          collapsed && 'justify-center',
          isActive
            ? 'bg-accent text-accent-foreground font-medium'
            : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground'
        )
      }
    >
      <Icon className="h-4 w-4 shrink-0" />
      {!collapsed && <span className="truncate">{label}</span>}
      {badge != null && badge > 0 && (
        <span
          className={cn(
            'ml-auto inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-bold text-destructive-foreground',
            collapsed && 'absolute top-1 right-1 h-1.5 w-1.5 min-w-0 p-0'
          )}
        >
          {!collapsed && (badge > 99 ? '99+' : badge)}
        </span>
      )}
    </NavLink>
  );

  if (collapsed) {
    return (
      <li>
        <Tooltip>
          <TooltipTrigger asChild>{content}</TooltipTrigger>
          <TooltipContent side="right" className="max-w-xs">
            <div className="font-medium">{label}</div>
            {description && (
              <div className="mt-0.5 text-xs text-muted-foreground">{description}</div>
            )}
          </TooltipContent>
        </Tooltip>
      </li>
    );
  }

  return <li>{content}</li>;
}

function SidebarButton({ icon: Icon, label, onClick, collapsed, danger = false }) {
  const btn = (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors',
        collapsed && 'justify-center',
        danger
          ? 'text-muted-foreground hover:bg-destructive/10 hover:text-destructive'
          : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground'
      )}
    >
      <Icon className="h-4 w-4 shrink-0" />
      {!collapsed && <span className="truncate">{label}</span>}
    </button>
  );

  if (collapsed) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>{btn}</TooltipTrigger>
        <TooltipContent side="right">{label}</TooltipContent>
      </Tooltip>
    );
  }
  return btn;
}
