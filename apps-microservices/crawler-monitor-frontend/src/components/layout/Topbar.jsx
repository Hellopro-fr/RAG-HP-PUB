import { Menu, RefreshCw, Search } from 'lucide-react';
import { Button } from '../ui/button';
import { Breadcrumbs } from './Breadcrumbs';
import { ThemeToggle } from '../ThemeToggle';
import { cn } from '../../lib/utils';

/**
 * Topbar — sticky header above the routed content.
 *
 * Layout (left → right):
 *   [mobile sidebar trigger] · Breadcrumbs · (spacer) · Cmd+K · Refresh · Theme
 */
export function Topbar({
  onOpenMobileSidebar,
  onOpenCommandPalette,
  onRefresh,
  isRefreshing = false,
}) {
  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-border bg-background/80 px-3 backdrop-blur supports-[backdrop-filter]:bg-background/60 sm:px-4">
      {/* Mobile: open sidebar */}
      <Button
        variant="ghost"
        size="icon"
        className="lg:hidden shrink-0"
        aria-label="Ouvrir la navigation"
        onClick={onOpenMobileSidebar}
      >
        <Menu className="h-5 w-5" />
      </Button>

      <div className="flex-1 min-w-0">
        <Breadcrumbs />
      </div>

      <div className="flex items-center gap-1 shrink-0">
        {onOpenCommandPalette && (
          <button
            type="button"
            onClick={onOpenCommandPalette}
            className="hidden md:inline-flex h-8 items-center gap-2 rounded-md border border-input bg-background px-2.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            aria-label="Ouvrir la palette de commandes"
          >
            <Search className="h-3.5 w-3.5" />
            <span>Rechercher…</span>
            <kbd className="ml-2 inline-flex items-center gap-0.5 rounded border border-border bg-muted px-1 font-mono text-[10px] text-muted-foreground">
              <span className="text-[11px] leading-none">⌘</span>K
            </kbd>
          </button>
        )}
        {/* Mobile: icon-only command trigger */}
        {onOpenCommandPalette && (
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            aria-label="Rechercher"
            onClick={onOpenCommandPalette}
          >
            <Search className="h-4 w-4" />
          </Button>
        )}
        {onRefresh && (
          <Button
            variant="ghost"
            size="icon"
            aria-label="Rafraîchir"
            onClick={onRefresh}
            title="Rafraîchir"
          >
            <RefreshCw className={cn('h-4 w-4', isRefreshing && 'animate-spin')} />
          </Button>
        )}
        <ThemeToggle />
      </div>
    </header>
  );
}
