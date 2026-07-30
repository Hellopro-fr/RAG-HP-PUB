import Image from 'next/image';
import { HubSection, HubIcon } from './primitives';
import type { HubAccompagnement } from '@/types/hub';

/** Bloc « accompagnement humain » : visuel, texte, liste de garanties. */
export function AccompagnementSplit({ data }: { data: HubAccompagnement }) {
  return (
    <HubSection id="accompagnement">
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
            <h2 className="text-2xl font-bold tracking-tight text-foreground">{data.title}</h2>
            <p className="text-muted-foreground">{data.text}</p>
          </div>

          <div className="flex flex-col justify-center gap-3 p-6 sm:p-8 lg:col-span-3">
            {data.points.map((point) => (
              <div key={point} className="flex items-start gap-2.5">
                <HubIcon name="check-circle" className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
                <span className="text-sm font-medium text-foreground">{point}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </HubSection>
  );
}
