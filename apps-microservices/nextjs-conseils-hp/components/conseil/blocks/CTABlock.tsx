'use client';

import { useState } from 'react';
import { ArrowRight } from 'lucide-react';
import type { CTABlockData } from '@/types/blocks/cta';
import { IframeFormModal } from '@/components/conseil/IframeFormModal';

interface CTABlockProps {
  data: CTABlockData;
}

/**
 * Détecte si l'URL pointe vers demande_info.php.
 * Si oui → extraire f (= id_rubrique) + tous les autres params à passer à l'iframe.
 * L'URL demande_info.php ne doit JAMAIS apparaître dans le HTML (SEO/crawl).
 *
 * Exemple : https://www.hellopro.fr/demande_info.php?soc=1&origine=46&f=1002011
 *   → idRubrique = "1002011"
 *   → extraParams = { soc: "1", origine: "46" }
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

export function CTABlock({ data }: CTABlockProps) {
  const [modalOpen, setModalOpen] = useState(false);

  // Détection demande_info.php
  const demandeInfo   = data.ctaUrl ? parseDemandeInfo(data.ctaUrl) : null;
  const isDemandeInfo = demandeInfo !== null;

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
          /* demande_info.php → bouton qui ouvre l'iframe, jamais de href dans le DOM */
          <button
            type="button"
            onClick={() => setModalOpen(true)}
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

      {/* Modal iframe — démarre à l'étape 1 (start=1) car pas de pré-sélection */}
      {isDemandeInfo && demandeInfo && (
        <IframeFormModal
          idRubrique={demandeInfo.idRubrique}
          category=""
          extraParams={Object.keys(demandeInfo.extraParams).length > 0 ? demandeInfo.extraParams : undefined}
          startFromStep1
          open={modalOpen}
          onClose={() => setModalOpen(false)}
        />
      )}
    </>
  );
}
