import Link from 'next/link';
import Image from 'next/image';
import { Search, User, Menu, ChevronDown } from 'lucide-react';

/**
 * Header global du site conseils.hellopro.fr
 * Composant serveur — pas d'interactivité (menu mobile géré côté client si besoin).
 */
export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 w-full border-b border-border bg-background/95 backdrop-blur">
      <div className="mx-auto flex max-w-[1400px] items-center gap-4 px-4 py-3 lg:px-6">
        <Link href="/" className="flex flex-col leading-none">
          <Image
            src="/images/hp-logo.svg"
            alt="HelloPro"
            width={140}
            height={31}
            className="h-8 w-auto"
            priority
          />
          <span className="mt-1 text-[10px] uppercase tracking-wide text-muted-foreground">
            Partenaire de vos achats pros
          </span>
        </Link>

        <div className="hidden flex-1 md:block">
          <div className="relative mx-auto max-w-2xl">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              type="search"
              placeholder="Rechercher du matériel parmi 1 million de produits"
              className="h-11 w-full rounded-md border border-input bg-background pl-10 pr-12 text-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
            <button
              aria-label="Rechercher"
              className="absolute right-1 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-md bg-primary text-primary-foreground hover:opacity-90"
            >
              →
            </button>
          </div>
        </div>

        <nav className="ml-auto hidden items-center gap-2 lg:flex">
          <a
            href="https://www.hellopro.fr/devenir-vendeur"
            className="rounded-md border border-input bg-background px-4 py-2 text-sm font-semibold text-foreground hover:bg-secondary"
          >
            Devenir vendeur
          </a>
          <a
            href="https://www.hellopro.fr"
            className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90"
          >
            Trouver du matériel
          </a>
        </nav>

        <button className="lg:hidden" aria-label="Menu">
          <Menu className="h-6 w-6 text-foreground" />
        </button>
      </div>

      <div className="border-t border-border bg-background">
        <div className="mx-auto flex max-w-[1400px] items-center gap-6 px-4 py-2 text-sm lg:px-6">
          <button className="flex items-center gap-2 font-semibold text-foreground">
            <Menu className="h-4 w-4" />
            Tous les produits
            <ChevronDown className="h-3 w-3" />
          </button>
          <a
            href="https://www.hellopro.fr/qui-sommes-nous"
            className="hidden text-muted-foreground hover:text-foreground md:inline"
          >
            Qui sommes-nous ?
          </a>
          <a
            href="https://www.hellopro.fr/mes-demandes"
            className="ml-auto hidden items-center gap-2 text-muted-foreground hover:text-foreground md:flex"
          >
            <User className="h-4 w-4" />
            Mes demandes
          </a>
        </div>
      </div>
    </header>
  );
}
