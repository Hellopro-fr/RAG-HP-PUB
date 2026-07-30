import { HubSection } from './primitives';
import { sanitizeHubHtml } from '@/lib/hub/sanitize';
import type { HubEdito } from '@/types/hub';

/**
 * Section éditoriale — le contenu SEO de la page.
 *
 * Server Component, colonne unique en `max-w-3xl` : c'est du texte long, la
 * largeur de lecture compte plus que l'occupation de l'écran.
 *
 * Trois formes possibles, combinables : `intro` (paragraphe), `items` (liste à
 * puces), `bodyHtml` (prose avec emphase inline, assainie). `bodyHtml` existe
 * parce que certains paragraphes ont du gras au milieu d'une phrase — impossible
 * à exprimer proprement en texte plat sans mettre du JSX dans les données.
 */
export function EditoSection({ data }: { data: HubEdito }) {
  return (
    <HubSection id={data.id} compact>
      <div className="mx-auto max-w-3xl">
        <h2 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
          {data.title}
        </h2>

        {/* `intro`, `items` et `note` acceptent du HTML restreint, comme `bodyHtml` :
            les chiffres clés et les intitulés de puce sont mis en gras au milieu
            des phrases. Tout passe par le même sanitizer. */}
        {data.intro && (
          <p
            className="mt-4 text-base text-muted-foreground [&_strong]:font-semibold [&_strong]:text-foreground"
            dangerouslySetInnerHTML={{ __html: sanitizeHubHtml(data.intro) }}
          />
        )}

        {data.bodyHtml && (
          <div
            className="mt-4 space-y-3 text-base text-muted-foreground [&_li]:ml-5 [&_li]:list-disc [&_strong]:text-foreground [&_ul]:space-y-3"
            dangerouslySetInnerHTML={{ __html: sanitizeHubHtml(data.bodyHtml) }}
          />
        )}

        {data.items && data.items.length > 0 && (
          <ul className="mt-4 space-y-2">
            {data.items.map((item) => (
              <li key={item} className="flex items-start gap-2 text-base text-foreground">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                <span
                  className="[&_strong]:font-semibold"
                  dangerouslySetInnerHTML={{ __html: sanitizeHubHtml(item) }}
                />
              </li>
            ))}
          </ul>
        )}

        {data.note && (
          <p
            className="mt-6 rounded-2xl border border-border bg-surface p-5 text-sm text-muted-foreground [&_strong]:font-semibold [&_strong]:text-foreground"
            dangerouslySetInnerHTML={{ __html: sanitizeHubHtml(data.note) }}
          />
        )}
      </div>
    </HubSection>
  );
}
