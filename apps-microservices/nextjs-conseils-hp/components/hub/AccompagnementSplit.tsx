import Image from 'next/image';
import { HubSection, HubIcon } from './primitives';
import { CHECK_ITEM, PROSE, SECTION_TITLE } from './typography';
import { sanitizeHubHtml } from '@/lib/hub/sanitize';
import { HUB_SECTION_IDS } from '@/lib/hub/anchors';
import type { HubAccompagnement } from '@/types/hub';

/** Bloc « accompagnement humain » : visuel, texte, liste de garanties. */
export function AccompagnementSplit({ data }: { data: HubAccompagnement }) {
  return (
    <HubSection id={HUB_SECTION_IDS.accompagnement}>
      <div className="overflow-hidden rounded-2xl border border-border bg-surface">
        <div className="grid lg:grid-cols-12">
          {data.image && (
            <div className="relative min-h-[13rem] lg:col-span-4">
              <Image
                src={data.image.src}
                alt={data.image.alt}
                fill
                sizes="(max-width: 1024px) 100vw, 33vw"
                className="object-cover"
              />
            </div>
          )}

          <div
            className={`flex flex-col justify-center gap-5 p-6 sm:p-8 ${
              data.image ? 'lg:col-span-5' : 'lg:col-span-8'
            }`}
          >
            {/* Hors plan de titres (2026-08-07) : section de réassurance, sans
                mot-clé métier. `SECTION_TITLE` conservé — seule la balise change. */}
            <p className={`${SECTION_TITLE} text-foreground`}>{data.title}</p>
            {/* HTML restreint : le texte de référence compte deux paragraphes. */}
            <div
              className={`space-y-3 ${PROSE} text-muted-foreground [&_strong]:text-foreground`}
              dangerouslySetInnerHTML={{ __html: sanitizeHubHtml(data.text) }}
            />
          </div>

          <div className="flex flex-col justify-center gap-3 p-6 sm:p-8 lg:col-span-3">
            {data.points.map((point) => (
              <div key={point} className="flex items-start gap-2.5">
                <HubIcon name="check-circle" className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
                <span className={`${CHECK_ITEM} text-foreground`}>{point}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </HubSection>
  );
}
