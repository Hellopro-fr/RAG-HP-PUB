import { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { CheckCircle, XCircle, AlertTriangle, Info, X } from 'lucide-react';
import { cn } from '../lib/utils';

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
 */

const ToastContext = createContext(null);

const TYPE_STYLES = {
  success: { surface: 'border-success/50 bg-success/15 text-success',         Icon: CheckCircle },
  error:   { surface: 'border-destructive/50 bg-destructive/15 text-destructive', Icon: XCircle },
  warn:    { surface: 'border-warning/50 bg-warning/15 text-warning',         Icon: AlertTriangle },
  info:    { surface: 'border-info/50 bg-info/15 text-info',                  Icon: Info },
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
      <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-full max-w-sm flex-col gap-2">
        {toasts.map(t => {
          const { surface, Icon } = TYPE_STYLES[t.type] || TYPE_STYLES.info;
          return (
            <div
              key={t.id}
              role="status"
              className={cn(
                'pointer-events-auto flex items-start gap-3 rounded-md border px-4 py-3 shadow-xl backdrop-blur-sm animate-in slide-in-from-bottom-2',
                surface
              )}
            >
              <Icon className="mt-0.5 h-5 w-5 flex-shrink-0" />
              <div className="flex-1 whitespace-pre-line text-sm">{t.message}</div>
              <button
                onClick={() => dismiss(t.id)}
                className="-mr-1 mt-0.5 opacity-70 hover:opacity-100"
                aria-label="Fermer"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
};

export const useToast = () => {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within <ToastProvider>');
  return ctx;
};

export default ToastProvider;
