'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { Search, X, ChevronRight, Loader2 } from 'lucide-react';

/* ─── Types ────────────────────────────────────────────────────────────────── */

interface CategoryResult {
  name: string;
  boldPart: string;
  rest: string;
  categoryId: string;
  type: string;
}

interface ProductResult {
  name: string;
  segments: Array<{ text: string; bold: boolean }>;
  imageUrl: string;
  productId: string;
  categoryId: string;
}

interface SearchResults {
  categories: CategoryResult[];
  products: ProductResult[];
}

interface SearchModalProps {
  open: boolean;
  onClose: () => void;
  initialQuery?: string;
}

/* ─── Résolution d'URL via le proxy Next.js ─────────────────────────────────── */

async function resolveCategoryUrl(item: CategoryResult): Promise<string> {
  try {
    const res = await fetch('/api/resolve-link', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id_rubrique: item.categoryId, type: item.type }),
    });
    const data = await res.json() as { url: string };
    return data.url ?? 'https://www.hellopro.fr';
  } catch {
    return 'https://www.hellopro.fr';
  }
}

async function resolveProductUrl(item: ProductResult): Promise<string> {
  try {
    const res = await fetch('/api/resolve-link', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id_rubrique: item.categoryId,
        id_produit: item.productId,
        nom_produit: item.name,
      }),
    });
    const data = await res.json() as { url: string };
    return data.url ?? 'https://www.hellopro.fr';
  } catch {
    return 'https://www.hellopro.fr';
  }
}

/* ─── Parseur HTML ──────────────────────────────────────────────────────────── */

