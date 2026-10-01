import type { EstimationPrixBlockData } from '@/types/blocks/estimation-prix';
import { EstimationBox } from './EstimationBox';

interface EstimationPrixBlockProps {
  data: EstimationPrixBlockData;
}

/**
 * Tableau prix « single » (type 11 BO non fusionné) — box estimation pleine largeur.
 */
export function EstimationPrixBlock({ data }: EstimationPrixBlockProps) {
  if (!data.value) return null;
  return (
    <div className="not-prose my-6">
      <EstimationBox label={data.label} value={data.value} />
    </div>
  );
}
