'use client';

import { useState } from 'react';
import { ArrowRight } from 'lucide-react';
import type { CTABlockData } from '@/types/blocks/cta';
import { IframeFormModal } from '@/components/conseil/IframeFormModal';
import { IframeProduitModal } from '@/components/conseil/IframeProduitModal';

interface CTABlockProps {
  data: CTABlockData;
}

/**
 * demande_info.php → TOUJOURS IframeFormModal (formulaire groupée).
 * Extrait f (= id_rubrique) + tous les autres params à transmettre à l'iframe.
 * L'URL demande_info.php ne doit JAMAIS apparaître dans le HTML rendu.
 */
function parseDemandeInfo(url: string): { idRubrique: string; extraParams: Record<string, string> } | null {
  try {
    if (!url.includes('demande_info.php')) return null;
    const parsed = new URL(url, 'https://www.hellopro.fr');
    const idRubrique = parsed.searchParams.get('f');
    if (!idRubrique) return null;
    const extraParams: Record<string, string> = {};
    parsed.searchParams.forEach((value, key) => {
      if (key !== 'f') extraParams[key] = value;
    });
    return { idRubrique, extraParams };
  } catch {
    return null;
  }
}

/**
 * contact_info.php → TOUJOURS IframeProduitModal, id_produit peut être absent.
 * Tous les params de l'URL originale sont transmis à l'iframe sauf id_produit et src_integ
 * qui sont extraits séparément.
 */
function parseContactInfo(url: string): { idProduit: string; srcInteg: 0 | 1; extraParams: Record<string, string> } | null {
  try {
    if (!url.includes('contact_info.php')) return null;
    const parsed = new URL(url, 'https://www.hellopro.fr');
    const idProduit = parsed.searchParams.get('id_produit') ?? '';
    const srcInteg: 0 | 1 = parsed.searchParams.get('src_integ') === '1' ? 1 : 0;
    const extraParams: Record<string, string> = {};
    parsed.searchParams.forEach((value, key) => {
      if (key !== 'id_produit' && key !== 'src_integ') extraParams[key] = value;
    });
    return { idProduit, srcInteg, extraParams };
  } catch {
    return null;
  }
}

export function CTABlock({ data }: CTABlockProps) {
  const [groupeeModalOpen, setGroupeeModalOpen] = useState(false);
  const [produitModalOpen, setProduitModalOpen] = useState(false);

  const demandeInfo  = data.ctaUrl ? parseDemandeInfo(data.ctaUrl) : null;
  const contactInfo  = data.ctaUrl ? parseContactInfo(data.ctaUrl) : null;
  const isDemandeInfo = demandeInfo !== null;
  const isContactInfo = contactInfo !== null;

  return (
    <>
      <div className="my-8 flex flex-col gap-4 rounded-xl border border-cta/30 bg-gradient-to-br from-cta/10 via-card to-card p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-cta/15 text-cta">
            <ArrowRight className="h-6 w-6" aria-hidden="true" />
          </div>
          <div>
            <p className="font-bold text-foreground">{data.title}</p>
            {data.subtitle && (
              <p className="text-sm text-muted-foreground">{data.subtitle}</p>
            )}
          </div>
        </div>

        {isDemandeInfo ? (
          /* demande_info.php → formulaire demande groupée */
          <button
            type="button"
            onClick={() => setGroupeeModalOpen(true)}
            className="shrink-0 cursor-pointer rounded-md bg-cta px-5 py-3 text-sm font-bold uppercase tracking-wide text-cta-foreground shadow-md hover:bg-cta-hover"
          >
            {data.ctaLabel}
          </button>
        ) : isContactInfo ? (
          /* contact_info.php → formulaire demande sur produit */
          <button
            type="button"
            onClick={() => setProduitModalOpen(true)}
            className="shrink-0 cursor-pointer rounded-md bg-cta px-5 py-3 text-sm font-bold uppercase tracking-wide text-cta-foreground shadow-md hover:bg-cta-hover"
          >
            {data.ctaLabel}
          </button>
        ) : data.ctaUrl ? (
          /* URL classique → lien normal */
          <a
            href={data.ctaUrl}
            className="shrink-0 rounded-md bg-cta px-5 py-3 text-sm font-bold uppercase tracking-wide text-cta-foreground shadow-md hover:bg-cta-hover"
          >
            {data.ctaLabel}
          </a>
        ) : (
          <button
            type="button"
            className="shrink-0 rounded-md bg-cta px-5 py-3 text-sm font-bold uppercase tracking-wide text-cta-foreground shadow-md hover:bg-cta-hover"
          >
            {data.ctaLabel}
          </button>
        )}
      </div>

      {/* Modal demande groupée */}
      {isDemandeInfo && demandeInfo && (
        <IframeFormModal
          idRubrique={demandeInfo.idRubrique}
          category=""
          extraParams={Object.keys(demandeInfo.extraParams).length > 0 ? demandeInfo.extraParams : undefined}
          startFromStep1
          open={groupeeModalOpen}
          onClose={() => setGroupeeModalOpen(false)}
        />
      )}

      {/* Modal demande sur produit */}
      {isContactInfo && contactInfo && (
        <IframeProduitModal
          idProduit={contactInfo.idProduit}
          srcInteg={contactInfo.srcInteg}
          extraParams={Object.keys(contactInfo.extraParams).length > 0 ? contactInfo.extraParams : undefined}
          open={produitModalOpen}
          onClose={() => setProduitModalOpen(false)}
        />
      )}
    </>
  );
}
