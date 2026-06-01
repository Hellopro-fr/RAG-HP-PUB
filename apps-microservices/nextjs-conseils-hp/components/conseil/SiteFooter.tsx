import Image from 'next/image';

const FOOTER_COLUMNS = [
  {
    title: 'Pour les acheteurs',
    links: [
      { label: 'Connexion à mon espace', href: 'https://www.hellopro.fr/mhp/buyer/login?utm=mca' },
      { label: 'Liste produits', href: 'https://www.hellopro.fr/liste-produit.html' },
      { label: 'Liste vendeurs', href: 'https://www.hellopro.fr/liste-societe.html' },
    ],
  },
  {
    title: 'Pour les vendeurs',
    links: [
      { label: 'Connexion à mon espace vendeur', href: 'https://www.hellopro.fr/redirection_interne.php?v=mc' },
      { label: 'Devenir vendeur sur Hellopro.fr', href: 'https://www.hellopro.fr/online/page_fournisseur.php?utm_source=www.hellopro.fr' },
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

/**
 * Footer global du site conseils.hellopro.fr
 */
export function SiteFooter() {
  return (
    <footer className="mt-16 border-t border-border bg-primary text-primary-foreground">
      <div className="mx-auto max-w-[1400px] px-4 py-12 lg:px-6">
        <div className="mb-10">
          <div className="inline-block rounded bg-white px-3 py-2">
            <Image
              src="/images/hp-logo.svg"
              alt="HelloPro"
              width={140}
              height={31}
              className="h-8 w-auto"
            />
          </div>
          <p className="mt-3 text-sm text-primary-foreground/70">
            Le 1er marketplace BtoB français. Plus d&apos;1 million de produits pros et 1 200
            constructeurs de bâtiments référencés.
          </p>
        </div>

        <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-5">
          {FOOTER_COLUMNS.map((col) => (
            <div key={col.title}>
              <div className="mb-3 text-sm font-bold uppercase tracking-wide text-primary-foreground/90">
                {col.title}
              </div>
              <ul className="space-y-2 text-sm text-primary-foreground/70">
                {col.links.map((link) => (
                  <li key={link.href}>
                    <a
                      href={link.href}
                      className="hover:text-primary-foreground hover:underline"
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-primary-foreground/15 py-4 text-center text-xs text-primary-foreground/60">
        5 avenue de la République 75011 PARIS &nbsp;·&nbsp; ©{new Date().getFullYear()} Hellopro - Tous droits réservés
      </div>
    </footer>
  );
}
