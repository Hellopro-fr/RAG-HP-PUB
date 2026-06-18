/**
 * Rend la valeur d'une estimation (type 11 BO) en HTML, en conservant la mise en forme
 * autorisée (listes ul/ol/li, b/strong, i, u, br) déjà filtrée côté API. Sanitation
 * défensive : retrait des scripts, gestionnaires on* et attributs style.
 * Police 1,10rem (demandé). Le poids/la couleur sont passés via `className`.
 */
function sanitizeEstimationHtml(html: string): string {
  return html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/\s+on\w+="[^"]*"/gi, '')
    .replace(/\s+style="[^"]*"/gi, '');
}

interface EstimationContentProps {
  value: string;
  className?: string;
}

export function EstimationContent({ value, className = '' }: EstimationContentProps) {
  return (
    <div
      className={
        'leading-snug [&_ul]:my-0 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:my-0 [&_ol]:list-decimal [&_ol]:pl-5 ' +
        '[&_li]:mb-0.5 [&_li]:leading-snug [&_b]:font-semibold [&_strong]:font-semibold [&_i]:italic [&_u]:underline ' +
        className
      }
      style={{ fontSize: '1.10rem' }}
      dangerouslySetInnerHTML={{ __html: sanitizeEstimationHtml(value) }}
    />
  );
}
