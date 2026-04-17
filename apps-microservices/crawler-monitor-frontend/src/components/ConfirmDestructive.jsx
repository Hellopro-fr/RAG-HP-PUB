import { useState, useEffect, useRef } from 'react';
import { AlertTriangle } from 'lucide-react';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from './ui/dialog';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';

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
      setTimeout(() => idRef.current?.focus(), 50);
    }
  }, [open]);

  const ready = typedId.trim() === shortId && typedWord.trim() === confirmWord;

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next && !busy) onCancel(); }}>
      <DialogContent className="max-w-lg border-destructive/40">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="h-5 w-5" /> {title}
          </DialogTitle>
          <DialogDescription asChild>
            <div className="pt-1 text-sm text-foreground">{description}</div>
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="confirm-id" className="text-xs text-muted-foreground">
              Tape l&apos;identifiant{' '}
              <code className="rounded bg-muted px-1 py-0.5 text-warning">{shortId}</code> :
            </Label>
            <Input
              id="confirm-id"
              ref={idRef}
              value={typedId}
              onChange={e => setTypedId(e.target.value)}
              placeholder={shortId}
              disabled={busy}
              autoComplete="off"
              spellCheck={false}
              className="font-mono"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="confirm-word" className="text-xs text-muted-foreground">
              Tape <code className="rounded bg-muted px-1 py-0.5 text-warning">{confirmWord}</code> en majuscules :
            </Label>
            <Input
              id="confirm-word"
              value={typedWord}
              onChange={e => setTypedWord(e.target.value)}
              placeholder={confirmWord}
              disabled={busy}
              autoComplete="off"
              spellCheck={false}
              className="font-mono"
            />
          </div>
          <div className="text-[11px] italic text-muted-foreground">
            Cette action est tracée dans l&apos;audit log.
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCancel} disabled={busy}>
            Annuler
          </Button>
          <Button variant="destructive" onClick={onConfirm} disabled={!ready || busy}>
            {busy ? 'En cours…' : title}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ConfirmDestructive;
