import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import ToastProvider from './components/ToastProvider.jsx'

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

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <ToastProvider>
            <App />
          </ToastProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
)