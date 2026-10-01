import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import ToastProvider from './components/ToastProvider.jsx'
import { ThemeProvider } from './components/providers/ThemeProvider.jsx'
import { TooltipProvider } from './components/ui/tooltip'
import { ApiError } from './lib/api'
import { tryAutoReloadOnStaleChunk, clearStaleChunkReloadFlag } from './lib/staleChunk'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Keep data visible even when stale; refetch in background.
      // Most data is also pushed via WebSocket (job_update), so manual refetch
      // intervals are unnecessary. WS handlers will invalidate queries.
      staleTime: 30 * 1000,        // 30s before considered stale
      gcTime:    5 * 60 * 1000,    // 5min cache retention after unmount
      refetchOnWindowFocus: false, // dashboard is already live via WS
      // Un ApiError est une réponse HTTP typée : les 4xx ne guériront pas d'un
      // retry, et les 5xx ont déjà été rejoués par lib/api. On ne rejoue donc
      // ici que les échecs non typés (réseau/parse), une seule fois.
      retry: (failureCount, error) => failureCount < 1 && !(error instanceof ApiError),
    },
  },
})

// Intercepter les rejets de promesses non catches (echecs import() lazy()).
// Les chunks charges via React.lazy() peuvent echouer AVANT d'atteindre l'ErrorBoundary
// car le rejet se propage en unhandledrejection. On le capture ici en premier.
window.addEventListener('unhandledrejection', (event) => {
  if (tryAutoReloadOnStaleChunk(event.reason)) {
    // Eviter la pollution de la console si le rechargement est en cours
    event.preventDefault();
  }
});

// Apres 5s de fonctionnement normal, effacer le flag de tentative de rechargement.
// Si la page s'est rechargee et que tout fonctionne, le compteur est remis a zero
// pour ne pas bloquer une eventuelle vraie erreur future.
setTimeout(clearStaleChunkReloadFlag, 5000);

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ErrorBoundary>
      <ThemeProvider defaultTheme="system">
        <QueryClientProvider client={queryClient}>
          {/* Future flags v7 : opt-in explicite pour lever les 2 avertissements
              console de react-router 6 et aligner le comportement sur v7. */}
          <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
            <TooltipProvider delayDuration={200}>
              <ToastProvider>
                <App />
              </ToastProvider>
            </TooltipProvider>
          </BrowserRouter>
        </QueryClientProvider>
      </ThemeProvider>
    </ErrorBoundary>
  </StrictMode>,
)
