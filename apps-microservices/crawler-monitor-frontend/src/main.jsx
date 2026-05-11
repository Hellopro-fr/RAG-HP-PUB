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
      retry: 1,                    // one retry on failure
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
          <BrowserRouter>
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
