import type { TableauPrixBlockData } from '@/types/blocks/tableau-prix';

interface TableauPrixBlockProps {
  data: TableauPrixBlockData;
}

export function TableauPrixBlock({ data }: TableauPrixBlockProps) {
  const hasSurface = data.rows.some((r) => r.surface);
  const hasPricePerM2 = data.rows.some((r) => r.pricePerM2);

  return (
    <div className="not-prose my-6 overflow-hidden rounded-xl border border-border shadow-sm">
      <table className="w-full text-left text-sm">
        <thead className="bg-primary text-primary-foreground">
          <tr>
            <th className="px-4 py-3 font-semibold align-middle">Type de bâtiment</th>
            <th className="px-4 py-3 font-semibold align-middle">Prix par place</th>
            {hasSurface && (
              <th className="hidden px-4 py-3 font-semibold align-middle sm:table-cell">
                Surface utile
              </th>
            )}
            {hasPricePerM2 && (
              <th className="px-4 py-3 font-semibold align-middle">Prix au m²</th>
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-border bg-card">
          {data.rows.map((row, i) => (
            <tr key={`${row.type}-${i}`} className="hover:bg-secondary">
              <td className="px-4 py-3 align-middle font-semibold text-foreground">{row.type}</td>
              <td className="px-4 py-3 align-middle text-foreground">{row.price}</td>
              {hasSurface && (
                <td className="hidden px-4 py-3 align-middle text-muted-foreground sm:table-cell">
                  {row.surface ?? '—'}
                </td>
              )}
              {hasPricePerM2 && (
                <td className="px-4 py-3 align-middle font-semibold text-primary">
                  {row.pricePerM2 ?? '—'}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
