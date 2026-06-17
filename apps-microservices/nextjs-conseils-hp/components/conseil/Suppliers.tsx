'use client';

import { useRef, useState, useEffect } from 'react';
import Image from 'next/image';
import { Building2, ChevronLeft, ChevronRight } from 'lucide-react';
import type { Supplier } from '@/types/conseils';
import { IframeProduitModal } from '@/components/conseil/IframeProduitModal';

const FALLBACK_DESC = 'Fournisseur référencé sur HelloPro — demandez votre devis gratuitement.';

/**
 * Construit « de {libellé} » avec élision devant voyelle / h muet : « d'{libellé} ».
 * normalize('NFD') gère les voyelles accentuées (É, À…). Limite connue : le h aspiré
 * (« de hangar ») est rare dans les libellés catégories et reste élidé ici.
 */
function avecDe(label: string): string {
  const t = label.trim();
  const first = t.normalize('NFD').charAt(0).toLowerCase();
  return 'aeiouhyœæ'.includes(first) ? `d'${t}` : `de ${t}`;
}

function sanitizeHtml(html: string): string {
  return html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/\s+on\w+="[^"]*"/gi, '')
    .replace(/\sstyle="[^"]*"/gi, '')
    .replace(/\[\/?(b|i|u|s|em|strong)\]/gi, '');
}

interface SuppliersProps {
  suppliers?: Supplier[];
  /** id de la rubrique — utilisé comme paramètre f dans contact_info.php */
  infoRubriqueId?: number;
  /** Libellé de la catégorie (info_rubrique.libelle de l'API) — titre dynamique du bloc. */
  categoryLabel?: string;
}

export function Suppliers({ suppliers = [], infoRubriqueId, categoryLabel }: SuppliersProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);
  const [openSocId, setOpenSocId] = useState<string | null>(null);
  const showArrows = suppliers.length > 3;

  const updateScrollState = () => {
    const el = scrollRef.current;
    if (!el) return;
    setCanScrollLeft(el.scrollLeft > 0);
    setCanScrollRight(el.scrollLeft < el.scrollWidth - el.clientWidth - 1);
  };

  useEffect(() => {
    if (showArrows) updateScrollState();
  }, [showArrows]);

  const scroll = (dir: 'left' | 'right') => {
    scrollRef.current?.scrollBy({ left: dir === 'left' ? -300 : 300, behavior: 'smooth' });
  };

  if (!suppliers?.length) return null;

  return (
    <section id="constructeurs" className="not-prose my-12 scroll-mt-32">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-extrabold text-foreground">
            {categoryLabel ? `Nos fournisseurs ${avecDe(categoryLabel)}` : 'Nos fournisseurs'}
          </h2>
        </div>
        {showArrows && (
          <div className="flex shrink-0 gap-2">
            <button
              onClick={() => scroll('left')}
              disabled={!canScrollLeft}
              aria-label="Précédent"
              className="flex h-8 w-8 items-center justify-center rounded-full border border-border bg-card text-foreground transition hover:border-primary hover:text-primary disabled:opacity-30"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              onClick={() => scroll('right')}
              disabled={!canScrollRight}
              aria-label="Suivant"
              className="flex h-8 w-8 items-center justify-center rounded-full border border-border bg-card text-foreground transition hover:border-primary hover:text-primary disabled:opacity-30"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>

      <div
        ref={showArrows ? scrollRef : undefined}
        onScroll={showArrows ? updateScrollState : undefined}
        className={
          showArrows
            ? 'mt-6 flex gap-5 overflow-x-auto scroll-smooth pb-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden'
            : 'mt-6 grid gap-5 md:grid-cols-3'
        }
      >
        {suppliers.map((s) => (
          <article
            key={s.id}
            className={`flex flex-col rounded-xl border border-border bg-card p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md${showArrows ? ' w-72 shrink-0' : ''}`}
          >
            <div className="mb-3 flex h-14 w-14 items-center justify-center overflow-hidden rounded-lg bg-primary-soft text-primary">
              {s.logoPath ? (
                <Image
                  src={s.logoPath}
                  alt={`Logo ${s.name}`}
                  width={56}
                  height={56}
                  className="h-full w-full object-contain"
                  unoptimized
                />
              ) : (
                <Building2 className="h-7 w-7" />
              )}
            </div>
            <h3 className="text-lg font-extrabold text-foreground">{s.name}</h3>
            {s.description ? (
              <div className="relative mt-3 max-h-[10rem] overflow-hidden text-sm text-foreground/90 [&_*]:!text-sm">
                <div
                  className="[&_p]:mb-1.5 [&_p:last-child]:mb-0 [&_ul]:list-disc [&_ul]:pl-4 [&_li]:mb-1 [&_strong]:font-normal [&_b]:font-normal [&_u]:no-underline [&_h1]:text-sm [&_h1]:font-normal [&_h2]:text-sm [&_h2]:font-normal [&_h3]:text-sm [&_h3]:font-normal [&_h4]:text-sm [&_h4]:font-normal [&_a]:text-primary [&_a]:underline"
                  dangerouslySetInnerHTML={{ __html: sanitizeHtml(s.description) }}
                />
                <div className="pointer-events-none absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-card to-transparent" />
                <span className="absolute bottom-0.5 right-1 text-xs text-foreground/50">…</span>
              </div>
            ) : (
              <p className="mt-3 text-sm text-foreground/90">{FALLBACK_DESC}</p>
            )}
            <button
              type="button"
              onClick={() => setOpenSocId(String(s.id))}
              className="mt-auto w-full cursor-pointer rounded-md border border-primary bg-primary/5 py-2 text-sm font-bold text-primary transition hover:bg-primary hover:text-primary-foreground"
            >
              Envoyer un message
            </button>
          </article>
        ))}
      </div>

      {/* Modal contact_info.php — soc = id_societe, origine = 55, f = id_rubrique */}
      {openSocId && (
        <IframeProduitModal
          idProduit=""
          extraParams={{
            soc: openSocId,
            origine: '55',
            ...(infoRubriqueId !== undefined ? { f: String(infoRubriqueId) } : {}),
          }}
          open={true}
          onClose={() => setOpenSocId(null)}
        />
      )}
    </section>
  );
}
