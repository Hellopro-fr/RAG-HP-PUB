import { useEffect, useState } from 'react';
import { Sheet, SheetContent, SheetTitle } from '../ui/sheet';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';

const COLLAPSED_KEY = 'sidebar:collapsed';

/**
 * AppShell — persistent sidebar (desktop) + slide-in drawer (mobile) + topbar.
 *
 * Kept as a layout wrapper (not a router layout route) to preserve App.jsx's
 * existing auth gate and top-level state (token, replicas, WebSocket).
 */
export function AppShell({
  children,
  badges = {},
  onLogout,
  onRefresh,
  isRefreshing = false,
  onOpenCommandPalette,
}) {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(COLLAPSED_KEY) === '1';
    } catch {
      return false;
    }
  });
  const [mobileOpen, setMobileOpen] = useState(false);

  const toggleCollapsed = () => {
    setCollapsed((c) => {
      const next = !c;
      try { localStorage.setItem(COLLAPSED_KEY, next ? '1' : '0'); } catch { /* noop */ }
      return next;
    });
  };

  // Close mobile drawer on resize to desktop breakpoint (Tailwind lg = 1024px).
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 1024px)');
    const handler = (e) => { if (e.matches) setMobileOpen(false); };
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="flex min-h-screen">
        {/* Desktop sidebar */}
        <aside className="hidden lg:block sticky top-0 h-screen shrink-0">
          <Sidebar
            collapsed={collapsed}
            onToggleCollapsed={toggleCollapsed}
            onLogout={onLogout}
            badges={badges}
          />
        </aside>

        {/* Mobile sidebar (Sheet) */}
        <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetContent side="left" className="w-64 p-0">
            <SheetTitle className="sr-only">Navigation</SheetTitle>
            <Sidebar
              mobile
              onLogout={() => { setMobileOpen(false); onLogout?.(); }}
              onItemSelect={() => setMobileOpen(false)}
              badges={badges}
            />
          </SheetContent>
        </Sheet>

        {/* Main column */}
        <div className="flex flex-1 min-w-0 flex-col">
          <Topbar
            onOpenMobileSidebar={() => setMobileOpen(true)}
            onOpenCommandPalette={onOpenCommandPalette}
            onRefresh={onRefresh}
            isRefreshing={isRefreshing}
          />
          <main className="flex-1 min-w-0">
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
