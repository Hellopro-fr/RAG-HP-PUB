import type { TableauHtmlBlockData } from '@/types/blocks/tableau-html';

interface TableauHtmlBlockProps {
  data: TableauHtmlBlockData;
}

/** Retire les attributs de présentation inline et les <br> superflus en bord de cellule. */
function sanitizeCell(html: string): string {
  return html
    .replace(/\s*(style|class|contenteditable)\s*=\s*"[^"]*"/gi, '')
    .replace(/\s*(style|class|contenteditable)\s*=\s*'[^']*'/gi, '')
    .replace(/^(\s*<br\s*\/?>\s*)+/gi, '')
    .replace(/(\s*<br\s*\/?>\s*)+$/gi, '')
    .trim();
}

export function TableauHtmlBlock({ data }: TableauHtmlBlockProps) {
  const { headers, rows } = data;

  if (!headers.length && !rows.length) return null;

  const colCount = headers.length || (rows[0]?.length ?? 0);
  const isWide = colCount > 3;

  const cleanHeaders = headers.map(sanitizeCell);
  const cleanRows = rows.map((row) =>
    Array.from({ length: colCount }, (_, i) => sanitizeCell(row[i] ?? ''))
  );

  const TableBody = (
    <tbody className="divide-y divide-border">
      {cleanRows.map((row, ri) => (
        <tr key={ri} className={ri % 2 === 0 ? 'bg-card' : 'bg-muted/30'}>
          {row.map((cell, ci) => (
            <td
              key={ci}
              className={`px-4 py-3 align-top text-foreground text-pretty${ci === 0 ? ' font-semibold' : ''}`}
              dangerouslySetInnerHTML={{ __html: cell }}
            />
          ))}
        </tr>
      ))}
    </tbody>
  );

  /* ≤ 3 colonnes — table-auto : le navigateur répartit l'espace selon le contenu,
     text-pretty évite les orphelins (mot seul en fin de ligne), pas de scroll */
  if (!isWide) {
    return (
      <div className="not-prose my-6 overflow-hidden rounded-xl border border-border shadow-sm">
        <table className="w-full text-left text-base">
          {cleanHeaders.length > 0 && (
            <thead className="bg-primary text-primary-foreground">
              <tr>
                {cleanHeaders.map((h, i) => (
                  <th
                    key={i}
                    className="px-4 py-3 font-semibold text-pretty"
                    dangerouslySetInnerHTML={{ __html: h }}
                  />
                ))}
              </tr>
            </thead>
          )}
          {TableBody}
        </table>
      </div>
    );
  }

  /* > 3 colonnes : en-têtes non-wrappés, scroll horizontal autorisé */
  const WideTable = (
    <table className="w-full text-left text-base">
      {cleanHeaders.length > 0 && (
        <thead className="bg-primary text-primary-foreground">
          <tr>
            {cleanHeaders.map((h, i) => (
              <th
                key={i}
                className="px-4 py-3 font-semibold whitespace-nowrap"
                dangerouslySetInnerHTML={{ __html: h }}
              />
            ))}
          </tr>
        </thead>
      )}
      {TableBody}
    </table>
  );

  /* > 3 colonnes — desktop table + cartes mobile */
  return (
    <>
      {/* Desktop : tableau classique, masqué en mobile */}
      <div className="not-prose my-6 hidden overflow-hidden rounded-xl border border-border shadow-sm md:block">
        <div className="overflow-x-auto [scrollbar-width:thin]">
          {WideTable}
        </div>
      </div>

      {/* Mobile : une carte par ligne de données, masquée sur desktop */}
      <div className="not-prose my-6 space-y-4 md:hidden">
        {cleanRows.map((row, ri) => (
          <div key={ri} className="overflow-hidden rounded-xl border border-border shadow-sm">
            <table className="w-full text-base">
              <thead className="bg-primary text-primary-foreground">
                <tr>
                  {/* Titre de carte : header[0] : row[0] */}
                  <th colSpan={2} className="px-4 py-3 font-normal text-left">
                    <span
                      className="font-semibold"
                      dangerouslySetInnerHTML={{ __html: cleanHeaders[0] ?? '' }}
                    />
                    {' : '}
                    <span dangerouslySetInnerHTML={{ __html: row[0] ?? '' }} />
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {row.slice(1).map((cell, ci) => (
                  <tr key={ci} className={ci % 2 === 0 ? 'bg-card' : 'bg-muted/30'}>
                    <td
                      className="px-3 py-2 font-medium text-muted-foreground whitespace-nowrap"
                      dangerouslySetInnerHTML={{ __html: cleanHeaders[ci + 1] ?? '' }}
                    />
                    <td
                      className="px-3 py-2 text-foreground whitespace-nowrap"
                      dangerouslySetInnerHTML={{ __html: cell }}
                    />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </>
  );
}
