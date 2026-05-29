'use client';

import { useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { Search, User, Menu, ChevronDown } from 'lucide-react';
import { SearchModal } from './SearchModal';

/**
 * Header global du site conseils.hellopro.fr
 *
 * Mobile  : Logo | Vendre | Trouver  (ligne 1)
 *           [──── barre de recherche ────]  (ligne 2, visible uniquement mobile)
 *           ≡ Tous les produits  Qui sommes-nous  👤  (ligne 3)
 *
 * Desktop : Logo | [── barre de recherche ──] | Devenir vendeur | Trouver du matériel  (ligne 1)
 *           ≡ Tous les produits  Qui sommes-nous  Mes demandes  (ligne 2)
 */
export function SiteHeader() {
  const [searchOpen, setSearchOpen] = useState(false);

  return (
    <>
      <header className="sticky top-0 z-40 w-full border-b border-border bg-background/95 backdrop-blur">

        {/* ── Ligne principale ── */}
        <div className="mx-auto flex max-w-[1400px] items-center gap-3 px-4 py-3 lg:px-6">

          {/* Logo */}
          <Link href="/" className="flex flex-col leading-none">
            <Image
              src="/images/hp-logo.svg"
              alt="HelloPro"
              width={140}
              height={31}
              className="h-8 w-auto"
              priority
            />
            <span className="mt-0.5 hidden text-[10px] uppercase tracking-wide text-muted-foreground sm:block">
              Partenaire de vos achats pros
            </span>
          </Link>

          {/* Barre de recherche — visible dès md (tablette + desktop) */}
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
              <span
                aria-hidden="true"
                className="pointer-events-none absolute right-1 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-md bg-primary text-primary-foreground"
              >
                →
              </span>
            </div>
          </div>

          {/* Boutons d'action — ml-auto sur mobile (pas de barre de recherche), 0 sur md+ */}
          <div className="ml-auto flex items-center gap-2 md:ml-0">
            <a
              href="https://www.hellopro.fr/online/page_fournisseur.php?utm_source=www.hellopro.fr"
              className="rounded-md border border-input bg-background px-3 py-2 text-sm font-semibold text-foreground hover:bg-secondary lg:px-4"
            >
              {/* Label court sur mobile, complet sur desktop */}
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

        {/* ── Barre de recherche mobile (uniquement < md) ── */}
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
            <span
              aria-hidden="true"
              className="pointer-events-none absolute right-1 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md bg-primary text-primary-foreground text-sm"
            >
              →
            </span>
          </div>
        </div>

        {/* ── Sous-navigation ── */}
        <div className="border-t border-border bg-background">
          <div className="mx-auto flex max-w-[1400px] items-center gap-6 px-4 py-2 text-sm lg:px-6">
            <button className="flex items-center gap-2 font-semibold text-foreground">
              <Menu className="h-4 w-4" />
              Tous les produits
              <ChevronDown className="h-3 w-3" />
            </button>
            <a
              href="https://www.hellopro.fr/qui-sommes-nous"
              className="text-muted-foreground hover:text-foreground"
            >
              Qui sommes-nous ?
            </a>
            <a
              href="https://www.hellopro.fr/mhp/buyer/login?utm=mca"
              className="ml-auto flex items-center gap-2 text-muted-foreground hover:text-foreground"
            >
              <User className="h-4 w-4" />
              <span className="hidden sm:inline">Mes demandes</span>
            </a>
          </div>
        </div>

      </header>

      <SearchModal
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
      />
    </>
  );
}
