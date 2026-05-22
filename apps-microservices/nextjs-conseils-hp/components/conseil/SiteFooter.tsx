import Image from 'next/image';

const FOOTER_LINKS = [
  {
    title: 'HelloPro',
    links: ['Qui sommes-nous', 'Devenir vendeur', 'Carrières', 'Presse'],
  },
  {
    title: 'Acheteurs',
    links: ['Demander un devis', 'Mes demandes', 'Guides experts', 'Comparateurs'],
  },
  {
    title: 'Aide',
    links: ['Centre d\'aide', 'Nous contacter', 'CGU', 'Confidentialité'],
  },
];

/**
 * Footer global du site conseils.hellopro.fr
 */
export function SiteFooter() {
  return (
    <footer className="mt-16 border-t border-border bg-primary text-primary-foreground">
      <div className="mx-auto grid max-w-[1400px] gap-8 px-4 py-12 md:grid-cols-4 lg:px-6">
        <div>
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

        {FOOTER_LINKS.map((col) => (
          <div key={col.title}>
            <div className="mb-3 text-sm font-bold uppercase tracking-wide text-primary-foreground/90">
              {col.title}
            </div>
            <ul className="space-y-2 text-sm text-primary-foreground/70">
              {col.links.map((link) => (
                <li key={link}>
                  <a href="#" className="hover:text-primary-foreground hover:underline">
                    {link}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="border-t border-primary-foreground/15 py-4 text-center text-xs text-primary-foreground/60">
        © {new Date().getFullYear()} HelloPro · Partenaire de vos achats pros
      </div>
    </footer>
  );
}
