import { Search } from 'lucide-react';
import { Input } from '../ui/input';
import { Button } from '../ui/button';

const FILTERS = [
  ['all',     'Tous'],
  ['errors',  'Erreurs'],
  ['pending', 'Non sync'],
  ['synced',  'Sync'],
];

const SORTS = [
  ['updated',   'Plus récent'],
  ['name',      'Nom A→Z'],
  ['name_desc', 'Nom Z→A'],
  ['errors',    'Plus d\'erreurs'],
];

const SELECT_CLS =
  'h-8 appearance-none rounded-md border border-input bg-background px-2 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring';

/**
 * Toolbar de la page détail album : recherche produit (nom ou id), filtre rapide
 * (Tous / Erreurs / Non sync / Sync) et tri (récent / nom / erreurs).
 *
 * Les paramètres `q`, `filter`, `sort` sont passés tels quels au backend via
 * `useAlbumProductsQuery` ; le filtrage/tri est donc serveur — la toolbar
 * envoie juste les valeurs au parent.
 */
export function AlbumToolbar({ q, onQ, filter, onFilter, sort, onSort }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="relative min-w-[200px] flex-1">
        <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          className="pl-8"
          placeholder="Rechercher un produit (nom ou id)"
          value={q}
          onChange={(e) => onQ(e.target.value)}
        />
      </div>
      <div className="flex gap-1">
        {FILTERS.map(([k, label]) => (
          <Button
            key={k}
            size="sm"
            variant={filter === k ? 'default' : 'outline'}
            onClick={() => onFilter(k)}
          >
            {label}
          </Button>
        ))}
      </div>
      <select
        className={`${SELECT_CLS} ml-auto`}
        value={sort}
        onChange={(e) => onSort(e.target.value)}
        aria-label="Tri des produits"
      >
        {SORTS.map(([k, l]) => (
          <option key={k} value={k}>{l}</option>
        ))}
      </select>
    </div>
  );
}
