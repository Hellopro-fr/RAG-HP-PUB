import { useEffect, useState } from 'react';
import { Sheet, SheetContent, SheetTitle } from '../ui/sheet';
import { CommandPalette } from '../CommandPalette';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';
import { ScrollToTop } from './ScrollToTop';

/**
 * AppShell — layout global : sidebar 232px fixe (desktop) + sheet mobile + topbar 52px.
 *
 * Structure CSS :
 *   flex h-screen overflow-hidden
 *   ├── <Sidebar> 232px (desktop uniquement)
 *   └── flex flex-col flex-1 min-w-0 overflow-hidden
 *       ├── <Topbar> h-[52px]
 *       └── <main> flex-1 overflow-y-auto p-5
 */
export function AppShell({
  children,
  badges = {},
  onLogout,
  onRefresh,
  isRefreshing = false,
}) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  // Fermer le drawer mobile au passage au breakpoint lg (1024px).
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 1024px)');
    const handler = (e) => { if (e.matches) setMobileOpen(false); };
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-bg-1 text-ink-0">
      <ScrollToTop />

      {/* Sidebar desktop — 232px fixe, masquée sur mobile */}
      <aside className="hidden lg:block flex-shrink-0">
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
        />
        <main className="flex-1 overflow-y-auto p-5">
          {children}
        </main>
      </div>

      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        onLogout={onLogout}
        onRefresh={onRefresh}
      />
    </div>
  );
}
