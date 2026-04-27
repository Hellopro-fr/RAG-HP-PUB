import { ArrowLeft, RefreshCw } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from '../ui/button';

/**
 * En-tête de la page détail album : breadcrumb retour, titre (domaine),
 * sous-titre récap (produits / images / erreurs) et bouton refresh manuel.
 */
export function AlbumHeader({ domain, totalProducts, totalImages, errorCount, onRefresh, isRefetching }) {
  return (
    <header className="space-y-2">
      <Link
        to="/albums"
        className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3 w-3" /> Albums
      </Link>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-mono text-2xl font-semibold">{domain}</h1>
          <p className="text-sm text-muted-foreground">
            {totalProducts} produits · {totalImages} images
            {errorCount > 0 && (
              <span className="text-destructive"> · {errorCount} en erreur</span>
            )}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={onRefresh} disabled={isRefetching}>
          <RefreshCw className={`mr-1 h-3 w-3 ${isRefetching ? 'animate-spin' : ''}`} />
          Rafraîchir
        </Button>
      </div>
    </header>
  );
}
