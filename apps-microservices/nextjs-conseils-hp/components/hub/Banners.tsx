import Image from 'next/image';
import { HubSection, CategoryTag, HubIcon } from './primitives';
import { AssistantButton, GuideButton } from './triggers';
import type { HubAccompagnementBanner, HubGuideCta, HubImage } from '@/types/hub';

/**
 * Les deux bandeaux horizontaux de la page (accompagnement, guide gratuit).
 * Même gabarit, deux contenus — d'où un composant unique paramétré.
 *
 * Le CTA ouvre le questionnaire (bannière accompagnement) ou le dialog de
 * téléchargement (bandeau guide), selon la prop `action`.
 */
interface BannerProps {
  id?: string;
  tag: string;
  tagIcon: 'phone-call' | 'book-open';
  title: string;
  text: string;
  ctaLabel: string;
  ctaIcon?: 'download';
  image?: HubImage;
  /** Quel dialog le CTA ouvre. */
  action: 'assistant' | 'guide';
}

function Banner({ id, tag, tagIcon, title, text, ctaLabel, ctaIcon, image, action }: BannerProps) {
  return (
    <HubSection id={id}>
      <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
        <div className="grid items-center gap-5 px-5 py-5 sm:px-6 lg:grid-cols-[160px_minmax(0,1fr)] lg:gap-8 lg:px-8">
          {image ? (
            // Boîte carrée + `object-contain` : le ratio réel est préservé sans
            // qu'on ait à déclarer les dimensions du fichier.
            <div className="relative mx-auto h-32 w-full max-w-[140px]">
              <Image
                src={image.src}
                alt={image.alt}
                fill
                sizes="160px"
                className="object-contain"
              />
            </div>
          ) : (
            // Visuel non livré → pastille d'icône.
            <div className="mx-auto flex h-24 w-24 items-center justify-center rounded-2xl bg-primary/10 text-primary">
              <HubIcon name={tagIcon} className="h-10 w-10" />
            </div>
          )}

          <div>
            <CategoryTag icon={tagIcon}>{tag}</CategoryTag>
            <div className="mt-2 flex flex-col items-start gap-4 sm:flex-row sm:items-center sm:justify-between">
              <h2 className="text-xl font-bold tracking-tight text-foreground sm:text-2xl">
                {title}
              </h2>
              {action === 'assistant' ? (
                <AssistantButton label={ctaLabel} icon={ctaIcon} />
              ) : (
                <GuideButton label={ctaLabel} icon={ctaIcon} variant="solid" />
              )}
            </div>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{text}</p>
          </div>
        </div>
      </div>
    </HubSection>
  );
}

export function AccompagnementBanner({ data }: { data: HubAccompagnementBanner }) {
  return (
    <Banner
      tag={data.tag}
      tagIcon="phone-call"
      title={data.title}
      text={data.text}
      ctaLabel={data.ctaLabel}
      image={data.image}
      action="assistant"
    />
  );
}

export function GuideCta({ data }: { data: HubGuideCta }) {
  return (
    <Banner
      id="guide-gratuit"
      tag={data.tag}
      tagIcon="book-open"
      title={data.title}
      text={data.text}
      ctaLabel={data.ctaLabel}
      ctaIcon="download"
      image={data.image}
      action="guide"
    />
  );
}
