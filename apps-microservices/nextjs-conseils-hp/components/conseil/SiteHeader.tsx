'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { Search, User, Menu, ChevronDown, ChevronRight, X } from 'lucide-react';
import { SearchModal } from './SearchModal';
import { getCategoryIcon } from '@/lib/categoryIcons';

interface Category {
  id: number;
  nom: string;
  url: string;
}

interface SiteHeaderProps {
  categories?: Category[];
}

export function SiteHeader({ categories = [] }: SiteHeaderProps) {
  const [searchOpen, setSearchOpen]   = useState(false);
  const [menuOpen, setMenuOpen]       = useState(false);
  const menuRef                        = useRef<HTMLDivElement>(null);

  /* Fermer le menu au clic en dehors */
  useEffect(() => {
    if (!menuOpen) return;
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setMenuOpen(false);
    }
    document.addEventListener('mousedown', handleClick);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handleClick);
      document.removeEventListener('keydown', handleKey);
    };
  }, [menuOpen]);

  return (
    <>
      <header className="sticky top-0 z-40 w-full border-b border-border bg-background">

        {/* ── Ligne 1 : Logo + boutons ── */}
        <div className="mx-auto flex max-w-[1400px] items-center gap-3 px-4 py-3 md:py-5 lg:px-6">
          <Link href="https://www.hellopro.fr/" className="flex flex-col leading-none">
            <Image
              src="/images/hp-logo.svg"
              alt="HelloPro"
              width={140}
              height={31}
              className="h-8 w-auto"
              priority
            />
            <span className="mt-0.5 block text-[11px] font-bold text-foreground">
              Partenaire de vos achats pros
            </span>
          </Link>

          {/* Barre recherche desktop (md+) */}
          <div className="hidden flex-1 md:block">
            <div className="relative mx-auto max-w-2xl">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <button
                type="button"
                onClick={() => setSearchOpen(true)}
                aria-label="Ouvrir la recherche"
                className="flex h-11 w-full cursor-text items-center overflow-hidden rounded-md border border-input bg-background pl-10 pr-12 text-sm text-muted-foreground hover:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
              >
                <span className="truncate">Rechercher du matériel parmi 1 million de produits</span>
              </button>
              <span aria-hidden="true" className="pointer-events-none absolute right-1 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-md bg-primary text-primary-foreground">
                →
              </span>
            </div>
          </div>

          {/* Boutons action */}
          <div className="ml-auto flex items-center gap-2 md:ml-0">
            <a
              href="https://www.hellopro.fr/online/page_fournisseur.php?utm_source=www.hellopro.fr"
              className="rounded-md border border-input bg-background px-3 py-2 text-sm font-semibold text-foreground hover:bg-secondary lg:px-4"
            >
              <span className="lg:hidden">Vendre</span>
              <span className="hidden lg:inline">Devenir vendeur</span>
            </a>
            <button
              type="button"
              onClick={() => setSearchOpen(true)}
              className="rounded-md bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 lg:px-4"
            >
              <span className="lg:hidden">Trouver</span>
              <span className="hidden lg:inline">Trouver du matériel</span>
            </button>
          </div>
        </div>

        {/* ── Barre recherche mobile (< md) ── */}
        <div className="border-t border-border bg-background px-4 py-2 md:hidden">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <button
              type="button"
              onClick={() => setSearchOpen(true)}
              aria-label="Ouvrir la recherche"
              className="flex h-10 w-full cursor-text items-center overflow-hidden rounded-md border border-input bg-background pl-10 pr-12 text-sm text-muted-foreground hover:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            >
              <span className="truncate">Rechercher du matériel parmi 1 million de produits</span>
            </button>
            <span aria-hidden="true" className="pointer-events-none absolute right-1 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md bg-primary text-primary-foreground text-sm">
              →
            </span>
          </div>
        </div>

        {/* ── Sous-navigation ── */}
        <div className="border-t border-border bg-background" ref={menuRef}>
          <div className="mx-auto flex max-w-[1400px] items-center gap-6 px-4 py-2 text-sm lg:px-6">

            {/* Bouton Tous les produits */}
            <button
              type="button"
              onClick={() => setMenuOpen((v) => !v)}
              aria-expanded={menuOpen}
              aria-haspopup="true"
              className={`flex items-center gap-2 font-semibold transition ${
                menuOpen ? 'text-primary' : 'text-foreground hover:text-primary'
              }`}
            >
              <Menu className="h-4 w-4" />
              Tous les produits
              <ChevronDown className={`h-3 w-3 transition-transform ${menuOpen ? 'rotate-180' : ''}`} />
            </button>

            <a
              href="https://www.hellopro.fr/qui-sommes-nous"
              className="font-semibold text-foreground transition hover:text-primary"
            >
              Qui sommes-nous ?
            </a>
            <a
              href="https://www.hellopro.fr/mhp/buyer/login?utm=mca"
              className="ml-auto flex items-center gap-2 font-semibold text-foreground transition hover:text-primary"
            >
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-foreground text-background">
                <User className="h-3.5 w-3.5" strokeWidth={2.25} />
              </span>
              <span className="hidden sm:inline">Mes demandes</span>
            </a>
          </div>

          {/* ── Dropdown menu catégories ── */}
          {menuOpen && categories.length > 0 && (
            <div className="border-t border-border bg-background shadow-lg">
              <div className="mx-auto max-w-[1400px] px-4 py-4 lg:px-6">


                {/* Bouton fermer visible sur mobile */}
                <div className="mb-3 flex items-center justify-between md:hidden">
                  <span className="text-sm font-semibold text-foreground">Toutes les catégories</span>
                  <button
                    type="button"
                    onClick={() => setMenuOpen(false)}
                    aria-label="Fermer"
                    className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>

                {/* Grille de catégories — scrollable sur mobile */}
                <ul className="grid max-h-[60svh] grid-cols-1 gap-0.5 overflow-y-auto sm:max-h-none sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                  {categories.map((cat) => {
                    const Icon = getCategoryIcon(cat.nom);
                    return (
                      <li key={cat.id}>
                        <a
                          href={cat.url}
                          onClick={() => setMenuOpen(false)}
                          className="group flex items-center gap-3 rounded-md px-3 py-2 text-sm text-foreground hover:bg-primary-soft hover:text-primary"
                        >
                          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary-soft text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
                            <Icon className="h-[18px] w-[18px]" strokeWidth={1.75} />
                          </span>
                          <span className="min-w-0 flex-1">{cat.nom}</span>
                          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-colors group-hover:text-primary" />
                        </a>
                      </li>
                    );
                  })}
                </ul>
              </div>
            </div>
          )}
        </div>

      </header>

      <SearchModal open={searchOpen} onClose={() => setSearchOpen(false)} />
    </>
  );
}
