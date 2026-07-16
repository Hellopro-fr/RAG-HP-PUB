import Image from 'next/image';
import { MapPin } from 'lucide-react';
import { ScrollToTopButton } from './ScrollToTopButton';

interface FooterLink {
  label: string;
  href: string;
  /** Classe d'accent optionnelle (override la couleur par défaut du lien). */
  accentClass?: string;
}

interface FooterColumn {
  title: string;
  /** Classe d'accent appliquée au dernier mot du titre (ex. « acheteurs », « vendeurs »). */
  accentClass?: string;
  links: FooterLink[];
}

// Accents footer sur fond bleu : ambre (acheteurs) + corail (vendeurs).
const ACCENT_ACHETEURS = 'text-[#ffc861]';
const ACCENT_VENDEURS = 'text-[#ff9e7a]';

const FOOTER_COLUMNS: FooterColumn[] = [
  {
    title: 'Pour les acheteurs',
    accentClass: ACCENT_ACHETEURS,
    links: [
      { label: 'Connexion à mon espace', href: 'https://www.hellopro.fr/mhp/buyer/login?utm=mca' },
      { label: 'Liste produits', href: 'https://www.hellopro.fr/liste-produit.html' },
      { label: 'Liste vendeurs', href: 'https://www.hellopro.fr/liste-societe.html' },
    ],
  },
  {
    title: 'Pour les vendeurs',
    accentClass: ACCENT_VENDEURS,
    links: [
      { label: 'Connexion à mon espace vendeur', href: 'https://www.hellopro.fr/redirection_interne.php?v=mc' },
      { label: 'Devenir vendeur sur Hellopro.fr', href: 'https://www.hellopro.fr/online/page_fournisseur.php?utm_source=www.hellopro.fr', accentClass: `${ACCENT_VENDEURS} font-medium` },
    ],
  },
  {
    title: 'À propos',
    links: [
      { label: 'Qui sommes-nous ?', href: 'https://www.hellopro.fr/qui-sommes-nous' },
    ],
  },
  {
    title: "Besoin d'aide ?",
    links: [
      { label: 'Nous contacter', href: 'https://www.hellopro.fr/nous-contacter.html' },
      { label: "Guides et conseils d'achat", href: 'https://conseils.hellopro.fr/' },
      { label: 'Plan du site', href: 'https://www.hellopro.fr/plan-site.html' },
    ],
  },
  {
    title: 'Informations légales',
    links: [
      { label: 'Mentions légales', href: 'https://www.hellopro.fr/mentions.html' },
      { label: 'CGUs Hellopro', href: 'https://www.hellopro.fr/mhp/buyer/cgu' },
    ],
  },
];

/** Colore le dernier mot du titre (ex. « acheteurs », « vendeurs ») avec la classe d'accent. */
function renderColumnTitle(col: FooterColumn) {
  if (!col.accentClass) return col.title;
  const idx = col.title.lastIndexOf(' ');
  if (idx === -1) return <span className={col.accentClass}>{col.title}</span>;
  return (
    <>
      {col.title.slice(0, idx + 1)}
      <span className={col.accentClass}>{col.title.slice(idx + 1)}</span>
    </>
  );
}

/**
 * Footer global du site conseils.hellopro.fr
 */
export function SiteFooter() {
  return (
    <footer id="site-footer" className="min-[769px]:mt-8 border-t border-border bg-primary text-primary-foreground">
      <div className="mx-auto max-w-[1400px] px-4 py-12 lg:px-6">
        <div className="mb-10">
          <a href="https://www.hellopro.fr/" className="inline-block rounded bg-white px-3 py-2">
            <Image
              src="/images/hp-logo.svg"
              alt="HelloPro"
              width={140}
              height={31}
              className="h-8 w-auto"
            />
          </a>
          <p className="mt-3 text-base text-primary-foreground/70">
            <strong className="font-semibold text-primary-foreground">Hellopro</strong> est la
            première place de marché professionnelle en France. Cherchez, obtenez et comparez des
            devis pour du matériel dans plus de 10 000 catégories différentes.
          </p>
        </div>

        <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-5">
          {FOOTER_COLUMNS.map((col) => (
            <div key={col.title}>
              <div className="mb-3 text-base font-bold uppercase tracking-wide text-primary-foreground/90">
                {renderColumnTitle(col)}
              </div>
              <ul className="space-y-2 text-base text-primary-foreground/70">
                {col.links.map((link) => (
                  <li key={link.href}>
                    <a
                      href={link.href}
                      className={
                        link.accentClass
                          ? `${link.accentClass} hover:underline`
                          : 'hover:text-primary-foreground hover:underline'
                      }
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Adresse (avec picto) à gauche + bouton remonter à droite */}
        <div className="mt-10 flex items-end justify-between gap-4">
          <p className="flex items-start gap-2 text-base text-primary-foreground/70">
            <MapPin className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
            <span>
              5 avenue de la République
              <br />
              75011 PARIS
            </span>
          </p>
          <ScrollToTopButton />
        </div>
      </div>

      <div className="border-t border-primary-foreground/15 py-4 text-center text-xs text-primary-foreground/60">
        ©{new Date().getFullYear()} Hellopro - Tous droits réservés
      </div>
    </footer>
  );
}
