import Image from 'next/image';
import { HubSection, HubIcon } from './primitives';
import type { HubGrandeEtape } from '@/types/hub';

/**
 * Tuiles de navigation vers les blocs thématiques de la page.
 *
 * Une tuile sans `href` est rendue en `<div>` et non en lien mort — c'est le cas
 * d'« Exploitation », qui n'a pas de bloc correspondant sur cette page.
 */
export function GrandesEtapes({
  data,
}: {
  data: { title: string; items: HubGrandeEtape[] };
}) {
  return (
    <HubSection id="grandes-etapes" className="bg-surface">
      <div className="mx-auto max-w-3xl text-center">
        <h2 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
          {data.title}
        </h2>
      </div>

      <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {data.items.map((item) => {
          const content = (
            <>
              {item.image ? (
                <div className="relative aspect-square w-full">
                  <Image
                    src={item.image.src}
                    alt={item.image.alt}
                    fill
                    sizes="(max-width: 640px) 100vw, 240px"
                    className="object-cover"
                  />
                </div>
              ) : (
                // Vignette non livrée → aplat neutre.
                <div className="flex aspect-square w-full items-center justify-center bg-surface-muted text-primary/30">
                  <HubIcon name="compass" className="h-9 w-9" />
                </div>
              )}
              <div className="px-4 py-4 text-center text-sm font-semibold text-foreground">
                {item.label}
              </div>
            </>
          );

          const className =
            'overflow-hidden rounded-2xl border border-border bg-card shadow-sm transition';

          return item.href ? (
            <a
              key={item.label}
              href={item.href}
              className={`${className} hover:-translate-y-1 hover:shadow-elegant`}
            >
              {content}
            </a>
          ) : (
            <div key={item.label} className={className}>
              {content}
            </div>
          );
        })}
      </div>
    </HubSection>
  );
}
