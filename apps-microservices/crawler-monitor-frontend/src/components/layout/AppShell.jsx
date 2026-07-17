import { useEffect, useState } from 'react';
import { Sheet, SheetContent, SheetTitle } from '../ui/sheet';
import { CommandPalette } from '../CommandPalette';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';
import { BottomTabBar } from './BottomTabBar';
import { ScrollToTop } from './ScrollToTop';

/**
 * AppShell — layout global : sidebar 232px fixe (desktop) + sheet mobile + topbar 52px.
 *
 * Structure CSS :
 *   flex h-screen overflow-hidden
 *   ├── <Sidebar> 232px (sm+ uniquement)
 *   └── flex flex-col flex-1 min-w-0 overflow-hidden
 *       ├── <Topbar> h-[52px]
 *       └── <main> flex-1 overflow-y-auto p-5 pb-16 sm:pb-5
 *   <BottomTabBar> fixe en bas (mobile uniquement)
 */
export function AppShell({
  children,
  badges = {},
  onLogout,
  onRefresh,
  isRefreshing = false,
  wsConnected = true,
}) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  // Fermer le drawer mobile au passage au breakpoint sm (640px).
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 640px)');
    const handler = (e) => { if (e.matches) setMobileOpen(false); };
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  // Nombre d'alertes pour le badge BottomTabBar (callbacks en échec).
  const alertCount = badges?.failedCallbacks ?? 0;

  return (
    <div className="flex h-screen overflow-hidden bg-bg-1 text-ink-0">
      <ScrollToTop />

      {/* Sidebar desktop — 232px fixe, masquée sous sm (640px) */}
      <aside className="hidden sm:block flex-shrink-0">
        <Sidebar
          onLogout={onLogout}
          onSearch={() => setPaletteOpen(true)}
          badges={badges}
        />
      </aside>

      {/* Sidebar mobile — Sheet slide-in */}
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="w-[232px] p-0">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <Sidebar
            mobile
            onLogout={() => { setMobileOpen(false); onLogout?.(); }}
            onItemSelect={() => setMobileOpen(false)}
            onSearch={() => { setMobileOpen(false); setPaletteOpen(true); }}
            badges={badges}
          />
        </SheetContent>
      </Sheet>

      {/* Colonne principale */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Topbar
          onOpenMobileSidebar={() => setMobileOpen(true)}
          onOpenCommandPalette={() => setPaletteOpen(true)}
          onRefresh={onRefresh}
          isRefreshing={isRefreshing}
          wsConnected={wsConnected}
        />
        {/* pb-16 réserve la hauteur de la BottomTabBar sur mobile */}
        <main className="flex-1 overflow-y-auto p-5 pb-16 sm:pb-5">
          {children}
        </main>
      </div>

      {/* Barre de navigation fixe en bas — mobile uniquement */}
      <BottomTabBar alertCount={alertCount} />

      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        onLogout={onLogout}
        onRefresh={onRefresh}
      />
    </div>
  );
}
