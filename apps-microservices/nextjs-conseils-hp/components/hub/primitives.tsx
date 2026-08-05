import { resolveHubIcon } from '@/lib/hub/icons';
import { TAG } from './typography';
import type { HubIconName, HubTitlePart } from '@/types/hub';

/**
 * Primitives présentationnelles du template HUB.
 * Toutes Server Components — aucun état, aucun événement.
 */

interface HubSectionProps {
  id?: string;
  className?: string;
  /** Espacement vertical réduit — utilisé par les sections éditoriales. */
  compact?: boolean;
  children: React.ReactNode;
}

/**
 * Conteneur de section : ancre, largeur max, espacement.
 * `scroll-mt-32` compense le header sticky quand on arrive par une ancre.
 */
export function HubSection({ id, className = '', compact = false, children }: HubSectionProps) {
  const spacing = compact ? 'py-5 sm:py-6' : 'py-10 sm:py-12';
  return (
    <section id={id} className={`scroll-mt-32 px-4 ${spacing} ${className}`}>
      <div className="mx-auto max-w-7xl">{children}</div>
    </section>
  );
}

/** Pastille de rubrique (« Budget & financement », « Équipements »…). */
export function CategoryTag({ icon, children }: { icon?: HubIconName; children: React.ReactNode }) {
  return (
    <span
      className={`inline-flex w-fit items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1 text-primary ${TAG}`}
    >
      <HubIcon name={icon} className="h-3.5 w-3.5" />
      {children}
    </span>
  );
}

/**
 * Rend une icône depuis son nom. Ne rend rien si le nom est absent — c'est le
 * comportement voulu, un champ `icon` optionnel ne doit pas casser la mise en page.
 */
export function HubIcon({ name, className = 'h-5 w-5' }: { name?: HubIconName; className?: string }) {
  const Icon = resolveHubIcon(name);
  if (!Icon) return null;
  return <Icon className={className} aria-hidden />;
}

/**
 * Rend un titre découpé en fragments, les fragments `accent` en orange.
 * Évite d'avoir du JSX dans les fichiers de données.
 */
export function HubTitle({ parts }: { parts: HubTitlePart[] }) {
  return (
    <>
      {parts.map((part, index) =>
        part.accent ? (
          <span key={index} className="text-cta">
            {part.text}
          </span>
        ) : (
          <span key={index}>{part.text}</span>
        )
      )}
    </>
  );
}

/** Puce de liste « check » sur fond orange. */
export function CheckBullet() {
  return (
    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-cta text-cta-foreground">
      <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="3" aria-hidden>
        <path d="M20 6 9 17l-5-5" />
      </svg>
    </span>
  );
}
