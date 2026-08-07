import { HubSection } from './primitives';
import { sanitizeHubHtml } from '@/lib/hub/sanitize';
import { PROSE as PROSE_SCALE, SECTION_TITLE } from './typography';
import type { HubEdito } from '@/types/hub';

/**
 * Typographie du bloc : la constante `PROSE` de l'échelle partagée, plus la
 * couleur (la couleur n'est jamais dans l'échelle — cf. `typography.ts`).
 * Une seule taille, une seule couleur, le gras dans la couleur du texte courant.
 */
const PROSE = `${PROSE_SCALE} text-foreground`;

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
        {/* `h2` — arbitré le 2026-08-07 par l'équipe SEO. Les blocs éditoriaux
            sont des sections de plein droit : ils portent le contenu le plus riche
            en mots-clés de la page et ne dépendent d'aucune section parente.
            Un passage en `h3` les avait rattachés au dernier `h2` rendu avant eux
            (« Explorez les grandes étapes », « Comment ça marche ? »), où deux
            d'entre eux se lisaient comme les étapes 5 et 6 du processus. */}
        <h2 className={`${SECTION_TITLE} text-foreground`}>{data.title}</h2>

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
