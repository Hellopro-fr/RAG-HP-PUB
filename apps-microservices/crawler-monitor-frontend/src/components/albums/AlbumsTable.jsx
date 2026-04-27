import { List } from 'react-window';
import { Trash2 } from 'lucide-react';
import { Button } from '../ui/button';

const ROW_HEIGHT = 48;
const MAX_LIST_HEIGHT = 600;
const GRID_COLS = 'grid-cols-[2fr_1fr_1fr_1fr_1.5fr_1fr_60px]';

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });
}

function syncPercent(row) {
  if (!row.product_count || row.product_count <= 0) return '—';
  return `${Math.round((row.synced_count / row.product_count) * 100)}%`;
}

/**
 * Ligne virtualisée du tableau albums.
 * Reçoit `rows`, `onSelectDomain`, `onRequestDelete` via `rowProps`
 * (mécanisme react-window v2 — passe les données arbitraires au row component).
 */
function AlbumRow({ index, style, rows, onSelectDomain, onRequestDelete }) {
  const r = rows[index];
  if (!r) return null;
  return (
    <div
      style={style}
      role="button"
      tabIndex={0}
      onClick={() => onSelectDomain(r.domain)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelectDomain(r.domain);
        }
      }}
      className={`grid ${GRID_COLS} cursor-pointer items-center border-b border-border px-3 hover:bg-accent/40 focus:outline-none focus-visible:bg-accent/60 focus-visible:ring-2 focus-visible:ring-ring`}
    >
      <div className="truncate font-mono text-sm">{r.domain}</div>
      <div className="font-mono text-sm">{r.product_count ?? 0}</div>
      <div className="font-mono text-sm">{r.image_count ?? 0}</div>
      <div className={`font-mono text-sm ${r.error_count > 0 ? 'font-semibold text-destructive' : ''}`}>
        {r.error_count ?? 0}
      </div>
      <div className="text-xs text-muted-foreground">{formatDate(r.last_update)}</div>
      <div className="font-mono text-xs">{syncPercent(r)}</div>
      <div
        className="flex justify-end"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
      >
        <Button
          variant="ghost"
          size="icon"
          title="Supprimer l'album"
          aria-label={`Supprimer l'album ${r.domain}`}
          onClick={() => onRequestDelete(r)}
        >
          <Trash2 className="h-4 w-4 text-destructive" />
        </Button>
      </div>
    </div>
  );
}

/**
 * Tableau virtualisé (react-window v2 `List`) listant les albums.
 *
 * Colonnes : Domaine, Produits, Images, Erreurs, Dernière MAJ, Sync %, Actions.
 * Le tri (ASC/DESC) est géré côté parent via `sort` + `onSort(key)`.
 */
export function AlbumsTable({ rows, onSelectDomain, onRequestDelete, sort, onSort }) {
  const HeadCell = ({ k, label, className = '' }) => {
    const active = sort === k || sort === `${k}_desc`;
    const arrow = active ? (sort.endsWith('_desc') ? ' ↓' : ' ↑') : '';
    return (
      <button
        type="button"
        className={`py-2 text-left text-xs text-muted-foreground hover:text-foreground ${active ? 'font-semibold text-foreground' : ''} ${className}`}
        onClick={() => onSort(k)}
      >
        {label}{arrow}
      </button>
    );
  };

  // Hauteur calculée pour ne pas réserver 600px quand il n'y a que 3 lignes.
  const listHeight = Math.min(MAX_LIST_HEIGHT, Math.max(ROW_HEIGHT, rows.length * ROW_HEIGHT));

  return (
    <div>
      <div className={`grid ${GRID_COLS} border-b border-border bg-muted/30 px-3`}>
        <HeadCell k="domain"        label="Domaine" />
        <HeadCell k="product_count" label="Produits" />
        <HeadCell k="image_count"   label="Images" />
        <HeadCell k="error_count"   label="Erreurs" />
        <HeadCell k="last_update"   label="Dernière MAJ" />
        <HeadCell k="synced_count"  label="Sync" />
        <span />
      </div>
      <List
        rowComponent={AlbumRow}
        rowCount={rows.length}
        rowHeight={ROW_HEIGHT}
        rowProps={{ rows, onSelectDomain, onRequestDelete }}
        style={{ height: listHeight }}
        overscanCount={6}
      />
    </div>
  );
}
