import { Search, Layers, Disc3, Film, Clapperboard } from 'lucide-react';
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

// Modes d'affichage des images dans les cartes produit. Voir le handoff
// `design_handoff_albums_image_presentations/README.md` pour le détail des
// 4 présentations stylisées (stack/coverflow/reel/dial).
const IMAGE_MODES = [
  ['deck',      'Stack',     Layers],
  ['coverflow', 'Coverflow', Disc3],
  ['reel',      'Reel',      Film],
  ['dial',      'Dial',      Clapperboard],
];

const SELECT_CLS =
  'h-8 appearance-none rounded-md border border-hairline bg-bg-1 px-2 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent';

/**
 * Toolbar de la page détail album : recherche produit (nom ou id), sélecteur
 * du mode d'affichage des images (stack/coverflow/reel/dial), filtre rapide
 * (Tous / Erreurs / Non sync / Sync) et tri (récent / nom / erreurs).
 *
 * Les paramètres `q`, `filter`, `sort` sont passés tels quels au backend via
 * `useAlbumProductsQuery` ; le filtrage/tri est donc serveur — la toolbar
 * envoie juste les valeurs au parent. `imageMode` est purement client
 * (persisté en localStorage par `AlbumDetailPage`).
 */
export function AlbumToolbar({
  q,
  onQ,
  filter,
  onFilter,
  sort,
  onSort,
  imageMode,
  onImageMode,
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="relative min-w-[200px] flex-1">
        <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" />
        <Input
          className="pl-8"
          placeholder="Rechercher un produit (nom ou id)"
          value={q}
          onChange={(e) => onQ(e.target.value)}
        />
      </div>

      {onImageMode && (
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-mono uppercase text-ink-3 tracking-wider">
            Vue
          </span>
          <div className="flex gap-1">
            {IMAGE_MODES.map((mode) => {
              const [id, label, ModeIcon] = mode;
              const active = imageMode === id;
              return (
                <Button
                  key={id}
                  size="sm"
                  variant={active ? 'default' : 'outline'}
                  onClick={() => onImageMode(id)}
                  aria-pressed={active}
                  aria-label={`Mode d'affichage ${label}`}
                  title={label}
                >
                  <ModeIcon className="h-3.5 w-3.5" />
                  <span className="ml-1.5 hidden sm:inline">{label}</span>
                </Button>
              );
            })}
          </div>
        </div>
      )}

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
