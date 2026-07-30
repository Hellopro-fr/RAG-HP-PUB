import Image from 'next/image';
import { HubSection, HubIcon } from './primitives';
import { AssistantButton } from './triggers';
import type { HubIconName, HubRessources } from '@/types/hub';

/**
 * Grille de ressources en fin de page.
 *
 * Le prototype Lovable déclarait 20 items puis les filtrait sur un seul tag
 * (« Exploitation »), n'en affichant que 3 — et couplait chaque image au titre
 * exact de l'article via un dictionnaire de 19 entrées. On ne porte que les
 * items réellement rendus, et l'image vit dans l'item.
 */

/** Icône de rubrique. Un tag inconnu n'affiche simplement pas d'icône. */
const TAG_ICONS: Record<string, HubIconName> = {
  'Budgets & financement': 'piggy-bank',
  Équipements: 'wrench',
  'Réglementation & démarches': 'scale',
  Dimensionnement: 'ruler',
  Exploitation: 'factory',
};

export function RessourcesGrid({ data }: { data: HubRessources }) {
  return (
    <HubSection id="nos-ressources">
      <div className="mx-auto max-w-3xl text-center">
        <h2 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
          {data.title}
        </h2>
        <p className="mt-3 text-base text-muted-foreground sm:text-lg">{data.subtitle}</p>
      </div>

      <div className="mt-10 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {data.items.map((item) => (
          <article
            key={item.title}
            className="flex h-full flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-sm transition hover:-translate-y-1 hover:shadow-elegant"
          >
            {item.image ? (
              <div className="relative h-52 w-full shrink-0">
                <Image
                  src={item.image.src}
                  alt={item.image.alt}
                  fill
                  sizes="(max-width: 768px) 100vw, 380px"
                  className="object-cover"
                />
              </div>
            ) : (
              <div className="flex h-52 w-full shrink-0 items-center justify-center bg-surface-muted text-primary/30">
                <HubIcon name={TAG_ICONS[item.tag]} className="h-10 w-10" />
              </div>
            )}
            <div className="flex flex-1 flex-col gap-3 p-5">
              <span className="inline-flex w-fit items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider text-primary">
                <HubIcon name={TAG_ICONS[item.tag]} className="h-3 w-3" />
                {item.tag}
              </span>
              <h3 className="text-base font-bold leading-snug text-foreground">{item.title}</h3>
              <div className="mt-auto">
                {item.href ? (
                  <a
                    href={item.href}
                    className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline"
                  >
                    En savoir plus
                    <HubIcon name="arrow-right" className="h-4 w-4" />
                  </a>
                ) : (
                  // Sans URL : on oriente vers le questionnaire plutôt que
                  // d'exposer un lien mort.
                  <AssistantButton
                    label="Être accompagné"
                    variant="link"
                    icon="arrow-right"
                    iconPosition="end"
                  />
                )}
              </div>
            </div>
          </article>
        ))}
      </div>
    </HubSection>
  );
}
