import { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { CheckCircle, XCircle, AlertTriangle, Info, X } from 'lucide-react';

/**
 * Toast system — centralized, fire-and-forget user feedback.
 *
 * Usage:
 *   const toast = useToast();
 *   toast.success('Saved');
 *   toast.error('Failed: ' + err.message);
 *   toast.warn('Capacity reaching limit');
 *   toast.info('Background job queued');
 *
 *   // or with options:
 *   toast.show({ type: 'success', message: '...', durationMs: 3000 });
 *
 * Existing inline status divs (RequestQueueEditor, DatasetAnalyzer, CallbacksPanel)
 * are NOT migrated yet to avoid scope creep — they keep working.
 * New code should prefer useToast().
 */

const ToastContext = createContext(null);

const TYPE_STYLES = {
  success: { bg: 'bg-green-900/80 border-green-500/50', text: 'text-green-200', Icon: CheckCircle },
  error:   { bg: 'bg-red-900/80 border-red-500/50',     text: 'text-red-200',   Icon: XCircle },
  warn:    { bg: 'bg-orange-900/80 border-orange-500/50', text: 'text-orange-200', Icon: AlertTriangle },
  info:    { bg: 'bg-blue-900/80 border-blue-500/50',   text: 'text-blue-200',  Icon: Info },
};

let _idCounter = 0;

export const ToastProvider = ({ children }) => {
  const [toasts, setToasts] = useState([]);

  const dismiss = useCallback((id) => {
    setToasts(curr => curr.filter(t => t.id !== id));
  }, []);

  const show = useCallback((opts) => {
    const id = ++_idCounter;
    const type = opts.type || 'info';
    const message = opts.message || '';
    const durationMs = opts.durationMs ?? (type === 'error' ? 6000 : 3500);
    setToasts(curr => [...curr, { id, type, message, durationMs }]);
    return id;
  }, []);

  // Auto-dismiss timers
  useEffect(() => {
    if (toasts.length === 0) return undefined;
    const timers = toasts.map(t =>
      setTimeout(() => dismiss(t.id), t.durationMs)
    );
    return () => timers.forEach(clearTimeout);
  }, [toasts, dismiss]);

  const apiValue = {
    show,
    success: (message, opts = {}) => show({ ...opts, type: 'success', message }),
    error:   (message, opts = {}) => show({ ...opts, type: 'error',   message }),
    warn:    (message, opts = {}) => show({ ...opts, type: 'warn',    message }),
    info:    (message, opts = {}) => show({ ...opts, type: 'info',    message }),
    dismiss,
  };

  return (
    <ToastContext.Provider value={apiValue}>
      {children}
      <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none max-w-sm w-full">
        {toasts.map(t => {
          const { bg, text, Icon } = TYPE_STYLES[t.type] || TYPE_STYLES.info;
          return (
            <div
              key={t.id}
              role="status"
              className={`pointer-events-auto flex items-start gap-3 px-4 py-3 rounded-lg shadow-xl border ${bg} ${text} backdrop-blur-sm animate-in slide-in-from-bottom-2`}
            >
              <Icon className="w-5 h-5 flex-shrink-0 mt-0.5" />
              <div className="flex-1 text-sm whitespace-pre-line">{t.message}</div>
              <button
                onClick={() => dismiss(t.id)}
                className="text-gray-400 hover:text-white -mr-1 mt-0.5"
                aria-label="Fermer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
};

/** Returns { show, success, error, warn, info, dismiss }. Throws if outside ToastProvider. */
export const useToast = () => {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within <ToastProvider>');
  return ctx;
};

export default ToastProvider;