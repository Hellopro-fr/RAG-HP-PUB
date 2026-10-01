import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from '../src/App.jsx';

// --- Mocks posés AVANT l'import de App -------------------------------------

// Overview tire tout le dashboard (Recharts, react-window…) : inutile ici.
vi.mock('../src/pages/Overview', () => ({ default: () => <div>overview</div> }));

// AppShell (Sidebar/Topbar/CommandPalette) → passe-plat instrumenté : on expose
// l'état du WS et trois boutons de navigation pour rejouer un changement de
// route sans monter les pages lazy.
vi.mock('../src/components/layout/AppShell', async () => {
  const { useNavigate } = await vi.importActual('react-router-dom');
  const AppShell = ({ children, wsConnected }) => {
    const navigate = useNavigate();
    return (
      <div data-testid="shell">
        <span data-testid="ws-state">{wsConnected ? 'online' : 'offline'}</span>
        <button data-testid="nav-1" onClick={() => navigate('/jobs/a')}>1</button>
        <button data-testid="nav-2" onClick={() => navigate('/jobs/b')}>2</button>
        <button data-testid="nav-3" onClick={() => navigate('/')}>3</button>
        {children}
      </div>
    );
  };
  return { AppShell };
});

// CoherenceProvider → passe-plat (le contexte reste exporté pour hooks.js).
vi.mock('../src/coherence/CoherenceProvider', () => ({
  CoherenceProvider: ({ children }) => <>{children}</>,
}));

// On garde useWsInvalidator réel (c'est lui qui coalesce) mais on neutralise
// les deux queries que App monte au démarrage.
vi.mock('../src/hooks/queries', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    useCallbacksQuery: () => ({ data: undefined, refetch: vi.fn() }),
    useSystemHealthQuery: () => ({ data: undefined }),
  };
});

// --- WebSocket factice ------------------------------------------------------

class MockWebSocket {
  static instances = [];
  constructor(url) {
    this.url = url;
    this.readyState = 0;
    this.onopen = null;
    this.onmessage = null;
    this.onclose = null;
    MockWebSocket.instances.push(this);
  }
  close() {
    this.readyState = 3;
    this.onclose?.({ code: 1000 });
  }
  /** Simule une fermeture côté serveur. */
  serverClose(code) {
    this.readyState = 3;
    this.onclose?.({ code });
  }
}

const renderApp = () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={['/']}>
      <QueryClientProvider client={qc}>
        <App />
      </QueryClientProvider>
    </MemoryRouter>,
  );
};

const lastWs = () => MockWebSocket.instances[MockWebSocket.instances.length - 1];

beforeEach(() => {
  MockWebSocket.instances = [];
  globalThis.WebSocket = MockWebSocket;
  localStorage.setItem('authToken', 'jwt-de-test');
  vi.useFakeTimers();
  vi.spyOn(console, 'log').mockImplementation(() => {});
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  localStorage.clear();
});

describe('App — cycle de vie du WebSocket', () => {
  it('ne logge jamais le JWT en clair', () => {
    renderApp();
    const logged = console.log.mock.calls.flat().join(' ');
    expect(logged).not.toContain('jwt-de-test');
    // L'URL réellement ouverte porte bien le token (c'est le log qui est masqué).
    expect(lastWs().url).toContain('token=jwt-de-test');
  });

  it('déconnecte immédiatement sur une fermeture 1008 (token refusé)', () => {
    renderApp();
    expect(MockWebSocket.instances).toHaveLength(1);

    act(() => { lastWs().serverClose(1008); });

    expect(localStorage.getItem('authToken')).toBeNull();
    // Aucune tentative de reconnexion programmée
    act(() => { vi.advanceTimersByTime(60_000); });
    expect(MockWebSocket.instances).toHaveLength(1);
  });

  it('5 fermetures 1006 consécutives ne déconnectent PAS (redéploiement backend)', () => {
    const { getByTestId } = renderApp();

    // Un redéploiement du backend enchaîne les 1006 pendant quelques secondes :
    // l'opérateur doit rester loggué et la reconnexion doit continuer.
    for (let i = 0; i < 5; i++) {
      act(() => { lastWs().serverClose(1006); });
      expect(localStorage.getItem('authToken')).toBe('jwt-de-test');
      act(() => { vi.advanceTimersByTime(60_000); }); // couvre tout le backoff (max 30s)
    }

    // 5 reconnexions programmées + la socket initiale.
    expect(MockWebSocket.instances).toHaveLength(6);
    // Session intacte ; seul le badge passe hors ligne (fallback REST 15s).
    expect(getByTestId('shell')).toBeInTheDocument();
    expect(getByTestId('ws-state').textContent).toBe('offline');
  });

  it('une reconnexion réussie remet le backoff à zéro', () => {
    renderApp();

    act(() => { lastWs().serverClose(1006); });
    act(() => { vi.advanceTimersByTime(1000); });
    act(() => { lastWs().onopen?.(); });          // connexion établie
    act(() => { lastWs().serverClose(1006); });   // puis coupure réseau
    // Backoff remis à zéro : la tentative suivante repart à 1s, pas à 2s.
    act(() => { vi.advanceTimersByTime(1000); });
    expect(MockWebSocket.instances).toHaveLength(3);
    expect(localStorage.getItem('authToken')).toBe('jwt-de-test');
  });

  it('3 navigations ne rouvrent pas la socket (handleLogout lu via un ref)', () => {
    const { getByTestId } = renderApp();
    expect(MockWebSocket.instances).toHaveLength(1);

    // `handleLogout` change d'identité à chaque navigation ; s'il restait en
    // dépendance de l'effet WS, chaque changement de route fermerait puis
    // rouvrirait la socket.
    act(() => { getByTestId('nav-1').click(); });
    act(() => { getByTestId('nav-2').click(); });
    act(() => { getByTestId('nav-3').click(); });

    expect(MockWebSocket.instances).toHaveLength(1);
  });
});
