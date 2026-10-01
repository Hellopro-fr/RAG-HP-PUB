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

  // Valeur « single line » = pas de <br> et moins de 2 <li> → centrée en mobile.
  // Sinon (liste à puces multiple / sauts de ligne) → alignée à gauche. Desktop : toujours à gauche.
  const liCount = (value.match(/<li\b/gi) ?? []).length;
  const isSingleLine = liCount < 2 && !/<br\s*\/?>/i.test(value);
  const valueAlign = isSingleLine ? 'text-center sm:text-left' : 'text-left';

  return (
    <div className={`overflow-hidden rounded-xl border border-primary ${className}`}>
      <div className="flex flex-col sm:flex-row sm:items-stretch">
        <div className={`flex items-center justify-center bg-primary-soft px-6 py-4 text-center ${labelWidthClass}`}>
          <span className="font-bold text-primary" style={{ fontSize: '1.10rem' }}>
            {label}
          </span>
        </div>
        <div className={`flex flex-1 items-center px-6 py-4 ${valueAlign}`}>
          <EstimationContent value={value} className="w-full font-semibold text-foreground" />
        </div>
      </div>
    </div>
  );
}
