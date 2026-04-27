import { Search } from 'lucide-react';
import { Input } from '../ui/input';
import { Button } from '../ui/button';

/**
 * Toolbar du listing /albums : recherche par nom de domaine + filtre rapide
 * (tous / avec erreurs / avec produits non sync). Le compteur total reflète
 * la liste complète (pas la liste filtrée), pour donner le contexte global.
 */
export function AlbumsToolbar({ q, onQ, filter, onFilter, total }) {
  const filters = [
    ['all',      'Tous'],
    ['errors',   'Avec erreurs'],
    ['unsynced', 'Non sync'],
  ];

  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <div className="relative min-w-[200px] flex-1">
        <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          className="pl-8"
          placeholder="Rechercher un domaine"
          value={q}
          onChange={(e) => onQ(e.target.value)}
        />
      </div>
      <div className="flex gap-1">
        {filters.map(([k, label]) => (
          <Button
            key={k}
            variant={filter === k ? 'default' : 'outline'}
            size="sm"
            onClick={() => onFilter(k)}
          >
            {label}
          </Button>
        ))}
      </div>
      <span className="ml-auto text-xs text-muted-foreground">{total} albums</span>
    </div>
  );
}