function parseSearchResults(html: string): SearchResults {
  if (typeof window === 'undefined') return { categories: [], products: [] };

  const parser = new DOMParser();
  const doc = parser.parseFromString(html, 'text/html');

  /* Catégories */
  const categories: CategoryResult[] = [];
  doc.querySelectorAll('span.link-categ').forEach((span) => {
    const name = span.getAttribute('title') ?? span.textContent ?? '';
    const onclick = span.getAttribute('onclick') ?? '';
    const m = onclick.match(/completer_moteur\([^,]+,\s*'([^']+)',\s*[^,]+,\s*'([^']+)'/);
    const categoryId = m?.[1] ?? '';
    const type = m?.[2] ?? '';
    const boldPart = span.querySelector('b')?.textContent ?? '';
    const rest = name.slice(boldPart.length);
    if (name) categories.push({ name, boldPart, rest, categoryId, type });
  });

  /* Produits */
  const products: ProductResult[] = [];
  doc.querySelectorAll('.lien-produit').forEach((div) => {
    const onclick = div.getAttribute('onclick') ?? '';
    const m = onclick.match(/completer_moteur\('[^']*',\s*'([^']+)',\s*'([^']+)'\)/);
    const categoryId = m?.[1] ?? '';
    const productId = m?.[2] ?? '';
    const img = div.querySelector('img');
    const imageUrl = img?.getAttribute('src') ?? '';
    const name = img?.getAttribute('title') ?? div.querySelector('.nom_produit')?.getAttribute('title') ?? '';
    const segments: Array<{ text: string; bold: boolean }> = [];
    const nameSpan = div.querySelector('.nom_produit > span > span');
    if (nameSpan) {
      nameSpan.childNodes.forEach((node) => {
        if (node.nodeType === Node.TEXT_NODE) {
          const t = node.textContent ?? '';
          if (t) segments.push({ text: t, bold: false });
        } else if (node.nodeName === 'B') {
          const t = node.textContent ?? '';
          if (t) segments.push({ text: t, bold: true });
        }
      });
    } else if (name) {
      segments.push({ text: name, bold: false });
    }
    if (productId) products.push({ name, segments, imageUrl, productId, categoryId });
  });

  return { categories, products };
}

/* ─── Debounce ──────────────────────────────────────────────────────────────── */

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

/* ─── Composant principal ───────────────────────────────────────────────────── */

export function SearchModal({ open, onClose, initialQuery = '' }: SearchModalProps) {
  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<SearchResults>({ categories: [], products: [] });
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  // Détecte la transition fermé→ouvert (pour n'appliquer initialQuery qu'à l'ouverture réelle).
  const wasOpenRef = useRef(false);
  // Dernière requête réellement chargée → évite un refetch (et le flash "Recherche en cours…")
  // à la réouverture quand la saisie n'a pas changé.
  const lastFetchedRef = useRef('');
  const debouncedQuery = useDebounce(query, 250);
  const hasResults = results.categories.length > 0 || results.products.length > 0;

  useEffect(() => {
    if (open && !wasOpenRef.current) {
      // Ouverture réelle : on n'écrase la saisie conservée que si une requête initiale
      // explicite est fournie (ex. ouverture depuis un terme pré-rempli). Sinon on garde
      // la dernière recherche.
      if (initialQuery) setQuery(initialQuery);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
    wasOpenRef.current = open;
  }, [open, initialQuery]);

  useEffect(() => {
    if (!open) return;
    const q = debouncedQuery.trim();
    if (q.length < 2) {
      setResults({ categories: [], products: [] });
      lastFetchedRef.current = '';
      return;
    }
    // Réouverture avec la même requête → résultats déjà en place, pas de refetch ni de loader.
    if (q === lastFetchedRef.current) return;
    let cancelled = false;
    setLoading(true);
    fetch('/api/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chaine: q }),
    })
      .then((r) => r.json())
      .then((data: { html: string }) => {
        if (!cancelled) {
          setResults(parseSearchResults(data.html ?? ''));
          lastFetchedRef.current = q;
          setLoading(false);
        }
      })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [debouncedQuery, open]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    window.location.href =
      `https://www.hellopro.fr/moteur_recherche/recherche_resultat.php?type_recherche=produit&recherche_active=1&mot_cles=${encodeURIComponent(query.trim())}`;
  }, [query]);

  if (!open) return null;

  return (
    <div role="dialog" aria-modal="true" aria-label="Recherche">
      {/* Backdrop — plein écran derrière le panel */}
      <div
        className="fixed inset-0 z-50 bg-foreground/50 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel — ancré en haut, pleine largeur garantie */}
      <div className="fixed inset-x-0 top-0 z-50 flex max-h-[85svh] flex-col bg-background shadow-2xl">
        {/* Barre de recherche */}
        <div className="mx-auto flex w-full max-w-[1400px] items-center gap-3 px-4 py-3 lg:px-6">
          <form onSubmit={handleSubmit} className="flex min-w-0 flex-1 items-center gap-2">
            <div className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-muted-foreground" />
              <input
                ref={inputRef}
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Rechercher du matériel parmi 1 million de produits"
                className="h-12 w-full rounded-lg border border-primary bg-background pl-11 pr-4 text-base shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30"
                autoComplete="off"
              />
            </div>
            <button
              type="submit"
              className="h-12 rounded-lg bg-primary px-5 text-base font-semibold text-primary-foreground hover:opacity-90"
            >
              Rechercher
            </button>
          </form>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fermer la recherche"
            className="flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Résultats — scrollable sur mobile */}
        {(loading || hasResults || (query.length >= 2 && !loading)) && (
          <div className="overflow-y-auto">
          <div className="mx-auto max-w-[1400px] border-t border-border px-4 pb-5 pt-3 lg:px-6">
            {loading && <p className="text-base text-muted-foreground">Recherche en cours…</p>}

            {!loading && !hasResults && query.trim().length >= 2 && (
              <p className="text-base text-muted-foreground">
                Aucun résultat pour «&nbsp;{query}&nbsp;»
              </p>
            )}

            {!loading && hasResults && (
              <div className={
                results.categories.length > 0 && results.products.length > 0
                  ? 'grid gap-6 lg:grid-cols-[280px_1fr]'
                  : 'space-y-4'
              }>

                {/* ── Catégories ── */}
                {results.categories.length > 0 && (
                  <div>
                    <p className="mb-2 text-xs font-bold uppercase tracking-widest text-muted-foreground">
                      Catégories
                    </p>
                    <ul className="space-y-0.5">
                      {results.categories.map((item) => (
                        <li key={`${item.categoryId}-${item.type}`}>
                          <CategoryItem item={item} onClose={onClose} />
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* ── Produits ── */}
                {results.products.length > 0 && (
                  <div>
                    <p className="mb-2 text-xs font-bold uppercase tracking-widest text-muted-foreground">
                      Produits
                    </p>
                    {/* 2 colonnes si catégories présentes, 3 sinon (pleine largeur) */}
                    <div className={
                      results.categories.length > 0
                        ? 'grid grid-cols-1 gap-2 sm:grid-cols-2'
                        : 'grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3'
                    }>
                      {results.products.map((item) => (
                        <ProductItem key={item.productId} item={item} onClose={onClose} />
                      ))}
                    </div>
                  </div>
                )}

              </div>
            )}
          </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── Item catégorie ────────────────────────────────────────────────────────── */

function CategoryItem({ item, onClose }: { item: CategoryResult; onClose: () => void }) {
  const [navigating, setNavigating] = useState(false);

  const handleClick = useCallback(async (e: React.MouseEvent) => {
    e.preventDefault();
    if (navigating) return;
    setNavigating(true);
    const url = await resolveCategoryUrl(item);
    onClose();
    window.location.href = url;
  }, [item, onClose, navigating]);

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={navigating}
      className="group flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-left text-base text-foreground hover:bg-primary-soft disabled:cursor-wait disabled:opacity-60"
    >
      {navigating
        ? <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
        : <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground group-hover:text-primary" />
      }
      <span className="flex-1">
        {item.boldPart ? (
          <>
            <span className="font-semibold text-primary">{item.boldPart}</span>
            <span>{item.rest}</span>
          </>
        ) : (
          <span>{item.name}</span>
        )}
      </span>
      <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
    </button>
  );
}

/* ─── Item produit ──────────────────────────────────────────────────────────── */

function ProductItem({ item, onClose }: { item: ProductResult; onClose: () => void }) {
  const [navigating, setNavigating] = useState(false);

  const handleClick = useCallback(async (e: React.MouseEvent) => {
    e.preventDefault();
    if (navigating) return;
    setNavigating(true);
    const url = await resolveProductUrl(item);
    onClose();
    window.location.href = url;
  }, [item, onClose, navigating]);

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={navigating}
      className="group flex w-full cursor-pointer items-center gap-3 rounded-md border border-transparent p-2 text-left text-base text-foreground hover:border-border hover:bg-secondary disabled:cursor-wait disabled:opacity-60"
    >
      {/* Miniature */}
      {item.imageUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={item.imageUrl}
          alt={item.name}
          className="h-12 w-12 shrink-0 rounded-md border border-border object-cover"
          loading="lazy"
        />
      ) : (
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md border border-border bg-muted">
          <Search className="h-4 w-4 text-muted-foreground" />
        </div>
      )}

      {/* Nom segmenté */}
      <span className="line-clamp-2 flex-1 leading-snug text-muted-foreground group-hover:text-foreground">
        {navigating ? (
          <span className="flex items-center gap-1.5">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Chargement…
          </span>
        ) : (
          item.segments.map((seg, i) =>
            seg.bold ? (
              <strong key={i} className="font-semibold text-primary">{seg.text}</strong>
            ) : (
              <span key={i}>{seg.text}</span>
            )
          )
        )}
      </span>

      <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
    </button>
  );
}
