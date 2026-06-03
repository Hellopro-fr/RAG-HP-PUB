import type { TableauHtmlBlockData } from '@/types/blocks/tableau-html';

interface TableauHtmlBlockProps {
  data: TableauHtmlBlockData;
}

export function TableauHtmlBlock({ data }: TableauHtmlBlockProps) {
  if (!data.headers.length && !data.rows.length) return null;

  return (
    <div className="not-prose my-6 overflow-hidden rounded-xl border border-border shadow-sm">
      <table className="w-full text-left text-sm">
        {data.headers.length > 0 && (
          <thead className="bg-primary text-primary-foreground">
            <tr>
              {data.headers.map((h, i) => (
                <th key={i} className="px-4 py-3 font-semibold" dangerouslySetInnerHTML={{ __html: h }} />
              ))}
            </tr>
          </thead>
        )}
        <tbody className="divide-y divide-border bg-card">
          {data.rows.map((row, ri) => (
            <tr key={ri} className="hover:bg-secondary">
              {row.map((cell, ci) => (
                <td
                  key={ci}
                  className={`px-4 py-3 text-foreground ${ci === 0 ? 'font-semibold' : ''}`}
                  dangerouslySetInnerHTML={{ __html: cell }}
                />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
