import { useState, useEffect, useRef } from 'react';
import { AlertTriangle, XCircle } from 'lucide-react';

/**
 * Type-to-confirm modal for destructive actions.
 * Requires user to type BOTH a short-id AND a confirmation word ("DROP" by default).
 *
 * Props:
 *   - open: bool
 *   - title: string                       e.g. "Drop entire queue"
 *   - description: ReactNode              full context (what gets deleted, count, irreversibility)
 *   - shortId: string                     identifier the user must retype (e.g. job c8f2)
 *   - confirmWord?: string                default 'DROP', case-sensitive
 *   - onConfirm: () => Promise<void>|void
 *   - onCancel: () => void
 *   - busy?: bool                         disables button + shows "En cours..."
 */
const ConfirmDestructive = ({
  open,
  title,
  description,
  shortId,
  confirmWord = 'DROP',
  onConfirm,
  onCancel,
  busy = false,
}) => {
  const [typedId, setTypedId] = useState('');
  const [typedWord, setTypedWord] = useState('');
  const idRef = useRef(null);

  useEffect(() => {
    if (open) {
      setTypedId('');
      setTypedWord('');
      // Defer focus until after render
      setTimeout(() => idRef.current?.focus(), 50);
    }
  }, [open]);

  if (!open) return null;
  const ready = typedId.trim() === shortId && typedWord.trim() === confirmWord;

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[60] p-4">
      <div className="bg-gray-800 rounded-lg shadow-xl w-full max-w-lg border border-red-500/30">
        <div className="flex justify-between items-center p-4 border-b border-gray-700">
          <h3 className="text-lg font-bold text-red-400 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5" /> {title}
          </h3>
          <button
            onClick={onCancel}
            className="text-gray-400 hover:text-white disabled:opacity-50"
            disabled={busy}
            title="Annuler"
          >
            <XCircle className="w-5 h-5" />
          </button>
        </div>
        <div className="p-5 space-y-4">
          <div className="text-sm text-gray-300">{description}</div>
          <div className="space-y-2">
            <label className="text-xs text-gray-400 block">
              Tape l&apos;identifiant <code className="text-orange-300">{shortId}</code> :
            </label>
            <input
              ref={idRef}
              value={typedId}
              onChange={e => setTypedId(e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-red-500 focus:outline-none"
              placeholder={shortId}
              disabled={busy}
              autoComplete="off"
              spellCheck={false}
            />
          </div>
          <div className="space-y-2">
            <label className="text-xs text-gray-400 block">
              Tape <code className="text-orange-300">{confirmWord}</code> en majuscules :
            </label>
            <input
              value={typedWord}
              onChange={e => setTypedWord(e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-red-500 focus:outline-none"
              placeholder={confirmWord}
              disabled={busy}
              autoComplete="off"
              spellCheck={false}
            />
          </div>
          <div className="text-[11px] text-gray-500 italic">
            Cette action est tracée dans l&apos;audit log.
          </div>
        </div>
        <div className="flex gap-2 justify-end p-4 border-t border-gray-700">
          <button
            onClick={onCancel}
            disabled={busy}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm disabled:opacity-50"
          >
            Annuler
          </button>
          <button
            onClick={onConfirm}
            disabled={!ready || busy}
            className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-gray-700 disabled:cursor-not-allowed rounded text-sm font-semibold text-white"
          >
            {busy ? 'En cours…' : title}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmDestructive;