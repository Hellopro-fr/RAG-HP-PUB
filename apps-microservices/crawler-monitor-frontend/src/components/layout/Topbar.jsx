import { Menu, RefreshCw, Search } from 'lucide-react';
import { Button } from '../ui/button';
import { Breadcrumbs } from './Breadcrumbs';
import { ThemeToggle } from '../ThemeToggle';
import { cn } from '../../lib/utils';

// Détection plateforme : Ctrl+K sur Windows/Linux, ⌘K sur macOS.
const isMac =
  typeof navigator !== 'undefined' &&
  /Mac|iPhone|iPod|iPad/.test(navigator.platform || navigator.userAgent || '');

/**
 * Topbar — barre fixe en haut de la colonne principale.
 *
 * Hauteur : 52px (alignée sur le brand de la Sidebar).
 * Layout (gauche → droite) :
 *   [burger mobile] · Breadcrumbs · (spacer) · Badge Live · Cmd+K · Refresh · ThemeToggle
 */
export function Topbar({
  onOpenMobileSidebar,
  onOpenCommandPalette,
  onRefresh,
  isRefreshing = false,
  wsConnected = true,
}) {
  return (
    <header className="h-[52px] flex-shrink-0 flex items-center px-5 border-b border-hairline bg-surface gap-4">
      {/* Bouton burger — mobile uniquement */}
      <Button
        variant="ghost"
        size="icon"
        className="sm:hidden shrink-0 hover:bg-bg-2 hover:text-ink-0"
        aria-label="Ouvrir la navigation"
        onClick={onOpenMobileSidebar}
      >
        <Menu className="h-5 w-5" />
      </Button>

      {/* Breadcrumbs — prennent l'espace restant */}
      <div className="flex-1 min-w-0">
        <Breadcrumbs />
      </div>

      {/* Actions à droite */}
      <div className="flex items-center gap-1 shrink-0">
        {/* État de la liaison temps réel (WebSocket) */}
        <span
          className={cn(
            'hidden sm:inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium',
            wsConnected
              ? 'border-ok/30 bg-ok-soft text-ok'
              : 'border-err/30 bg-err-soft text-err',
          )}
          title={wsConnected ? 'Temps réel actif (WebSocket connecté)' : 'Temps réel interrompu — données rafraîchies toutes les 15s, reconnexion en cours'}
        >
          <span className={cn('h-1.5 w-1.5 rounded-full', wsConnected ? 'bg-ok animate-pulse' : 'bg-err')} />
          {wsConnected ? 'Live' : 'Hors ligne'}
        </span>

        {/* Bouton Cmd+K — desktop */}
        {onOpenCommandPalette && (
          <button
            type="button"
            onClick={onOpenCommandPalette}
            className="hidden md:inline-flex h-8 items-center gap-2 rounded-md border border-hairline bg-surface px-2.5 text-[12px] text-ink-3 transition-colors hover:bg-bg-2 hover:text-ink-0"
            aria-label="Ouvrir la palette de commandes"
          >
            <Search className="h-3.5 w-3.5 shrink-0" />
            <span>Rechercher…</span>
            <kbd className="ml-2 inline-flex items-center gap-0.5 rounded border border-hairline bg-bg-2 px-1 font-mono text-[10px] text-ink-2">
              {isMac ? (
                <>
                  <span className="text-[11px] leading-none">⌘</span>K
                </>
              ) : (
                'Ctrl+K'
              )}
            </kbd>
          </button>
        )}

        {/* Bouton Cmd+K — mobile (icône seule) */}
        {onOpenCommandPalette && (
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden hover:bg-bg-2 hover:text-ink-0"
            aria-label="Rechercher"
            onClick={onOpenCommandPalette}
          >
            <Search className="h-4 w-4" />
          </Button>
        )}

        {/* Bouton rafraîchir */}
        {onRefresh && (
          <Button
            variant="ghost"
            size="icon"
            aria-label="Rafraîchir"
            onClick={onRefresh}
            title="Rafraîchir"
            className="hover:bg-bg-2 hover:text-ink-0"
          >
            <RefreshCw className={cn('h-4 w-4', isRefreshing && 'animate-spin')} />
          </Button>
        )}

        {/* Bascule thème clair/sombre */}
        <ThemeToggle />
      </div>
    </header>
  );
}
