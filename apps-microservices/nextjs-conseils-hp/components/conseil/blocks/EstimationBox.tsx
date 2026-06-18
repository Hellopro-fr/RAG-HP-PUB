import { EstimationContent } from './EstimationContent';

interface EstimationBoxProps {
  label: string;
  value: string;
  className?: string;
  /** Largeur de la cellule label (desktop). Défaut 30 % (isolé) ; 35 % en mode fusionné. */
  labelWidthClass?: string;
}

/**
 * Box estimation de prix (design hellopro.fr) — label ~30 % (fond clair) / valeur ~70 %
 * (alignée à gauche, rendue en HTML : listes + gras/italique/souligné). Bordure bleu primaire.
 * Empilée en mobile. Sans marge externe : la marge est posée par le composant appelant.
 * Utilisée pour le tableau prix isolé (EstimationPrixBlock) ET fusionné (TexteImageBlock).
 */
export function EstimationBox({
  label,
  value,
  className = '',
  labelWidthClass = 'sm:w-[30%]',
}: EstimationBoxProps) {
  if (!value) return null;

  return (
    <div className={`overflow-hidden rounded-xl border border-primary ${className}`}>
      <div className="flex flex-col sm:flex-row sm:items-stretch">
        <div className={`flex items-center justify-center bg-primary-soft px-6 py-4 text-center ${labelWidthClass}`}>
          <span className="font-bold text-primary" style={{ fontSize: '1.10rem' }}>
            {label}
          </span>
        </div>
        <div className="flex flex-1 items-center px-6 py-4 text-left">
          <EstimationContent value={value} className="font-semibold text-foreground" />
        </div>
      </div>
    </div>
  );
}
