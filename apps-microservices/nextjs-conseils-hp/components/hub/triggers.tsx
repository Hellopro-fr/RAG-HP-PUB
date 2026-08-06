'use client';

import { HubIcon } from './primitives';
import { openAssistantDialog } from './AssistantForm';
import { openGuideDialog } from './GuideDownloadDialog';
import type { HubEntryPoint } from '@/lib/analytics/hub';
import type { HubIconName } from '@/types/hub';

/**
 * Boutons déclencheurs des dialogs.
 *
 * Pourquoi des composants à part : les sections (`ThematiqueBloc`, `Banners`,
 * `RessourcesGrid`, `FinalCta`) sont des Server Components. Isoler le `onClick`
 * dans ces petits composants client garde les sections côté serveur — seul le
 * bouton est hydraté, pas la section entière. C'est ce qui évite de faire
 * basculer toute la page en client pour trois boutons.
 *
 * Le dialog ciblé est joint par un événement window, pas par une prop : un
 * Server Component ne peut pas passer de callback à un enfant client.
 */

interface TriggerProps {
  label: string;
  icon?: HubIconName;
  /**
   * `solid` = aplat orange (CTA principal), `outline` = bordure (CTA secondaire),
   * `link` = lien inline, `row` = ligne pleine largeur libellé ↔ flèche
   * (bas de carte informative).
   */
  variant?: 'solid' | 'outline' | 'link' | 'row' | 'soft';
  /**
   * Côté de l'icône. `start` pour une icône de sens (télécharger), `end` pour une
   * flèche de progression. Explicite plutôt que déduit du nom de l'icône.
   */
  iconPosition?: 'start' | 'end';
  className?: string;
}

const VARIANTS: Record<NonNullable<TriggerProps['variant']>, string> = {
  solid:
    'h-11 rounded-lg bg-cta px-5 text-sm font-semibold text-cta-foreground shadow-cta hover:bg-cta-hover',
  outline:
    'h-12 rounded-lg border border-cta bg-card px-5 text-sm font-semibold text-cta hover:bg-cta/5',
  link: 'text-sm font-semibold text-primary hover:underline',
  // Ligne de bas de carte informative : en noir, aligné sur le rendu avec `href`
  // (cf. InfoCard) — seules les icônes de ce bloc restent bleues.
  row: 'w-full justify-between text-sm font-semibold text-foreground hover:underline',
  // Bouton secondaire discret des cartes article : bordure fine bleue.
  soft:
    'rounded-lg border border-primary/25 px-3 py-2 text-sm font-semibold text-primary hover:bg-primary/5',
};

function TriggerButton({
  onClick,
  label,
  icon,
  variant,
  iconPosition,
  className,
}: Required<Pick<TriggerProps, 'label' | 'variant'>> &
  Pick<TriggerProps, 'icon' | 'iconPosition' | 'className'> & { onClick: () => void }) {
  const iconNode = <HubIcon name={icon} className="h-4 w-4" />;
  const atEnd = iconPosition === 'end';
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex shrink-0 items-center justify-center gap-2 transition ${VARIANTS[variant]} ${className ?? ''}`}
    >
      {!atEnd && iconNode}
      <span>{label}</span>
      {atEnd && iconNode}
    </button>
  );
}

/**
 * Ouvre le dialog de téléchargement du guide.
 *
 * `entryPoint` est OBLIGATOIRE : quatre emplacements de la page ouvrent ce même
 * dialog, et c'est la seule dimension qui dira lequel convertit. Le rendre
 * optionnel garantirait qu'on l'oublie sur un bouton et que ses conversions
 * soient attribuées au mauvais emplacement — une erreur silencieuse.
 */
export function GuideButton({
  variant = 'outline',
  entryPoint,
  ...props
}: TriggerProps & { entryPoint: HubEntryPoint }) {
  return (
    <TriggerButton
      onClick={() => openGuideDialog(entryPoint)}
      variant={variant}
      {...props}
    />
  );
}

/** Ouvre le questionnaire « plan projet ». */
export function AssistantButton({ variant = 'solid', ...props }: TriggerProps) {
  return <TriggerButton onClick={openAssistantDialog} variant={variant} {...props} />;
}
