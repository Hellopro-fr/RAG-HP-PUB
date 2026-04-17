import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { LogOut, Moon, RefreshCw, Sun, Monitor } from 'lucide-react';
import {
  CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem,
  CommandList, CommandSeparator, CommandShortcut,
} from './ui/command';
import { FLAT_NAV } from '../lib/navigation';
import { useTheme } from './providers/ThemeProvider';

/**
 * Global command palette (Cmd+K / Ctrl+K).
 *
 * Navigation items come from the same source as the sidebar (FLAT_NAV), so a
 * new page added to lib/navigation.js appears here automatically.
 *
 * Controlled: AppShell owns the open state so the Topbar button can open it.
 * Cmd+K handling is wired here to keep keyboard concerns with the UI.
 */
export function CommandPalette({ open, onOpenChange, onLogout, onRefresh }) {
  const navigate = useNavigate();
  const { setTheme } = useTheme();

  // Global keyboard: toggle on Cmd+K / Ctrl+K
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        onOpenChange(!open);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onOpenChange]);

  const run = (fn) => {
    onOpenChange(false);
    // Defer so the dialog close animation doesn't race with navigation.
    setTimeout(fn, 0);
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="Tapez une commande ou recherchez une page…" />
      <CommandList>
        <CommandEmpty>Aucun résultat.</CommandEmpty>

        <CommandGroup heading="Navigation">
          {FLAT_NAV.map((item) => {
            const Icon = item.icon;
            return (
              <CommandItem
                key={item.to}
                value={`nav ${item.label} ${item.to} ${item.description || ''}`}
                onSelect={() => run(() => navigate(item.to))}
              >
                {Icon && <Icon className="h-4 w-4" />}
                <span>{item.label}</span>
                {item.description && (
                  <span className="ml-2 truncate text-xs text-muted-foreground">
                    {item.description}
                  </span>
                )}
              </CommandItem>
            );
          })}
        </CommandGroup>

        {(onRefresh || onLogout) && (
          <>
            <CommandSeparator />
            <CommandGroup heading="Actions">
              {onRefresh && (
                <CommandItem
                  value="action refresh rafraichir recharger"
                  onSelect={() => run(onRefresh)}
                >
                  <RefreshCw className="h-4 w-4" />
                  <span>Rafraîchir les données</span>
                </CommandItem>
              )}
              {onLogout && (
                <CommandItem
                  value="action logout deconnexion"
                  onSelect={() => run(onLogout)}
                >
                  <LogOut className="h-4 w-4" />
                  <span>Déconnexion</span>
                </CommandItem>
              )}
            </CommandGroup>
          </>
        )}

        <CommandSeparator />
        <CommandGroup heading="Apparence">
          <CommandItem
            value="theme light clair"
            onSelect={() => run(() => setTheme('light'))}
          >
            <Sun className="h-4 w-4" />
            <span>Thème clair</span>
          </CommandItem>
          <CommandItem
            value="theme dark sombre"
            onSelect={() => run(() => setTheme('dark'))}
          >
            <Moon className="h-4 w-4" />
            <span>Thème sombre</span>
          </CommandItem>
          <CommandItem
            value="theme system systeme auto"
            onSelect={() => run(() => setTheme('system'))}
          >
            <Monitor className="h-4 w-4" />
            <span>Suivre le système</span>
            <CommandShortcut>auto</CommandShortcut>
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
