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
  // Placement grille desktop selon présence d'image (ne pas réserver la colonne
  // image si absente, sinon le texte hérite de ses 220 px).
  const gridCols = data.image
    ? 'lg:grid-cols-[220px_minmax(0,1fr)_auto]'
    : 'lg:grid-cols-[minmax(0,1fr)_auto]';
  const textCol = data.image ? 'lg:col-start-2' : 'lg:col-start-1';
  const btnCol = data.image ? 'lg:col-start-3' : 'lg:col-start-2';

  return (
    <HubSection id={HUB_SECTION_IDS.finalCta}>
      <div className="overflow-hidden rounded-3xl bg-navy-deep px-5 py-8 sm:px-10 sm:py-12">
        {/* MOBILE : pile badge (haut) → image → titre/texte/avantages → bouton.
            DESKTOP : image à gauche, colonne texte (badge en tête) au centre,
            bouton à droite. Un seul markup réordonné par la grille, pas de doublon. */}
        <div className={`grid items-center gap-6 sm:gap-8 lg:gap-10 ${gridCols}`}>
          {/* Badge — mobile : tout en haut (centré) ; desktop : en tête du texte. */}
          <div className={`text-center lg:text-left lg:row-start-1 ${textCol}`}>
            {/* `TAG` : même échelle que toutes les pastilles de la page. La valeur
                était identique en dur — la constante évite qu'elles divergent. */}
            <span
              className={`inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-white ${TAG}`}
            >
              {data.badge}
            </span>
          </div>

          {data.image && (
            <div className="flex justify-center lg:col-start-1 lg:row-span-2 lg:row-start-1 lg:justify-start lg:self-center">
              <div className="relative h-44 w-36 sm:h-64 sm:w-52">
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

          {/* Titre + trait + texte + avantages. Le badge a sa propre cellule
              au-dessus : il n'est plus rendu ici. */}
          <div className={`min-w-0 text-center lg:text-left lg:row-start-2 ${textCol}`}>
            {/* Hors plan de titres (2026-08-07) : bandeau de conversion, pas une
                section de contenu. Apparence inchangée. */}
            <p className={`${SECTION_TITLE} text-white`}>
              <HubTitle parts={data.titleParts} />
            </p>

            <span className="mx-auto mt-4 block h-0.5 w-16 bg-cta/70 lg:mx-0" />

            {/* `max-w-[42rem]` et non `max-w-2xl` : ce token vaut 1400px ici
                (cf. --container-2xl dans globals.css). */}
            {/* `mx-auto` (son centrage mobile) + `SECTION_SUBTITLE` (l'échelle
                partagée) : le centrage reste au point d'appel. */}
            <p className={`mx-auto mt-4 max-w-[42rem] ${SECTION_SUBTITLE} text-white/80`}>
              {data.text}
            </p>

            <ul className="mt-5 flex flex-col items-start gap-3 lg:flex-row lg:flex-wrap lg:items-center lg:justify-start lg:gap-x-6 lg:gap-y-3">
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

          {/* Bouton + réassurance. */}
          <div
            className={`relative flex flex-col items-center gap-3 lg:row-span-2 lg:row-start-1 lg:self-center lg:pl-8 ${btnCol}`}
          >
            <span
              aria-hidden
              className="absolute left-0 top-0 hidden h-full border-l border-dashed border-white/25 lg:block"
            />
            <GuideButton
              entryPoint="cta_final"
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
