import Image from 'next/image';
import { HubSection, HubIcon, HubTitle } from './primitives';
import { GuideButton } from './triggers';
import { CHECK_ITEM, META, SECTION_SUBTITLE, SECTION_TITLE, TAG } from './typography';
import { HUB_SECTION_IDS } from '@/lib/hub/anchors';
import type { HubFinalCta } from '@/types/hub';

/**
 * Bandeau de conversion en fin de page. Son id `cta-final` est la dernière entrée
 * du sommaire sticky ; son bouton ouvre le dialog de téléchargement du guide.
 */
export function FinalCta({ data }: { data: HubFinalCta }) {
  return (
    <HubSection id={HUB_SECTION_IDS.finalCta}>
      <div className="overflow-hidden rounded-3xl bg-navy-deep px-6 py-10 sm:px-10 sm:py-12">
        {/* Même précaution que dans LeadPopup : ne pas réserver la colonne image
            si l'image est absente, sinon le texte hérite de ses 220 px. */}
        <div
          className={`grid items-center gap-8 lg:gap-10 ${
            data.image
              ? 'lg:grid-cols-[220px_minmax(0,1fr)_auto]'
              : 'lg:grid-cols-[minmax(0,1fr)_auto]'
          }`}
        >
          {data.image && (
            <div className="flex justify-center lg:justify-start">
              <div className="relative h-56 w-44 sm:h-64 sm:w-52">
                <Image
                  src={data.image.src}
                  alt={data.image.alt}
                  fill
                  sizes="220px"
                  className="object-contain drop-shadow-2xl"
                />
              </div>
            </div>
          )}

          <div className="min-w-0 text-center lg:text-left">
            <span
              className={`inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-white ${TAG}`}
            >
              {data.badge}
            </span>

            <h2 className={`mt-4 ${SECTION_TITLE} text-white`}>
              <HubTitle parts={data.titleParts} />
            </h2>

            <span className="mt-4 block h-0.5 w-16 bg-cta/70" />

            {/* `max-w-[42rem]` et non `max-w-2xl` : ce token vaut 1400px ici
                (cf. --container-2xl dans globals.css). */}
            <p className={`mt-4 max-w-[42rem] ${SECTION_SUBTITLE} text-white/80`}>{data.text}</p>

            <ul className="mt-5 flex flex-wrap justify-center gap-x-6 gap-y-3 lg:justify-start">
              {data.items.map((item) => (
                <li key={item.label} className={`flex items-center gap-2 ${CHECK_ITEM} text-white`}>
                  <span className="grid h-8 w-8 place-items-center rounded-full bg-white/10">
                    <HubIcon name={item.icon} className="h-4 w-4 text-white" />
                  </span>
                  {item.label}
                </li>
              ))}
            </ul>
          </div>

          <div className="relative flex flex-col items-center gap-3 lg:pl-8">
            <span
              aria-hidden
              className="absolute left-0 top-0 hidden h-full border-l border-dashed border-white/25 lg:block"
            />
            <GuideButton
              label={data.ctaLabel}
              icon="download"
              variant="solid"
              className="h-14 w-full px-8 text-base lg:w-auto"
            />
            <p className={`flex items-center gap-1.5 ${META} text-white/70`}>
              <HubIcon name="shield" className="h-3.5 w-3.5" />
              {data.reassurance}
            </p>
          </div>
        </div>
      </div>
    </HubSection>
  );
}
