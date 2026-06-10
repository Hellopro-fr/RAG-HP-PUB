'use client';

import { useState } from 'react';
import Image from 'next/image';
import { ArrowRight } from 'lucide-react';
import type { TexteImageBlockData } from '@/types/blocks/texte-image';
import { IframeFormModal } from '@/components/conseil/IframeFormModal';
import { IframeProduitModal } from '@/components/conseil/IframeProduitModal';

interface TexteImageBlockProps {
  data: TexteImageBlockData;
}

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

export function TexteImageBlock({ data }: TexteImageBlockProps) {
  const [groupeeModalOpen, setGroupeeModalOpen] = useState(false);
  const [produitModalOpen, setProduitModalOpen] = useState(false);

  const demandeInfo  = data.ctaUrl ? parseDemandeInfo(data.ctaUrl) : null;
  const contactInfo  = data.ctaUrl ? parseContactInfo(data.ctaUrl) : null;
  const isDemandeInfo = demandeInfo !== null;
  const isContactInfo = contactInfo !== null;

  // Blocs 4 & 5 : dimensions naturelles sans +9px (min-height commenté côté PHP)
  const hasDims = data.image.width !== undefined && data.image.height !== undefined;
  const w = data.image.width ?? 600;
  const h = data.image.height ?? 400;

  // Sans taille connue : unoptimized + width:auto → rendu à dimensions naturelles,
  // jamais d'upscale depuis une source plus petite que le fallback 600px.
  const imageEl = hasDims ? (
    <Image
      src={data.image.src}
      alt={data.image.alt}
      width={w}
      height={h}
      className="h-auto max-w-full"
      style={{ maxWidth: `${w}px` }}
      sizes={`(max-width: 768px) 100vw, ${w}px`}
    />
  ) : (
    <Image
      src={data.image.src}
      alt={data.image.alt}
      width={600}
      height={400}
      unoptimized
      className="h-auto max-w-full"
      style={{ width: 'auto', height: 'auto' }}
    />
  );

  const imageColAlign = data.imagePosition === 'left' ? 'md:items-start' : 'md:items-end';
  const imageCol = (
    <figure className={`flex flex-col items-center ${imageColAlign}`}>
      <div className="w-fit max-w-full overflow-hidden rounded-xl">
        {imageEl}
      </div>
    </figure>
  );

  const ctaButton = isDemandeInfo ? (
    <button
      type="button"
      onClick={() => setGroupeeModalOpen(true)}
      className="mt-2 inline-flex cursor-pointer items-center gap-2 self-start rounded-md bg-cta px-5 py-2.5 text-sm font-bold uppercase tracking-wide text-cta-foreground hover:bg-cta-hover"
    >
      {data.ctaLabel} <ArrowRight className="h-4 w-4" />
    </button>
  ) : isContactInfo ? (
    <button
      type="button"
      onClick={() => setProduitModalOpen(true)}
      className="mt-2 inline-flex cursor-pointer items-center gap-2 self-start rounded-md bg-cta px-5 py-2.5 text-sm font-bold uppercase tracking-wide text-cta-foreground hover:bg-cta-hover"
    >
      {data.ctaLabel} <ArrowRight className="h-4 w-4" />
    </button>
  ) : data.ctaUrl ? (
    <a
      href={data.ctaUrl}
      className="mt-2 inline-flex items-center gap-2 self-start rounded-md bg-cta px-5 py-2.5 text-sm font-bold uppercase tracking-wide text-cta-foreground hover:bg-cta-hover"
    >
      {data.ctaLabel} <ArrowRight className="h-4 w-4" />
    </a>
  ) : (
    <button
      type="button"
      className="mt-2 inline-flex cursor-pointer items-center gap-2 self-start rounded-md bg-cta px-5 py-2.5 text-sm font-bold uppercase tracking-wide text-cta-foreground hover:bg-cta-hover"
    >
      {data.ctaLabel} <ArrowRight className="h-4 w-4" />
    </button>
  );

  const textCol = (
    <div className="flex flex-col gap-3">
      {data.estimate && (
        <div className="inline-flex items-baseline gap-2 self-start rounded-md bg-primary-soft px-3 py-2">
          {data.estimateLabel && (
            <span className="text-xs font-semibold uppercase tracking-wide text-primary">
              {data.estimateLabel}
            </span>
          )}
          <span className="text-lg font-extrabold text-primary">{data.estimate}</span>
        </div>
      )}
      <div
        className="text-base leading-relaxed text-foreground/90
          [&_p]:mb-3 [&_p:last-child]:mb-0
          [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:space-y-1
          [&_ol]:list-decimal [&_ol]:pl-5
          [&_li]:mb-1
          [&_strong]:font-bold [&_b]:font-bold"
        dangerouslySetInnerHTML={{ __html: data.html }}
      />
      {data.ctaLabel && ctaButton}
    </div>
  );

  // Image 40% / Texte 60% — règle PHP flex-basis: 40% sur la colonne image
  const gridCols = data.imagePosition === 'left'
    ? 'md:grid-cols-[2fr_3fr]'
    : 'md:grid-cols-[3fr_2fr]';

  return (
    <>
      <div className={`my-8 grid gap-8 md:items-start ${gridCols}`}>
        {data.imagePosition === 'left' ? (
          <>{imageCol}{textCol}</>
        ) : (
          <>{textCol}{imageCol}</>
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
