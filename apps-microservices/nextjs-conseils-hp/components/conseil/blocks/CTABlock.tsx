import { ArrowRight } from 'lucide-react';
import type { CTABlockData } from '@/types/blocks/cta';
import { CtaBlockAction } from './CtaBlockAction';

interface CTABlockProps {
  data: CTABlockData;
}

/** Accroches par défaut quand le BO n'en fournit pas. */
const DEFAULT_CTA_TITLE = 'Estimez le prix de votre projet en 30 secondes';
const DEFAULT_CTA_SUBTITLE = 'Recevez jusqu’à 3 devis gratuits de fournisseurs locaux';

/** Remplace « constructeur(s) » par « fournisseur(s) » (BO ou défaut), casse conservée. */
function constructeurToFournisseur(s: string): string {
  return s.replace(/Constructeur/g, 'Fournisseur').replace(/constructeur/g, 'fournisseur');
}

export function CTABlock({ data }: CTABlockProps) {
  const title = constructeurToFournisseur(data.title || DEFAULT_CTA_TITLE);
  const subtitle = constructeurToFournisseur(data.subtitle || DEFAULT_CTA_SUBTITLE);

  return (
    <div className="my-8 flex flex-col gap-4 rounded-xl border border-cta/30 bg-gradient-to-br from-cta/10 via-card to-card p-5 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center gap-4">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-cta/15 text-cta">
          <ArrowRight className="h-6 w-6" aria-hidden="true" />
        </div>
        <div>
          <p className="text-base font-bold text-foreground">{title}</p>
          <p className="text-sm text-muted-foreground">{subtitle}</p>
        </div>
      </div>

      {/* Interactivité (bouton → modale) isolée en client component ciblé */}
      <CtaBlockAction ctaUrl={data.ctaUrl} ctaLabel={data.ctaLabel} />
    </div>
  );
}
