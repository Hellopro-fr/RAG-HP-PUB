'use client';

import { useState } from 'react';
import { ArrowRight } from 'lucide-react';
import { IframeFormModal, IframeProduitModal } from '@/components/conseil/lazyModals';

/**
 * Widget interactif du CTA de TexteImageBlock — isolé en client component ciblé.
 * Le reste du bloc (texte + image) est un Server Component pur : seul ce bouton
 * (ouverture de modale au clic) a besoin du client. Le clic ne pousse aucun
 * analytics ; le tracking vit dans les modales (déclenché à l'ouverture).
 */

/** demande_info.php → TOUJOURS IframeFormModal. */
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

/** contact_info.php → TOUJOURS IframeProduitModal, id_produit peut être absent. */
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

interface TexteImageCtaProps {
  ctaUrl?: string;
  ctaLabel: string;
}

export function TexteImageCta({ ctaUrl, ctaLabel }: TexteImageCtaProps) {
  const [groupeeModalOpen, setGroupeeModalOpen] = useState(false);
  const [produitModalOpen, setProduitModalOpen] = useState(false);

  const demandeInfo  = ctaUrl ? parseDemandeInfo(ctaUrl) : null;
  const contactInfo  = ctaUrl ? parseContactInfo(ctaUrl) : null;
  const isDemandeInfo = demandeInfo !== null;
  const isContactInfo = contactInfo !== null;

  const ctaButton = isDemandeInfo ? (
    <button
      type="button"
      onClick={() => setGroupeeModalOpen(true)}
      className="mt-2 inline-flex cursor-pointer items-center gap-2 self-start rounded-md bg-cta px-5 py-2.5 text-sm font-bold uppercase tracking-wide text-cta-foreground hover:bg-cta-hover"
    >
      {ctaLabel} <ArrowRight className="h-4 w-4" />
    </button>
  ) : isContactInfo ? (
    <button
      type="button"
      onClick={() => setProduitModalOpen(true)}
      className="mt-2 inline-flex cursor-pointer items-center gap-2 self-start rounded-md bg-cta px-5 py-2.5 text-sm font-bold uppercase tracking-wide text-cta-foreground hover:bg-cta-hover"
    >
      {ctaLabel} <ArrowRight className="h-4 w-4" />
    </button>
  ) : ctaUrl ? (
    <a
      href={ctaUrl}
      className="mt-2 inline-flex items-center gap-2 self-start rounded-md bg-cta px-5 py-2.5 text-sm font-bold uppercase tracking-wide text-cta-foreground hover:bg-cta-hover"
    >
      {ctaLabel} <ArrowRight className="h-4 w-4" />
    </a>
  ) : (
    <button
      type="button"
      className="mt-2 inline-flex cursor-pointer items-center gap-2 self-start rounded-md bg-cta px-5 py-2.5 text-sm font-bold uppercase tracking-wide text-cta-foreground hover:bg-cta-hover"
    >
      {ctaLabel} <ArrowRight className="h-4 w-4" />
    </button>
  );

  return (
    <>
      {ctaButton}

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
