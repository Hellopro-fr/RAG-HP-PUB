import { HubSection } from './primitives';
import { sanitizeHubHtml } from '@/lib/hub/sanitize';
import type { HubEdito } from '@/types/hub';

/**
 * Typographie UNIQUE du bloc éditorial : une seule taille, une seule couleur, le
 * gras dans la même couleur que le texte courant.
 *
 * Le bloc en comptait trois combinaisons — paragraphes en gris `text-base`, puces
 * en noir `text-base`, encart « À noter » en gris `text-sm` — plus des pastilles
 * bleues. À la lecture, ça donnait l'impression de plusieurs polices sur une même
 * section. Toute nuance de hiérarchie doit désormais passer par la structure
 * (titre, cadre de l'encart), pas par la couleur ou la taille du texte.
 */
const PROSE = 'text-base leading-relaxed text-foreground [&_strong]:font-semibold';

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
            className={`mt-4 ${PROSE}`}
            dangerouslySetInnerHTML={{ __html: sanitizeHubHtml(data.intro) }}
          />
        )}

        {data.bodyHtml && (
          <div
            className={`mt-4 space-y-4 ${PROSE} [&_li]:ml-5 [&_li]:list-disc [&_ul]:space-y-3`}
            dangerouslySetInnerHTML={{ __html: sanitizeHubHtml(data.bodyHtml) }}
          />
        )}

        {data.items && data.items.length > 0 && (
          <ul className="mt-4 space-y-2">
            {data.items.map((item) => (
              <li key={item} className={`flex items-start gap-2.5 ${PROSE}`}>
                {/* Pastille en noir : elle était bleue, seule touche de couleur
                    d'un bloc autrement monochrome. */}
                <span
                  aria-hidden
                  className="mt-[0.55rem] h-1.5 w-1.5 shrink-0 rounded-full bg-foreground"
                />
                <span dangerouslySetInnerHTML={{ __html: sanitizeHubHtml(item) }} />
              </li>
            ))}
          </ul>
        )}

        {data.note && (
          // Même typographie que le reste ; c'est le cadre qui distingue l'encart,
          // pas une taille ni une couleur de texte différentes.
          <p
            className={`mt-6 rounded-2xl border border-border bg-surface p-5 ${PROSE}`}
            dangerouslySetInnerHTML={{ __html: sanitizeHubHtml(data.note) }}
          />
        )}
      </div>
    </HubSection>
  );
}
