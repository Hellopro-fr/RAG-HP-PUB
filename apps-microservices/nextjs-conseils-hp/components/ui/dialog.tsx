'use client';

import * as DialogPrimitive from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Primitive Dialog (Radix) — premier composant de `components/ui/`.
 *
 * Écrite à la main plutôt que générée par `npx shadcn add dialog` : la CLI
 * réécrit `components.json`, `globals.css` et peut réinstaller des dépendances,
 * ce qui toucherait aux tokens conseils. Ici on garde le contrat d'API shadcn
 * (mêmes noms exportés) sans effet de bord sur le reste du service.
 *
 * ⚠️ Ne pas éditer pour un besoin ponctuel : créer un wrapper dans
 * `components/hub/` (cf. CLAUDE.md §7.3).
 */
// `Trigger` et `Close` de Radix ne sont pas réexportés : les 3 dialogs du HUB
// sont pilotés par événement `window`, et la croix de fermeture est rendue par
// `DialogContent` lui-même. Les ajouter « pour l'API complète » créerait des
// exports que personne n'importe.
const Dialog = DialogPrimitive.Root;
const DialogPortal = DialogPrimitive.Portal;

function DialogOverlay({ className, ...props }: React.ComponentProps<typeof DialogPrimitive.Overlay>) {
  return (
    <DialogPrimitive.Overlay
      className={cn(
        'fixed inset-0 z-50 bg-black/60 backdrop-blur-sm',
        'data-[state=open]:animate-in data-[state=closed]:animate-out',
        'data-[state=open]:fade-in-0 data-[state=closed]:fade-out-0',
        className
      )}
      {...props}
    />
  );
}

function DialogContent({
  className,
  children,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Content>) {
  return (
    <DialogPortal>
      <DialogOverlay />
      <DialogPrimitive.Content
        // Un clic à l'extérieur NE FERME PAS le dialog (formulaires lead : éviter
        // la perte de saisie). La croix et la touche Échap restent actives.
        // Un consommateur peut réactiver la fermeture en passant sa propre prop.
        onPointerDownOutside={(event) => event.preventDefault()}
        className={cn(
          'fixed left-1/2 top-1/2 z-50 w-[calc(100vw-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2',
          'max-h-[calc(100vh-2rem)] overflow-y-auto rounded-2xl border border-border bg-card shadow-elegant',
          'data-[state=open]:animate-in data-[state=closed]:animate-out',
          'data-[state=open]:fade-in-0 data-[state=closed]:fade-out-0',
          'data-[state=open]:zoom-in-95 data-[state=closed]:zoom-out-95',
          className
        )}
        {...props}
      >
        {children}
        <DialogPrimitive.Close
          aria-label="Fermer"
          className="absolute right-4 top-4 rounded-full p-1.5 text-muted-foreground transition hover:bg-muted hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <X className="h-4 w-4" />
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPortal>
  );
}

function DialogHeader({ className, ...props }: React.ComponentProps<'div'>) {
  return <div className={cn('flex flex-col gap-1.5', className)} {...props} />;
}

function DialogTitle({ className, ...props }: React.ComponentProps<typeof DialogPrimitive.Title>) {
  return (
    <DialogPrimitive.Title
      className={cn('text-lg font-bold leading-tight text-foreground', className)}
      {...props}
    />
  );
}

function DialogDescription({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Description>) {
  return (
    <DialogPrimitive.Description
      className={cn('text-sm text-muted-foreground', className)}
      {...props}
    />
  );
}

export { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription };
