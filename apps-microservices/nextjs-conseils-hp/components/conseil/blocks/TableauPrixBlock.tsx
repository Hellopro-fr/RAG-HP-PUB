import type { TableauPrixBlockData } from '@/types/blocks/tableau-prix';

interface TableauPrixBlockProps {
  data: TableauPrixBlockData;
}

export function TableauPrixBlock({ data }: TableauPrixBlockProps) {
  return (
    <div className="not-prose my-6 overflow-hidden rounded-xl border border-border shadow-sm">
      <table className="w-full text-left text-sm">
        <thead className="bg-primary text-primary-foreground">
          <tr>
            <th className="px-4 py-3 font-semibold">Type de bâtiment</th>
            <th className="px-4 py-3 font-semibold">Prix par place</th>
            {data.rows.some((r) => r.surface) && (
              <th className="hidden px-4 py-3 font-semibold sm:table-cell">Surface utile</th>
            )}
            {data.rows.some((r) => r.pricePerM2) && (
              <th className="px-4 py-3 font-semibold">Prix au m²</th>
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-border bg-card">
          {data.rows.map((row) => (
            <tr key={row.type} className="hover:bg-secondary">
              <td className="px-4 py-3 font-semibold text-foreground">{row.type}</td>
              <td className="px-4 py-3 text-foreground">{row.price}</td>
              {row.surface && (
                <td className="hidden px-4 py-3 text-muted-foreground sm:table-cell">
                  {row.surface}
                </td>
              )}
              {row.pricePerM2 && (
                <td className="px-4 py-3 font-semibold text-primary">{row.pricePerM2}</td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
