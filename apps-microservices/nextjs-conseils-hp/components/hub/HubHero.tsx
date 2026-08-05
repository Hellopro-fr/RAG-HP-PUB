import Image from 'next/image';
import { HubIcon, HubTitle } from './primitives';
import type { HubHero as HubHeroData } from '@/types/hub';

/**
 * Hero des pages HUB. Server Component.
 *
 * Le `<h1>` est le premier contenu textuel du DOM, avant tout widget — c'est la
 * règle de prominence SEO déjà payée cher sur les pages conseils.
 *
 * L'image de fond est `priority` : c'est le LCP de la page.
 * Absente → fond sombre uni, la lisibilité est assurée par les mêmes dégradés.
 */
export function HubHero({
  data,
  formSlot,
}: {
  data: HubHeroData;
  /**
   * Colonne droite — reçoit `AssistantForm` (client). Passé en slot plutôt
   * qu'importé ici pour que le hero reste un Server Component et que la
   * frontière client soit visible dans `HubTemplate`.
   */
  formSlot?: React.ReactNode;
}) {
  return (
    <section className="relative overflow-hidden bg-neutral-950">
      {data.background && (
        <div className="absolute inset-0">
          <Image
            src={data.background.src}
            alt={data.background.alt}
            fill
            priority
            sizes="100vw"
            className="scale-105 object-cover blur-[2px]"
          />
        </div>
      )}

      {/* Assombrissement global + dégradé gauche→droite + vignette haut/bas */}
      <div className="absolute inset-0 bg-black/45" />
      <div className="absolute inset-0 bg-gradient-to-r from-black/85 via-black/55 to-black/10" />
      <div className="absolute inset-0 bg-gradient-to-b from-black/40 via-transparent to-black/50" />

      <div className="relative mx-auto flex min-h-[560px] max-w-7xl items-center px-4 py-12 sm:py-16 lg:py-20">
        <div className="flex w-full flex-col items-center gap-10 lg:flex-row lg:gap-[8%]">
          {/* `max-w-[42rem]` et non `max-w-2xl` : ce token vaut 1400px ici
              (cf. --container-2xl dans globals.css). */}
          <div className="w-full max-w-[42rem] lg:flex-1">
            <span className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-white backdrop-blur">
              <span className="h-1.5 w-1.5 rounded-full bg-cta" />
              {data.badge}
            </span>

            <h1 className="mt-5 text-4xl font-bold leading-[1.05] tracking-tight text-white sm:text-5xl lg:text-6xl">
              <HubTitle parts={data.titleParts} />
            </h1>

            <p className="mt-5 max-w-[42rem] text-base text-white/80 sm:text-lg">
              {data.subtitle}
            </p>

            {/* Mobile : timeline verticale (pastilles reliées par une ligne).
                Desktop (sm+) : grille 3 colonnes, icône au-dessus (inchangé).
                Même markup `<ul><li>` + texte réel → aucune régression SEO. */}
            <ul className="mt-8 flex flex-col sm:grid sm:grid-cols-3 sm:gap-5">
              {data.features.map((feature) => (
                <li
                  key={feature.title}
                  className="group relative flex gap-4 pb-6 last:pb-0 sm:block sm:pb-0"
                >
                  {/* Connecteur vertical — mobile seulement, masqué sous le dernier. */}
                  <span
                    aria-hidden
                    className="absolute bottom-1 left-5 top-11 w-px -translate-x-1/2 bg-white/20 group-last:hidden sm:hidden"
                  />
                  <span className="relative z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/15 bg-white/10 text-white backdrop-blur sm:mb-2">
                    <HubIcon name={feature.icon} />
                  </span>
                  <div className="flex flex-col gap-1">
                    <span className="text-sm font-semibold text-white">{feature.title}</span>
                    <span className="text-xs text-white/70">{feature.desc}</span>
                  </div>
                </li>
              ))}
            </ul>

            {(data.trust.rating || data.trust.suppliers) && (
              <ul className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3 text-sm">
                {data.trust.rating && (
                  <li className="flex items-center gap-2">
                    <span className="flex items-center gap-0.5 text-rating" aria-hidden>
                      {[0, 1, 2, 3, 4].map((i) => (
                        <svg key={i} viewBox="0 0 24 24" className="h-4 w-4 fill-current">
                          <path d="M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 22 12 18.56 5.82 22 7 14.14l-5-4.87 6.91-1.01L12 2z" />
                        </svg>
                      ))}
                    </span>
                    <span className="font-semibold text-white">{data.trust.rating}</span>
                  </li>
                )}
                {data.trust.suppliers && (
                  <li className="flex items-center gap-2 text-white">
                    <HubIcon name="users" className="h-4 w-4 text-cta" />
                    <span className="font-semibold">{data.trust.suppliers}</span>
                  </li>
                )}
              </ul>
            )}
          </div>

          {formSlot && <div className="w-full lg:max-w-[560px]">{formSlot}</div>}
        </div>
      </div>
    </section>
  );
}
